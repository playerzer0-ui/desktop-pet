# Builds the Windows game: dist\DesktopPet\DesktopPet.exe (a folder, run it from there), and the same folder zipped
# as dist\DesktopPet-windows.zip (what goes on itch.io). Run it after setup.bat has worked once:
#     powershell -ExecutionPolicy Bypass -File build.ps1
# Steps:
#   1. PyInstaller, into the project's own Python (.venv)
#   2. llama-server's files, copied from the one setup.bat installed (only what the game needs)
#   3. the icon, made from Pip's happy sprite
#   4. the build itself (DesktopPet.spec)
#   5. the licenses: THIRD_PARTY_NOTICES.txt and licenses\ in the build (build_notices.py)
#   6. the zip
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Run setup.bat first (there's no .venv yet)." }

Write-Host "1/6  PyInstaller" -ForegroundColor Cyan
& $python -m pip install --disable-pip-version-check --quiet pyinstaller
if ($LASTEXITCODE -ne 0) { throw "Couldn't install PyInstaller." }

Write-Host "2/6  llama-server" -ForegroundColor Cyan
$found = & $python -c "import server; print(server.find_llama_server())"
if ($LASTEXITCODE -ne 0) { throw "Can't find llama-server: run setup.bat first." }
$from = Split-Path $found
$to = Join-Path $PSScriptRoot "build\llama-server"
if ((Resolve-Path $from).Path -eq (Join-Path $PSScriptRoot "server")) { throw "llama-server was found in server\; the build copies it from setup's install instead." }
Remove-Item $to -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $to | Out-Null
# the server and what it loads; not the other llama.cpp tools, and not the GPU (Vulkan) backend: the game runs the
# model on the CPU (-ngl 0), and leaving it out saves 41 MB and any trouble with players' GPU drivers
$skip = "ggml-vulkan.dll", "ggml-rpc.dll"
Get-ChildItem $from -File | Where-Object {
    ($_.Name -eq "llama-server.exe" -or $_.Name -eq "llama-server-impl.dll" -or
     ($_.Extension -eq ".dll" -and $_.Name -notlike "*-impl.dll") -or $_.Name -like "LICENSE*") -and $skip -notcontains $_.Name
} | Copy-Item -Destination $to
Write-Host ("     " + (Get-ChildItem $to).Count + " files from $from")

Write-Host "3/6  The icon" -ForegroundColor Cyan
& $python -c @"
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtCore import Qt
app = QGuiApplication([])
img = QImage('character/pip/sprites/happy.png').scaled(256, 256, Qt.KeepAspectRatio, Qt.FastTransformation)
assert img.save('build/icon.ico'), 'could not write build/icon.ico'
"@
if ($LASTEXITCODE -ne 0) { throw "Couldn't make the icon." }

Write-Host "4/6  Building (a minute or two)" -ForegroundColor Cyan
& $python -m PyInstaller DesktopPet.spec --noconfirm --clean --distpath dist --workpath build\pyinstaller --log-level WARN
if ($LASTEXITCODE -ne 0) { throw "The build failed (see above)." }

Write-Host "5/6  Licenses" -ForegroundColor Cyan
& $python build_notices.py (Join-Path $PSScriptRoot "dist\DesktopPet")
if ($LASTEXITCODE -ne 0) { throw "Couldn't write the licenses." }

Write-Host "6/6  The zip" -ForegroundColor Cyan
$zip = Join-Path $PSScriptRoot "dist\DesktopPet-windows.zip"
Remove-Item $zip -ErrorAction SilentlyContinue
# (Python's zip, with a few tries: Windows Defender keeps freshly built files locked for a moment while it scans them)
& $python -c @"
import shutil, time
for attempt in range(6):
    try:
        shutil.make_archive('dist/DesktopPet-windows', 'zip', 'dist', 'DesktopPet')
        break
    except PermissionError:
        if attempt == 5:
            raise
        time.sleep(5)
"@
if ($LASTEXITCODE -ne 0) { throw "Couldn't make the zip." }
$size = (Get-ChildItem (Join-Path $PSScriptRoot "dist\DesktopPet") -Recurse | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("Done: dist\DesktopPet\DesktopPet.exe ({0:N0} MB), and {1} ({2:N0} MB)" -f $size, $zip, ((Get-Item $zip).Length / 1MB)) -ForegroundColor Green
