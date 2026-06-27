param(
    [string]$Python = "python",
    [string]$Version = "",
    [switch]$NoZip
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$SpecPath = Join-Path $RepoRoot "packaging\ve-analyse-portable.spec"
$DistRoot = Join-Path $RepoRoot "dist"
$PortableDir = Join-Path $DistRoot "VE-Analyse-Portable"

Push-Location $RepoRoot
try {
    & $Python -m PyInstaller --version | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller is not available."
    }

    & $Python -m PyInstaller $SpecPath --noconfirm --clean
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed."
    }

    $ReadmePath = Join-Path $PortableDir "README.txt"
    @"
VE Analyse Portable

Run:
  VE Analyse.exe

The app starts a local web UI and opens it in your default browser.
State is stored in:
  data\state.json

No installation or administrator rights are required.
Close the VE Analyse console window to stop the local web UI.
"@ | Set-Content -Path $ReadmePath -Encoding UTF8

    if (-not $NoZip) {
        $Suffix = if ($Version) { "-$Version" } else { "" }
        $ZipPath = Join-Path $DistRoot "VE-Analyse-Portable$Suffix.zip"
        if (Test-Path $ZipPath) {
            Remove-Item -LiteralPath $ZipPath -Force
        }
        $Compressed = $false
        for ($Attempt = 1; $Attempt -le 5; $Attempt++) {
            try {
                Compress-Archive -Path $PortableDir -DestinationPath $ZipPath -Force
                $Compressed = $true
                break
            }
            catch {
                if ($Attempt -eq 5) {
                    throw
                }
                Start-Sleep -Seconds 2
            }
        }
        if (-not $Compressed) {
            throw "Portable zip could not be created."
        }
        Write-Host "Portable zip created: $ZipPath"
    }

    Write-Host "Portable folder created: $PortableDir"
}
catch {
    Write-Error $_
    Write-Host ""
    Write-Host "Install PyInstaller, then rerun this script:"
    Write-Host "  $Python -m pip install pyinstaller"
    exit 1
}
finally {
    Pop-Location
}
