# Gera dist/Oiee.exe (portátil, janela única, sem console)
# Uso: powershell -ExecutionPolicy Bypass -File build_exe.ps1
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'

& $py -m PyInstaller --noconfirm --clean --onefile --windowed --name Oiee `
    --icon (Join-Path $root 'assets\icon.ico') `
    --collect-all customtkinter `
    --collect-all ctranslate2 `
    --collect-all tokenizers `
    --collect-all av `
    --collect-all PySide6 `
    --collect-submodules faster_whisper `
    --collect-data faster_whisper `
    (Join-Path $root 'main.py')

Write-Host "OK: dist\Oiee.exe"
