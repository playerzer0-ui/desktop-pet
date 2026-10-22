<#
Sets up the desktop pet on a Windows machine. Double-click setup.bat to run it.
Safe to run again: every step skips what is already done.

  1. Python 3.11 or newer   installs Python 3.13 with winget if there is none
  2. .venv and packages     the project's own Python, with requirements.txt
  3. llama-server           installs it with winget, unless server.py can already find one
  4. the model              downloads config.MODEL_URL into models\ and checks its SHA-256
  5. a quick check          the mood lists and the tests (no model needed)

Then start her with start.bat.
(Kept to plain ASCII: Windows PowerShell 5.1 misreads other characters in a script file.)
#>
Set-Location $PSScriptRoot
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

function Step($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Yellow }
function Ok($text) { Write-Host "   $text" -ForegroundColor Green }
function Note($text) { Write-Host "   $text" }
function Fail($text) { Write-Host "   $text" -ForegroundColor Red; exit 1 }

function Update-PathFromSystem {
    # a winget install changes PATH for new windows only: read it again for this one
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}

function Find-Python {
    # The py launcher first (it knows every installed version), then plain "python".
    # The Microsoft Store's "python" placeholder fails the version check, so it's skipped.
    foreach ($candidate in @("py -3", "python")) {
        $parts = $candidate.Split(" ")
        if (-not (Get-Command $parts[0] -ErrorAction SilentlyContinue)) { continue }
        & $parts[0] @($parts | Select-Object -Skip 1) -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { return $candidate }
    }
    return $null
}

function Install-WithWinget($id, $what) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Fail "winget isn't available, so $what can't be installed automatically. Install it by hand, then run this again."
    }
    Note "Installing $what with winget (it may ask you to accept its terms)..."
    winget install -e --id $id
    Update-PathFromSystem
}

# --- 1. Python ---
Step "1/5  Python 3.11 or newer"
if (Test-Path $venvPython) {
    Ok "already set up (.venv)"
} else {
    $python = Find-Python
    if (-not $python) {
        Install-WithWinget "Python.Python.3.13" "Python 3.13"
        $python = Find-Python
        if (-not $python) { Fail "Python was installed, but this window can't see it yet. Close it and run setup.bat again." }
    }
    Ok "found: $python"
}

# --- 2. .venv and packages ---
Step "2/5  The project's Python (.venv) and its packages"
if (-not (Test-Path $venvPython)) {
    $parts = $python.Split(" ")
    & $parts[0] @($parts | Select-Object -Skip 1) -m venv .venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) { Fail "Couldn't create .venv." }
    Ok "created .venv"
}
& $venvPython -m pip install --disable-pip-version-check --quiet -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail "Installing requirements.txt failed (see above)." }
Ok "packages installed"

# --- 3. llama-server ---
Step "3/5  llama-server (runs the model)"
$findServer = "import server; print(server.find_llama_server())"  # the same search the pet uses
$found = & $venvPython -c $findServer 2>$null
if ($LASTEXITCODE -ne 0) {
    Install-WithWinget "ggml.llamacpp" "llama-server (llama.cpp)"
    $found = & $venvPython -c $findServer 2>$null
    if ($LASTEXITCODE -ne 0) { Fail "llama-server was installed, but can't be found yet. Close this window and run setup.bat again." }
}
Ok "found: $found"

# --- 4. the model ---
Step "4/5  The model"
$model = & $venvPython -c "import config, json; print(json.dumps({'path': config.MODEL, 'url': config.MODEL_URL, 'sha256': config.MODEL_SHA256}))" | ConvertFrom-Json
if (-not $model) { Fail "Couldn't read MODEL, MODEL_URL and MODEL_SHA256 from config.py." }
$name = Split-Path $model.path -Leaf

function Test-ModelFile($path) {
    Note "Checking $(Split-Path $path -Leaf) (takes a little while for a few GB)..."
    return (Get-FileHash -Algorithm SHA256 $path).Hash -ieq $model.sha256
}

if ((Test-Path $model.path) -and (Test-ModelFile $model.path)) {
    Ok "$name is already here and intact"
} else {
    if (Test-Path $model.path) {
        Note "$name is there but doesn't match its checksum (incomplete or a different file): downloading it again."
        Remove-Item $model.path
    }
    New-Item -ItemType Directory -Force (Split-Path $model.path) | Out-Null
    $drive = Get-PSDrive -Name (Split-Path $model.path -Qualifier).TrimEnd(":")
    if ($drive.Free -lt 4GB) { Fail ("Not enough free space on {0}: (about 4 GB needed, {1:N1} GB free)." -f $drive.Name, ($drive.Free / 1GB)) }
    $part = $model.path + ".part"
    Note "Downloading $name from $($model.url)"
    Note "(If it stops, run setup.bat again: it carries on where it left off.)"
    curl.exe --location --fail --continue-at - --progress-bar --output $part $model.url
    if ($LASTEXITCODE -ne 0) { Fail "The download stopped (curl exit code $LASTEXITCODE). Run setup.bat again to carry on." }
    if (-not (Test-ModelFile $part)) {
        Remove-Item $part
        Fail "The downloaded file doesn't match its checksum, so it was deleted. Run setup.bat again."
    }
    Move-Item -Force $part $model.path
    Ok "$name downloaded and checked"
}

# --- 5. a quick check ---
Step "5/5  A quick check"
& $venvPython -m desktop.check
if ($LASTEXITCODE -ne 0) { Fail "The character's files don't agree (see above)." }
# (cmd merges the tests' two output streams: Windows PowerShell would show stderr lines as error objects)
$testOutput = @(cmd /c "`"$venvPython`" -m unittest discover -s tests 2>&1")
$testsPassed = ($LASTEXITCODE -eq 0)
$ran = $testOutput | Where-Object { $_ -match "^Ran \d+ tests?" } | Select-Object -Last 1
if ($testsPassed) {
    Ok "${ran}: all passed"
} else {
    # unittest lists each problem as "FAIL: <test> (...)" (a check came out wrong) or "ERROR: <test> (...)"
    # (the test crashed), then a traceback whose last line is the error itself. Our tests write that line to say
    # what's wrong and how to fix it, so it's the line worth showing.
    $failed = 0
    for ($i = 0; $i -lt $testOutput.Count; $i++) {
        if ($testOutput[$i] -notmatch "^(FAIL|ERROR): (\S+)") { continue }
        $kind, $test = $Matches[1], $Matches[2]
        $why = ""
        for ($j = $i + 2; $j -lt $testOutput.Count -and $testOutput[$j] -notmatch "^(=+|-+)$"; $j++) {
            if ($testOutput[$j].Trim()) { $why = $testOutput[$j].Trim() }
        }
        $why = $why -replace "^AssertionError: ", ""
        if ($why -match "^.+ : (.+)$") { $why = $Matches[1] }  # "10 != 240 : Pip's daily_minutes is..." -> the sentence
        $failed++
        Write-Host ""
        Write-Host ("   {0}  {1}" -f $(if ($kind -eq "FAIL") { "Failed " } else { "Crashed" }), $test) -ForegroundColor Red
        Note "         $why"
    }
    Write-Host ""
    Write-Host "   ${ran}: $failed failed (above). Each line under a test's name says what went wrong." -ForegroundColor Red
    Note "The pet may still run. For the full details: .venv\Scripts\python -m unittest discover -s tests"
}

Write-Host ""
if ($testsPassed) {
    Write-Host "All set. Start her with start.bat (or: .venv\Scripts\python main.py)." -ForegroundColor Green
} else {
    Write-Host "Set up, but with the test problems above. You can still try start.bat." -ForegroundColor Yellow
}
