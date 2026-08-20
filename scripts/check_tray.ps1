# Verifica se o Oiee esta rodando e se algum processo criou a janela
# do icone da bandeja (pystray). ASCII-only para PS 5.1.
$procs = Get-Process Oiee -ErrorAction SilentlyContinue
if (-not $procs) {
    Write-Output "ERRO: processo Oiee nao encontrado"
    exit 1
}
foreach ($proc in $procs) {
    Write-Output ("Processo PID {0}, memoria {1} MB" -f $proc.Id, [math]::Round($proc.WorkingSet64 / 1MB))
}

Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public class WinEnum3 {
    public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr lParam);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
    [DllImport("user32.dll")] public static extern int GetClassName(IntPtr hWnd, StringBuilder sb, int max);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
}
"@

$ids = @($procs | ForEach-Object { $_.Id })
$list = [System.Collections.Generic.List[string]]::new()
$cb = [WinEnum3+EnumProc]{
    param($h, $l)
    [uint32]$procId = 0
    [WinEnum3]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
    if ($ids -contains $procId) {
        $sb = [System.Text.StringBuilder]::new(256)
        [WinEnum3]::GetClassName($h, $sb, 256) | Out-Null
        $vis = [WinEnum3]::IsWindowVisible($h)
        $list.Add("PID=$procId classe=$($sb.ToString()) visivel=$vis")
    }
    return $true
}
[WinEnum3]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null

if ($list.Count -eq 0) {
    Write-Output "ERRO: nenhuma janela do processo - o icone da bandeja nao foi criado"
    exit 1
}
$list | ForEach-Object { Write-Output "janela: $_" }
if (($list -join ' ') -match "SystemTrayIcon|pystray|NotifyIcon") {
    Write-Output "OK: janela do icone da bandeja encontrada"
} else {
    Write-Output "AVISO: ha janelas, mas nenhuma com classe de bandeja obvia"
}
