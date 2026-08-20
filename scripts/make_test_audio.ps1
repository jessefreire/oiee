$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech

$out = Join-Path $env:TEMP 'flow_test.wav'
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice('Microsoft Maria Desktop')
$s.SetOutputToWaveFile($out)
$s.Speak('Olá mundo. Este é um teste de ditado por voz.')
$s.Dispose()
Write-Output "WAV criado: $out"
