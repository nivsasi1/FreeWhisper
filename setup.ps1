# FreeWhisper one-time setup. Run from the project folder:  .\setup.ps1
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Write-Host "== FreeWhisper setup ==" -ForegroundColor Cyan

# 1. virtual environment + Python deps
if (-not (Test-Path "$root\.venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv "$root\.venv"
}
$py  = "$root\.venv\Scripts\python.exe"
$pip = "$root\.venv\Scripts\pip.exe"
& $py -m pip install --quiet --upgrade pip
Write-Host "Installing dependencies (this can take a few minutes)..."
& $pip install --quiet -r "$root\requirements.txt"

# 2. NVIDIA GPU runtime (cuBLAS/cuDNN) — needed for faster-whisper on GPU
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    Write-Host "NVIDIA GPU detected — installing CUDA runtime wheels..."
    & $pip install --quiet nvidia-cublas-cu12 nvidia-cudnn-cu12
} else {
    Write-Host "No NVIDIA GPU found — will run on CPU (set device: cpu, compute_type: int8 in config.yaml)." -ForegroundColor Yellow
}

# 3. Ollama cleanup model
$ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if (-not $ollama) { $ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" }
if (Test-Path $ollama) {
    Write-Host "Pulling Ollama model gemma3:12b..."
    & $ollama pull gemma3:12b
} else {
    Write-Host "Ollama not installed. Install it (winget install Ollama.Ollama), then: ollama pull gemma3:12b" -ForegroundColor Yellow
}

# 4. shortcuts (desktop + run at login)
$ws = New-Object -ComObject WScript.Shell
foreach ($dest in @("$([Environment]::GetFolderPath('Desktop'))\FreeWhisper.lnk",
                    "$([Environment]::GetFolderPath('Startup'))\FreeWhisper.lnk")) {
    $s = $ws.CreateShortcut($dest)
    $s.TargetPath = "$root\.venv\Scripts\pythonw.exe"
    $s.Arguments = "-m freewhisper"
    $s.WorkingDirectory = $root
    if (Test-Path "$root\freewhisper.ico") { $s.IconLocation = "$root\freewhisper.ico" }
    $s.Save()
}

Write-Host "`nDone. Verify with:" -ForegroundColor Green
Write-Host "  .venv\Scripts\python -m freewhisper --check"
Write-Host "Then launch with the FreeWhisper desktop icon (or that command without --check)."
