param([int]$Wait=8)
Start-Sleep -Seconds $Wait
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Enum {
    public delegate bool EnumWindowsProc(IntPtr h, IntPtr lp);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lp);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
}
"@
$names = @()
$cb = [Win32Enum+EnumWindowsProc]{
    param($h, $lp)
    if ([Win32Enum]::IsWindowVisible($h)) {
        $sb = New-Object System.Text.StringBuilder 256
        [Win32Enum]::GetWindowText($h, $sb, 256) | Out-Null
        $t = $sb.ToString()
        if ($t -match 'TkTopLevel|ctk') { $global:names += "$h -> $t" }
    }
    return $true
}
[Win32Enum]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
if ($names.Count -gt 0) {
    Write-Output "JANELAS VISIVEIS: $($names.Count)"
    foreach ($n in $names) { Write-Output "  $n" }
} else {
    Write-Output "NENHUMA janela TkTopLevel visivel"
}
