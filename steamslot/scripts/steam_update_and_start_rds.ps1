param(
    # ===== Slot service =====
    [Parameter(Mandatory=$true)]
    [string]$ServiceBaseUrl,                 # пример: https://your-domain или http://127.0.0.1:8080

    [string]$PcName = $env:COMPUTERNAME,     # ДОЛЖНО совпадать с PC.name в админке сервиса

    [Parameter(Mandatory=$true)]
    [string]$PcKey,                          # PC.api_key из админки

    # ===== Steam paths =====
    [string]$SteamPath = "C:\Program Files (x86)\Steam\steam.exe",
    [string]$SteamRoot = "C:\Program Files (x86)\Steam",
    [string]$SteamConfigDir = "C:\Program Files (x86)\Steam\config",

    # ===== Update/Timing =====
    [int]$AcquireTtlSeconds = 900,
    [int]$AcquirePollSeconds = 20,
    [int]$HeartbeatSeconds = 60,

    [int]$SteamStartRetries = 2,
    [int]$LoginWaitSeconds = 120,

    [int]$DownloadsStableSeconds = 60,       # сколько секунд подряд downloading должен быть пуст
    [int]$DownloadsMaxWaitSeconds = 3600,    # максимум ждать обновления

    [int]$TargetAppId = 0,                   # если >0: триггер install/update этой игры

    [switch]$PatchManifestsAutoUpdate = $true,
    [switch]$RemoveLoginUsersAfter = $true,

    # ===== Post action =====
    [string]$RdsWrtcPath = "C:\Program Files\MTS Remote play\bin\rds-wrtc.exe",
    [switch]$StartRdsWrtc = $true
)

$ErrorActionPreference = "Stop"

# ========= Logs in C:\SteamSlot =========
$BaseDir = "C:\SteamSlot"
$LogDir  = Join-Path $BaseDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$LogFile = Join-Path $LogDir ("steam_update_user_" + $PcName + "_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

function Log([string]$msg) {
    $line = ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg)
    $line | Tee-Object -FilePath $LogFile -Append | Out-Null
}

# ========= Guard: must be normal interactive user (not SYSTEM) =========
try {
    $who = (whoami)
    if ($who -match "NT AUTHORITY\\SYSTEM") {
        Log "ERROR: Running as SYSTEM. Steam GUI won't work in Session 0. This script must run as the normal interactive user."
        throw "Running as SYSTEM is not supported."
    }
} catch {
    # if whoami fails - continue, but usually it exists
}

# ========= HTTP helpers =========
function Invoke-Json([string]$Method, [string]$Url, $BodyObj) {
    $headers = @{
        "Content-Type" = "application/json"
        "X-PC-KEY"      = $PcKey
    }
    $json = $BodyObj | ConvertTo-Json -Depth 10
    return Invoke-RestMethod -Method $Method -Uri $Url -Headers $headers -Body $json
}

function Download-LoginUsers([string]$Token, [string]$OutPath) {
    $headers = @{ "X-PC-KEY" = $PcKey }
    $url = "$ServiceBaseUrl/api/v1/loginusers?token=$Token"
    Invoke-WebRequest -Uri $url -Headers $headers -OutFile $OutPath
}

# ========= Steam helpers =========
function Stop-SteamHard {
    Log "Stopping Steam processes..."
    $names = @("steam", "steamwebhelper", "GameOverlayUI", "streaming_client", "steamerrorreporter")
    foreach ($n in $names) {
        Get-Process -Name $n -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    }
}

function Try-SoftExitSteam([int]$WaitSeconds = 45) {
    Log "Trying soft-exit Steam..."
    try { Start-Process "steam://exit" | Out-Null } catch { }

    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $WaitSeconds) {
        $p = Get-Process -Name "steam" -ErrorAction SilentlyContinue
        if (-not $p) {
            Log "Steam exited."
            return $true
        }
        Start-Sleep -Seconds 1
    }
    Log "Steam did not exit in time. Hard stop."
    Stop-SteamHard
    return $false
}

function Ensure-SteamInstalled {
    if (Test-Path $SteamPath) {
        Log "Steam found: $SteamPath"
        return
    }

    # Без админа мы НЕ гарантируем установку в Program Files.
    # Если Steam не установлен — лучше заранее ставить образ/шаблон.
    Log "ERROR: Steam not found at $SteamPath"
    throw "Steam is not installed (or SteamPath wrong). Install Steam beforehand or set -SteamPath/-SteamRoot."
}

function Start-Steam {
    Log "Starting Steam..."
    # -silent: обычно достаточно для автообновлений, но GUI-сессия при этом остается пользовательская
    Start-Process -FilePath $SteamPath -ArgumentList "-silent" | Out-Null

    # Открыть страницу загрузок (иногда помогает триггернуть UI/обновления)
    try { Start-Process "steam://open/downloads" | Out-Null } catch { }
}

function Wait-SteamLoginHeuristic {
    # Эвристика по логам (Steam не дает нормального API).
    $logFile = Join-Path $SteamRoot "logs\connection_log.txt"
    $sw = [Diagnostics.Stopwatch]::StartNew()

    Log "Waiting Steam login heuristic (${LoginWaitSeconds}s)..."

    while ($sw.Elapsed.TotalSeconds -lt $LoginWaitSeconds) {
        $p = Get-Process -Name "steam" -ErrorAction SilentlyContinue
        if (-not $p) {
            Log "Steam process not running while waiting login."
            return $false
        }

        if (Test-Path $logFile) {
            try {
                $tail = Get-Content -LiteralPath $logFile -Tail 200 -ErrorAction SilentlyContinue
                $joined = ($tail -join "`n")
                if ($joined -match "LogOnResponse" -or $joined -match "Logged on" -or $joined -match "Connected to Steam") {
                    Log "Login heuristic: OK"
                    return $true
                }
            } catch { }
        }

        Start-Sleep -Seconds 2
    }

    Log "Login heuristic: TIMEOUT"
    return $false
}

function Get-SteamLibraries {
    $libs = New-Object System.Collections.Generic.List[string]
    if (Test-Path $SteamRoot) { $libs.Add($SteamRoot) }

    $libFile = Join-Path $SteamRoot "steamapps\libraryfolders.vdf"
    if (!(Test-Path $libFile)) {
        return $libs.ToArray()
    }

    $txt = Get-Content -LiteralPath $libFile -Raw -ErrorAction SilentlyContinue
    if (-not $txt) { return $libs.ToArray() }

    $matches = [regex]::Matches($txt, '"path"\s*"([^"]+)"')
    foreach ($m in $matches) {
        $p = $m.Groups[1].Value -replace "\\\\", "\"
        if ($p -and (Test-Path $p) -and (-not $libs.Contains($p))) {
            $libs.Add($p)
        }
    }
    return $libs.ToArray()
}

function Has-ActiveDownloads {
    $libs = Get-SteamLibraries
    foreach ($l in $libs) {
        $d = Join-Path $l "steamapps\downloading"
        if (Test-Path $d) {
            $items = Get-ChildItem -LiteralPath $d -Force -ErrorAction SilentlyContinue
            if ($items -and $items.Count -gt 0) { return $true }
        }
    }
    return $false
}

function Find-AppManifest([int]$AppId) {
    $libs = Get-SteamLibraries
    foreach ($l in $libs) {
        $m = Join-Path $l ("steamapps\appmanifest_{0}.acf" -f $AppId)
        if (Test-Path $m) { return $m }
    }
    return $null
}

function Patch-AppManifestAutoUpdate([string]$ManifestPath) {
    # AutoUpdateBehavior "0" — обычно означает “всегда обновлять”
    $raw = Get-Content -LiteralPath $ManifestPath -Raw -ErrorAction Stop

    if ($raw -notmatch '"AutoUpdateBehavior"') {
        $raw = $raw -replace '("StateFlags"\s*"\d+")', '$1' + "`r`n`t`t" + '"AutoUpdateBehavior"' + "`t`t" + '"2"'
    } else {
        $raw = [regex]::Replace($raw, '"AutoUpdateBehavior"\s*"\d+"', '"AutoUpdateBehavior"        "2"')
    }

    if ($raw -notmatch '"AllowOtherDownloadsWhileRunning"') {
        $raw = $raw -replace '("AutoUpdateBehavior"\s*"\d+")', '$1' + "`r`n`t`t" + '"AllowOtherDownloadsWhileRunning"' + "`t" + '"0"'
    } else {
        $raw = [regex]::Replace($raw, '"AllowOtherDownloadsWhileRunning"\s*"\d+"', '"AllowOtherDownloadsWhileRunning" "0"')
    }

    Set-Content -LiteralPath $ManifestPath -Value $raw -Encoding UTF8
}

function Patch-AllManifests {
    if (-not $PatchManifestsAutoUpdate) { return }
    $libs = Get-SteamLibraries
    $count = 0

    foreach ($l in $libs) {
        $steamapps = Join-Path $l "steamapps"
        if (!(Test-Path $steamapps)) { continue }
        $manifests = Get-ChildItem -LiteralPath $steamapps -Filter "appmanifest_*.acf" -File -ErrorAction SilentlyContinue
        foreach ($m in $manifests) {
            try {
                Patch-AppManifestAutoUpdate -ManifestPath $m.FullName
                $count++
            } catch { }
        }
    }

    Log "Patched manifests: $count"
}

function Trigger-InstallOrUpdate([int]$AppId) {
    if ($AppId -le 0) { return }

    $manifest = Find-AppManifest -AppId $AppId
    if ($manifest) {
        Log "AppID $AppId seems installed (manifest found). Opening details to trigger update..."
        try { Start-Process ("steam://nav/games/details/{0}" -f $AppId) | Out-Null } catch { }
    } else {
        Log "AppID $AppId not installed. Triggering install..."
        try { Start-Process ("steam://install/{0}" -f $AppId) | Out-Null } catch { }
    }
}

# ========= MAIN FLOW =========
$token  = $null
$tmpVdf = $null
$dstVdf = Join-Path $SteamConfigDir "loginusers.vdf"

try {
    Log "=== START ==="
    Log "User=$(whoami) PcName=$PcName Service=$ServiceBaseUrl"
    Log "Logs => $LogFile"

    Ensure-SteamInstalled

    if (!(Test-Path $SteamConfigDir)) {
        Log "ERROR: Steam config dir not found: $SteamConfigDir"
        throw "Steam config dir not found: $SteamConfigDir"
    }

    # Acquire lease (poll)
    while ($true) {
        Log "Acquire lease..."
        $resp = Invoke-Json "POST" "$ServiceBaseUrl/api/v1/lease/acquire" @{
            pc_name     = $PcName
            ttl_seconds = $AcquireTtlSeconds
        }

        if ($resp.ok -eq $true -and $resp.token) {
            $token = $resp.token
            Log ("Lease acquired. account={0} expires_at={1}" -f $resp.account_name, $resp.expires_at)
            break
        }

        $wait = if ($resp.retry_after_seconds) { [int]$resp.retry_after_seconds } else { $AcquirePollSeconds }
        Log "No slots. Sleep $wait sec..."
        Start-Sleep -Seconds $wait
    }

    # Download loginusers.vdf
    $tmpVdf = Join-Path $env:TEMP ("loginusers_" + $PcName + "_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".vdf")
    Log "Downloading loginusers.vdf => $tmpVdf"
    Download-LoginUsers -Token $token -OutPath $tmpVdf
    if (!(Test-Path $tmpVdf)) { throw "loginusers download failed: $tmpVdf not found" }

    # Place loginusers into Steam config (USER MODE — без RunAs)
    Log "Placing loginusers.vdf into $dstVdf"
    Copy-Item -Force $tmpVdf $dstVdf

    # Patch manifests before starting Steam
    Patch-AllManifests

    # Start Steam with retries (if login fails)
    $successLogin = $false
    for ($attempt=1; $attempt -le $SteamStartRetries; $attempt++) {
        Log "Steam start attempt $attempt/$SteamStartRetries"
        Stop-SteamHard
        Start-Sleep -Seconds 2

        Start-Steam
        $successLogin = Wait-SteamLoginHeuristic

        if ($successLogin) { break }

        Log "Login failed/timeout. Restarting Steam..."
        Stop-SteamHard
        Start-Sleep -Seconds 3
    }

    if (-not $successLogin) {
        Log "AUTH FAILURE: login heuristic failed after retries."
        Stop-SteamHard

        if ($RemoveLoginUsersAfter -and (Test-Path $dstVdf)) {
            Log "Deleting loginusers due to auth failure: $dstVdf"
            Remove-Item -Force $dstVdf -ErrorAction SilentlyContinue
        }

        throw "Steam auth/login failed (heuristic)."
    }

    # Trigger install/update for specific AppID (optional)
    Trigger-InstallOrUpdate -AppId $TargetAppId

    # Wait downloads completion with heartbeats
    Log "Waiting downloads complete (max ${DownloadsMaxWaitSeconds}s, stable ${DownloadsStableSeconds}s)..."
    $globalSw = [Diagnostics.Stopwatch]::StartNew()
    $stableSw = [Diagnostics.Stopwatch]::StartNew()
    $stableSw.Reset()
    $stableRunning = $false

    $hbNext = (Get-Date).AddSeconds($HeartbeatSeconds)

    while ($globalSw.Elapsed.TotalSeconds -lt $DownloadsMaxWaitSeconds) {
        # heartbeat
        if ((Get-Date) -ge $hbNext) {
            try {
                Invoke-Json "POST" "$ServiceBaseUrl/api/v1/lease/heartbeat" @{
                    token       = $token
                    ttl_seconds = $AcquireTtlSeconds
                } | Out-Null
                Log "Heartbeat OK."
            } catch {
                Log "Heartbeat FAILED: $($_.Exception.Message)"
            }
            $hbNext = (Get-Date).AddSeconds($HeartbeatSeconds)
        }

        # downloads
        $active = Has-ActiveDownloads
        if ($active) {
            if ($stableRunning) {
                $stableSw.Reset()
                $stableSw.Stop()
                $stableRunning = $false
            }
            Start-Sleep -Seconds 3
            continue
        }

        if (-not $stableRunning) {
            $stableSw.Start()
            $stableRunning = $true
        }

        if ($stableSw.Elapsed.TotalSeconds -ge $DownloadsStableSeconds) {
            Log "Downloads stable-empty for ${DownloadsStableSeconds}s => done."
            break
        }

        Start-Sleep -Seconds 2
    }

    if ($globalSw.Elapsed.TotalSeconds -ge $DownloadsMaxWaitSeconds) {
        Log "WARN: downloads wait timeout reached."
    }

    # Patch manifests after updates (new manifests might appear)
    Patch-AllManifests

    # Close Steam (no logout)
    Try-SoftExitSteam -WaitSeconds 45 | Out-Null

    # Remove loginusers
    if ($RemoveLoginUsersAfter) {
        if (Test-Path $dstVdf) {
            Log "Deleting loginusers: $dstVdf"
            Remove-Item -Force $dstVdf -ErrorAction SilentlyContinue
            Log "Deleted loginusers.vdf"
        } else {
            Log "loginusers.vdf not found to delete (ok)"
        }
    }

    # Release lease
    Invoke-Json "POST" "$ServiceBaseUrl/api/v1/lease/release" @{
        token   = $token
        status  = "done"
        message = "Steam update completed (user-mode)"
    } | Out-Null
    Log "Lease released."

    # Start rds-wrtc as the SAME normal user
    if ($StartRdsWrtc) {
        if (Test-Path $RdsWrtcPath) {
            Log "Starting rds-wrtc: $RdsWrtcPath"
            Start-Process -FilePath $RdsWrtcPath | Out-Null
            Log "rds-wrtc started."
        } else {
            Log "WARN: rds-wrtc not found: $RdsWrtcPath"
        }
    }

    Log "=== SUCCESS ==="
}
catch {
    $err = $_.Exception.Message
    Log "=== ERROR === $err"

    # cleanup
    try { Stop-SteamHard } catch { }

    if ($RemoveLoginUsersAfter) {
        try {
            if (Test-Path $dstVdf) {
                Log "Cleanup: deleting loginusers: $dstVdf"
                Remove-Item -Force $dstVdf -ErrorAction SilentlyContinue
            }
        } catch { }
    }

    # release lease as error
    if ($token) {
        try {
            Invoke-Json "POST" "$ServiceBaseUrl/api/v1/lease/release" @{
                token   = $token
                status  = "error"
                message = $err
            } | Out-Null
            Log "Lease released with error."
        } catch {
            Log "Lease release failed: $($_.Exception.Message)"
        }
    }

    # start rds-wrtc even after error (as user)
    if ($StartRdsWrtc) {
        try {
            if (Test-Path $RdsWrtcPath) {
                Log "Starting rds-wrtc after error: $RdsWrtcPath"
                Start-Process -FilePath $RdsWrtcPath | Out-Null
                Log "rds-wrtc started after error."
            }
        } catch { }
    }

    throw
}
finally {
    if ($tmpVdf -and (Test-Path $tmpVdf)) {
        Remove-Item -Force $tmpVdf -ErrorAction SilentlyContinue
    }
}
