param(
    # Ссылка на "обновлятор" с Mesh/HTTP (exe или ps1)
    [string]$UpdaterUrl = "https://mesh.diwibot.ru/userfiles/adminded_sw/Steam/SteamSlots/steam_update_and_start_rds.ps1?download=1",

    # URL твоего slot-service (чтобы передать в обновлятор)
    [string]$ServiceBaseUrl = "https://steam-slots.diwibot.ru",

    # Папка Steam (для cleanup задачи; оставь как есть, если стандартно)
    [string]$SteamConfigPath1 = "C:\Program Files (x86)\Steam\config\loginusers.vdf",
    [string]$SteamConfigPath2 = "C:\Program Files\Steam\config\loginusers.vdf",

    # Задержка запуска обновлятора после логина
    [int]$LogonDelaySeconds = 5,

    # Имена задач
    [string]$TaskNameLogon   = "SteamSlot-RunUpdater",
    [string]$TaskNameStartup = "SteamSlot-CleanupLoginUsers"
)

$ErrorActionPreference = "Stop"

# ====== Self-elevation ======
function Ensure-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p  = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        $argList = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", "`"$PSCommandPath`""
        )

        foreach ($kv in $MyInvocation.BoundParameters.GetEnumerator()) {
            if ($kv.Value -is [switch]) {
                if ($kv.Value) { $argList += "-$($kv.Key)" }
            } else {
                $argList += "-$($kv.Key)"
                $argList += "`"$($kv.Value)`""
            }
        }

        Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $argList
        exit 0
    }
}
Ensure-Admin

# ====== Paths & logs ======
$BaseDir = "C:\SteamSlot"
New-Item -ItemType Directory -Force -Path $BaseDir | Out-Null
$LogFile = Join-Path $BaseDir "install.log"

function Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    $line | Tee-Object -FilePath $LogFile -Append | Out-Null
}

Log "=== INSTALL START ==="

# ====== PC identifiers ======
$PcName = $env:COMPUTERNAME

function Get-BoardSerial {
    $serial = $null

    # 1) BaseBoard serial (чаще всего то, что нужно)
    try {
        $bb = Get-CimInstance -ClassName Win32_BaseBoard -ErrorAction Stop
        if ($bb -and $bb.SerialNumber) { $serial = ($bb.SerialNumber + "") }
    } catch { }

    # 2) BIOS serial (фолбэк)
    if ([string]::IsNullOrWhiteSpace($serial) -or $serial -match "To be filled|Default string|None|System Serial Number") {
        try {
            $bios = Get-CimInstance -ClassName Win32_BIOS -ErrorAction Stop
            if ($bios -and $bios.SerialNumber) { $serial = ($bios.SerialNumber + "") }
        } catch { }
    }

    # 3) UUID (если вообще всё пусто)
    if ([string]::IsNullOrWhiteSpace($serial) -or $serial -match "To be filled|Default string|None|System Serial Number") {
        try {
            $cs = Get-CimInstance -ClassName Win32_ComputerSystemProduct -ErrorAction Stop
            if ($cs -and $cs.UUID) { $serial = ($cs.UUID + "") }
        } catch { }
    }

    # 4) Хеш-фолбэк (стабильный), если производитель отдал мусор
    if ([string]::IsNullOrWhiteSpace($serial) -or $serial -match "To be filled|Default string|None|System Serial Number") {
        $raw = ($env:COMPUTERNAME + "|" + (Get-CimInstance Win32_OperatingSystem).SerialNumber)
        $bytes = [Text.Encoding]::UTF8.GetBytes($raw)
        $sha = [System.Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
        $serial = ([BitConverter]::ToString($sha) -replace "-", "").Substring(0, 24)
    }

    # нормализация для передачи аргументом/ключом
    $serial = $serial.Trim()
    $serial = ($serial -replace "\s+", "_")
    $serial
}

$BoardSerial = Get-BoardSerial

Log "PcName=$PcName"
Log "BoardSerial(api_key)=$BoardSerial"

# ====== Download updater ======
function Get-FileNameFromUrl([string]$url) {
    try {
        $u = [Uri]$url
        $name = [System.IO.Path]::GetFileName($u.AbsolutePath)
        if ([string]::IsNullOrWhiteSpace($name)) { return "steam_updater.exe" }
        return $name
    } catch {
        return "steam_updater.exe"
    }
}

$UpdaterFileName = Get-FileNameFromUrl $UpdaterUrl
$UpdaterPath = Join-Path $BaseDir $UpdaterFileName

Log "Downloading updater: $UpdaterUrl"
Log "To: $UpdaterPath"

Invoke-WebRequest -Uri $UpdaterUrl -OutFile $UpdaterPath -UseBasicParsing
if (!(Test-Path $UpdaterPath)) { throw "Updater download failed: $UpdaterPath not found" }

# ====== Build command for Logon task (any user, normal privileges, interactive) ======
# Мы запускаем через powershell-wrapper, чтобы:
# - сделать задержку
# - одинаково запускать и exe, и ps1
$ext = [System.IO.Path]::GetExtension($UpdaterPath).ToLowerInvariant()

if ($ext -eq ".ps1") {
    $CommonArgs = @(
        "-ServiceBaseUrl", "`"$ServiceBaseUrl`"",
        "-PcName", "`"$PcName`"",
        "-PcKey", "`"$BoardSerial`""
    ) -join " "
} else {
    $CommonArgs = @(
        "--service", "`"$ServiceBaseUrl`"",
        "--pc", "`"$PcName`"",
        "--key", "`"$BoardSerial`""
    ) -join " "
}

# Собираем команду запуска (с задержкой)
if ($ext -eq ".ps1") {
    $RunCmd = "Start-Sleep -Seconds $LogonDelaySeconds; & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$UpdaterPath`" $CommonArgs"
} else {
    $RunCmd = "Start-Sleep -Seconds $LogonDelaySeconds; & `"$UpdaterPath`" $CommonArgs"
}

# Кодируем, чтобы не мучиться с кавычками в планировщике
$RunCmdB64 = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($RunCmd))


# ====== Create/Update TASK: ON LOGON (ANY USER) ======
function Register-LogonTask {
    try {
        Import-Module ScheduledTasks -ErrorAction Stop

        $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -EncodedCommand $RunCmdB64"
        $trigger = New-ScheduledTaskTrigger -AtLogOn

        # Принципиально: “любой пользователь”, запуск в его интерактивной сессии
        $principal = New-ScheduledTaskPrincipal -GroupId "BUILTIN\Users" -LogonType Group -RunLevel Limited

        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

        Register-ScheduledTask -TaskName $TaskNameLogon -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
        Log "Logon task created via ScheduledTasks: $TaskNameLogon"
        return $true
    } catch {
        Log "Register-LogonTask via ScheduledTasks failed: $($_.Exception.Message)"
        return $false
    }
}

function Register-LogonTaskFallbackSchtasks {
    try {
        $tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -EncodedCommand $RunCmdB64"

        # Попытка через NT AUTHORITY\INTERACTIVE (часто работает как “текущий вошедший”)
        $cmd = "schtasks /Create /F /TN `"$TaskNameLogon`" /SC ONLOGON /RU `"NT AUTHORITY\INTERACTIVE`" /RL LIMITED /TR `"$tr`""
        Log "Fallback schtasks cmd: $cmd"
        cmd.exe /c $cmd | Out-Null

        Log "Logon task created via schtasks: $TaskNameLogon"
        return $true
    } catch {
        Log "Register-LogonTaskFallbackSchtasks failed: $($_.Exception.Message)"
        return $false
    }
}

$okLogon = Register-LogonTask
if (-not $okLogon) {
    $okLogon = Register-LogonTaskFallbackSchtasks
}
if (-not $okLogon) {
    throw "Cannot create logon task (any user)."
}

# ====== Create/Update TASK: ON STARTUP (SYSTEM) cleanup loginusers.vdf ======
$cleanupCmd = @"
Remove-Item -LiteralPath '$SteamConfigPath1' -Force -ErrorAction SilentlyContinue;
Remove-Item -LiteralPath '$SteamConfigPath2' -Force -ErrorAction SilentlyContinue;
"@.Trim()

$cleanupCmdEsc = $cleanupCmd.Replace('"','\"')

function Register-StartupCleanupTask {
    try {
        Import-Module ScheduledTasks -ErrorAction Stop

        $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command `"$cleanupCmdEsc`""
        $trigger = New-ScheduledTaskTrigger -AtStartup
        $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

        Register-ScheduledTask -TaskName $TaskNameStartup -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
        Log "Startup cleanup task created via ScheduledTasks: $TaskNameStartup"
        return $true
    } catch {
        Log "Register-StartupCleanupTask via ScheduledTasks failed: $($_.Exception.Message)"
        return $false
    }
}

function Register-StartupCleanupTaskFallbackSchtasks {
    try {
        $tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command `"$cleanupCmdEsc`""
        $cmd = "schtasks /Create /F /TN `"$TaskNameStartup`" /SC ONSTART /RU `"SYSTEM`" /RL HIGHEST /TR `"$tr`""
        Log "Fallback schtasks cmd: $cmd"
        cmd.exe /c $cmd | Out-Null

        Log "Startup cleanup task created via schtasks: $TaskNameStartup"
        return $true
    } catch {
        Log "Register-StartupCleanupTaskFallbackSchtasks failed: $($_.Exception.Message)"
        return $false
    }
}

$okStartup = Register-StartupCleanupTask
if (-not $okStartup) {
    $okStartup = Register-StartupCleanupTaskFallbackSchtasks
}
if (-not $okStartup) {
    throw "Cannot create startup cleanup task."
}

Log "=== INSTALL DONE ==="
Log "UpdaterPath=$UpdaterPath"
Log "Tasks: $TaskNameLogon (ONLOGON any user), $TaskNameStartup (ONSTART SYSTEM cleanup)"
Log "Use BoardSerial(api_key)=$BoardSerial on server for this PC."
