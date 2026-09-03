# Gera dist/Oiee/Oiee.exe (inicialização rápida, sem console)
# Uso: powershell -ExecutionPolicy Bypass -File build_exe.ps1
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$py = Join-Path $root '.venv-build\Scripts\python.exe'

if (-not (Test-Path $py)) {
    throw "Ambiente de build ausente. Crie com: py -3.11 -m venv .venv-build"
}

# O PyInstaller procura dependências nativas em PATH. Ambientes de automação
# podem acrescentar Poppler/libheif e fazer DLLs alheias (ICU, OpenSSL e runtime
# C++) entrarem no Oiee, quebrando o Qt com "procedimento não encontrado".
$buildPathEntries = $env:Path -split ';' | Where-Object {
    $_ -and $_ -notlike '*\.cache\codex-runtimes\*'
}
$env:Path = $buildPathEntries -join ';'

& $py -m PyInstaller --noconfirm --clean --onedir --windowed --name Oiee `
    --icon (Join-Path $root 'assets\icon.ico') `
    --collect-all ctranslate2 `
    --collect-all tokenizers `
    --collect-all av `
    --collect-submodules faster_whisper `
    --collect-data faster_whisper `
    (Join-Path $root 'main.py')

Write-Host "OK: dist\Oiee\Oiee.exe"
