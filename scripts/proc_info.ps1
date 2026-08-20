$procs = Get-Process Oiee -ErrorAction SilentlyContinue
if (-not $procs) { Write-Output "nenhum Oiee rodando"; exit 0 }
foreach ($p in $procs) {
    $mb = [math]::Round($p.WorkingSet64 / 1MB)
    Write-Output ("PID {0}  inicio {1}  {2} MB  path={3}" -f $p.Id, $p.StartTime.ToString('HH:mm:ss'), $mb, $p.Path)
}
