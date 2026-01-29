"""
File generation service for OBS profiles and PowerShell scripts.
"""
import io
import zipfile
from typing import BinaryIO

from app.core.config import settings
from app.models.pc import PC
from app.models.user import User


class FileGeneratorService:
    """Service for generating downloadable configuration files."""

    def generate_obs_profile(self, pc: PC, user: User) -> BinaryIO:
        """
        Generate OBS Studio profile as ZIP archive.

        Args:
            pc: PC configuration
            user: User owner

        Returns:
            Binary IO with ZIP content
        """
        buffer = io.BytesIO()

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # Basic profile info
            basic_ini = self._generate_basic_ini(pc)
            zf.writestr("basic.ini", basic_ini)

            # Stream settings
            stream_ini = self._generate_stream_ini(pc)
            zf.writestr("streamEncoder.json", stream_ini)

            # Service configuration
            service_json = self._generate_service_json(pc)
            zf.writestr("service.json", service_json)

            # README
            readme = self._generate_profile_readme(pc, user)
            zf.writestr("README.txt", readme)

        buffer.seek(0)
        return buffer

    def _generate_basic_ini(self, pc: PC) -> str:
        """Generate basic.ini content."""
        return f"""[General]
Name=OBS Fog - {pc.name}

[Video]
BaseCX=1920
BaseCY=1080
OutputCX=1920
OutputCY=1080
FPSType=1
FPSNum=30
FPSDen=1

[Audio]
SampleRate=44100
ChannelSetup=2
"""

    def _generate_stream_ini(self, pc: PC) -> str:
        """Generate stream encoder settings."""
        return """{
    "encoder": "obs_x264",
    "settings": {
        "bitrate": 4500,
        "keyint_sec": 2,
        "preset": "veryfast",
        "profile": "main",
        "tune": "zerolatency"
    }
}"""

    def _generate_service_json(self, pc: PC) -> str:
        """Generate service.json with RTMP settings."""
        rtmp_url = settings.rtmp_url
        return f"""{{
    "settings": {{
        "server": "{rtmp_url}",
        "key": "{pc.stream_key}",
        "use_auth": false
    }},
    "type": "rtmp_custom"
}}"""

    def _generate_profile_readme(self, pc: PC, user: User) -> str:
        """Generate README for profile."""
        return f"""OBS Fog Server - Profile Configuration
======================================

PC Name: {pc.name}
User: {user.email}

RTMP Server: {settings.rtmp_url}
Stream Key: {pc.stream_key}

Installation:
1. Copy this folder to your OBS profiles directory:
   Windows: %APPDATA%\\obs-studio\\basic\\profiles\\
   Linux: ~/.config/obs-studio/basic/profiles/

2. Restart OBS Studio

3. Select profile "{pc.name}" from Profile menu

Note: Keep your stream key secret! Do not share it.
"""

    def generate_steamslot_ps1(
        self,
        pc: PC,
        user: User,
        api_key: str,
    ) -> str:
        """
        Generate PowerShell script for Steam Slot setup.

        Args:
            pc: PC configuration
            user: User owner
            api_key: API key for authentication

        Returns:
            PowerShell script content
        """
        base_url = settings.app_base_url

        return f'''# OBS Fog Server - Steam Slot Setup Script
# PC: {pc.name}
# User: {user.email}
# Generated: (timestamp auto-generated)
#
# This script uses a PC-bound token for authentication.
# The token is valid for 1 year and is tied to this specific PC.

$ErrorActionPreference = "Stop"

# Configuration
$ApiBaseUrl = "{base_url}/api/v1/steamslot"
$PcToken = "{api_key}"

# Headers with PC-bound token
$Headers = @{{
    "Authorization" = "Bearer $PcToken"
    "Content-Type" = "application/json"
}}

function Get-ActiveLease {{
    Write-Host "Checking for active lease..." -ForegroundColor Cyan

    try {{
        $response = Invoke-RestMethod -Uri "$ApiBaseUrl/script/active-lease" `
            -Method GET -Headers $Headers

        if ($response) {{
            Write-Host "Active lease found!" -ForegroundColor Green
            return $response
        }}
    }} catch {{
        if ($_.Exception.Response.StatusCode -ne 404) {{
            Write-Host "Error checking lease: $($_.Exception.Message)" -ForegroundColor Yellow
        }}
    }}

    Write-Host "No active lease found." -ForegroundColor Yellow
    return $null
}}

function Request-NewLease {{
    Write-Host "Requesting new lease..." -ForegroundColor Cyan

    try {{
        $response = Invoke-RestMethod -Uri "$ApiBaseUrl/script/lease?duration_hours=24" `
            -Method POST -Headers $Headers

        Write-Host "Lease acquired!" -ForegroundColor Green
        return $response
    }} catch {{
        Write-Host "Failed to acquire lease: $($_.Exception.Message)" -ForegroundColor Red
        return $null
    }}
}}

function Download-SteamFiles {{
    param([string]$Token)

    Write-Host "Downloading Steam files..." -ForegroundColor Cyan

    $downloadUrl = "$ApiBaseUrl/leases/download?token=$Token"
    $outputPath = "$env:TEMP\\steam_files.zip"

    try {{
        Invoke-WebRequest -Uri $downloadUrl -OutFile $outputPath

        # Extract to Steam directory
        $steamPath = "$env:ProgramFiles(x86)\\Steam"
        if (Test-Path $steamPath) {{
            Expand-Archive -Path $outputPath -DestinationPath $steamPath -Force
            Write-Host "Files extracted to Steam directory!" -ForegroundColor Green
        }} else {{
            Write-Host "Steam not found at default location." -ForegroundColor Yellow
            Write-Host "Please extract $outputPath manually." -ForegroundColor Yellow
        }}

        Remove-Item $outputPath -Force
    }} catch {{
        Write-Host "Failed to download files: $($_.Exception.Message)" -ForegroundColor Red
    }}
}}

# Main execution
Write-Host "=== OBS Fog Server - Steam Slot Setup ===" -ForegroundColor Magenta
Write-Host "PC: {pc.name}" -ForegroundColor Gray
Write-Host ""

$lease = Get-ActiveLease

if (-not $lease) {{
    $lease = Request-NewLease
}}

if ($lease) {{
    Write-Host ""
    Write-Host "Lease Details:" -ForegroundColor Cyan
    Write-Host "  Account: $($lease.account_name)"
    Write-Host "  Expires: $($lease.expires_at)"
    Write-Host ""

    Download-SteamFiles -Token $lease.token
}}

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Read-Host "Press Enter to exit"
'''

    def generate_obs_installer_ps1(self, pc: PC, user: User) -> str:
        """
        Generate PowerShell script for complete OBS setup.

        Args:
            pc: PC configuration
            user: User owner

        Returns:
            PowerShell script content
        """
        base_url = settings.app_base_url

        return f'''# OBS Fog Server - Complete Setup Script
# PC: {pc.name}
# User: {user.email}

$ErrorActionPreference = "Stop"

Write-Host "=== OBS Fog Server Setup ===" -ForegroundColor Magenta
Write-Host ""

# Check if OBS is installed
$obsPath = "$env:ProgramFiles\\obs-studio"
if (-not (Test-Path $obsPath)) {{
    $obsPath = "$env:ProgramFiles(x86)\\obs-studio"
}}

if (-not (Test-Path $obsPath)) {{
    Write-Host "OBS Studio not found. Installing..." -ForegroundColor Yellow

    # Download and install OBS
    $obsInstaller = "$env:TEMP\\obs-installer.exe"
    $obsUrl = "https://cdn-fastly.obsproject.com/downloads/OBS-Studio-30.0.2-Full-Installer-x64.exe"

    Write-Host "Downloading OBS Studio..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $obsUrl -OutFile $obsInstaller

    Write-Host "Installing OBS Studio..." -ForegroundColor Cyan
    Start-Process -FilePath $obsInstaller -Args "/S" -Wait

    Remove-Item $obsInstaller -Force
    Write-Host "OBS Studio installed!" -ForegroundColor Green
}}

# Download profile
Write-Host ""
Write-Host "Downloading OBS profile..." -ForegroundColor Cyan

$profileUrl = "{base_url}/api/v1/downloads/obs-profile/{pc.id}"
$profileZip = "$env:TEMP\\obs_profile.zip"
$profileDir = "$env:APPDATA\\obs-studio\\basic\\profiles\\OBS_Fog_{pc.name}"

try {{
    # You'll need to add authentication token here
    Invoke-WebRequest -Uri $profileUrl -OutFile $profileZip

    # Create profile directory
    if (-not (Test-Path $profileDir)) {{
        New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
    }}

    # Extract profile
    Expand-Archive -Path $profileZip -DestinationPath $profileDir -Force

    Remove-Item $profileZip -Force

    Write-Host "Profile installed!" -ForegroundColor Green
}} catch {{
    Write-Host "Failed to download profile: $($_.Exception.Message)" -ForegroundColor Red
}}

# Display stream settings
Write-Host ""
Write-Host "=== Stream Settings ===" -ForegroundColor Cyan
Write-Host "RTMP URL: {settings.rtmp_url}"
Write-Host "Stream Key: {pc.stream_key}"
Write-Host ""
Write-Host "Keep your stream key secret!" -ForegroundColor Yellow
Write-Host ""

Write-Host "Setup complete!" -ForegroundColor Green
Read-Host "Press Enter to exit"
'''
