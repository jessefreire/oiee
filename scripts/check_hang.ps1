# Verifica se a janela da bolha flutuante responde a mensagens (thread da UI viva?).
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class HangCheck {
    [DllImport("user32.dll", SetLastError=true)]
    public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint msg, UIntPtr wParam, IntPtr lParam,
        uint flags, uint timeout, out UIntPtr result);
    [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr hWnd);
}
"@
$proc = Get-Process Oiee -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc) { Write-Output "ERRO: Oiee nao rodando"; exit 1 }

$found = $false
$procs = @(Get-Process Oiee -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class WinEnum4 {
    public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr lParam);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
    [DllImport("user32.dll")] public static extern int GetClassName(IntPtr hWnd, StringBuilder sb, int max);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
}
"@
$list = [System.Collections.Generic.List[object]]::new()
$cb = [WinEnum4+EnumProc]{
    param($h, $l)
    [uint32]$procId = 0
    [WinEnum4]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
    if ($procs -contains $procId) {
        $sb = [System.Text.StringBuilder]::new(256)
        [WinEnum4]::GetClassName($h, $sb, 256) | Out-Null
        if ([WinEnum4]::IsWindowVisible($h)) {
            $list.Add([pscustomobject]@{ Hwnd = $h; Class = $sb.ToString() })
        }
    }
    return $true
}
[WinEnum4]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null

foreach ($w in $list) {
    [UIntPtr]$res = [UIntPtr]::Zero
    $ok = [HangCheck]::SendMessageTimeout($w.Hwnd, 0x0000, [UIntPtr]::Zero, [IntPtr]::Zero, 0x0002, 2000, [ref]$res)
    $state = if ($ok -ne [IntPtr]::Zero) { "RESPONDE" } else { "TRAVADA (timeout)" }
    Write-Output ("janela {0} classe={1} -> {2}" -f $w.Hwnd, $w.Class, $state)
}
if ($list.Count -eq 0) { Write-Output "nenhuma janela visivel do processo" }
