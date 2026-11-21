# Install (or update) REINS Edu on Windows and start it. In PowerShell:
#
#   irm https://raw.githubusercontent.com/Shpanier/reins-edu/main/install.ps1 | iex
#
# It puts REINS Edu in your user folder, in "REINS-Edu" (set $env:REINS_DIR for
# another folder). Run the same line again later to update: your settings (.env),
# your database (reins.db) and your exercises (data\) are kept.
$ErrorActionPreference = "Stop"
# Windows PowerShell 5.1 downloads many times slower while it draws a progress bar.
$ProgressPreference = "SilentlyContinue"
$repo = if ($env:REINS_REPO) { $env:REINS_REPO } else { "https://github.com/Shpanier/reins-edu" }
$branch = if ($env:REINS_BRANCH) { $env:REINS_BRANCH } else { "main" }
$dir = if ($env:REINS_DIR) { $env:REINS_DIR } else { Join-Path $HOME "REINS-Edu" }

if ((Test-Path (Join-Path $dir ".git")) -and (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "==> Updating REINS Edu in $dir"
    git -C $dir pull --ff-only
} else {
    Write-Host "==> Downloading REINS Edu to $dir"
    $zip = Join-Path $env:TEMP "reins-edu-$branch.zip"
    $tmp = Join-Path $env:TEMP "reins-unpack"
    Invoke-WebRequest "$repo/archive/refs/heads/$branch.zip" -OutFile $zip -UseBasicParsing
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    Expand-Archive $zip -DestinationPath $tmp
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    # Only the files of the release are written: .env, reins.db and data\ stay.
    Copy-Item -Path (Join-Path (Get-ChildItem $tmp | Select-Object -First 1).FullName "*") -Destination $dir -Recurse -Force
    Remove-Item $zip, $tmp -Recurse -Force
}
Write-Host "==> Starting. Next time: double-click start.bat in $dir"
& (Join-Path $dir "start.bat") @args
