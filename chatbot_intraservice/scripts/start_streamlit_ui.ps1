# Register + start Streamlit UI task (current user, AtLogOn).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$py = Join-Path (Split-Path -Parent $Root) ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = (Get-Command python).Source }
$app = Join-Path $Root "app.py"
$stArgs = "-m streamlit run `"$app`" --server.headless true --server.port 8502 --browser.gatherUsageStats false"

$action = New-ScheduledTaskAction -Execute $py -Argument $stArgs -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew -Hidden
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Unregister-ScheduledTask -TaskName "IEK-IntraService-StreamlitUI" -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName "IEK-IntraService-StreamlitUI" -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Local Streamlit UI chatbot on port 8502" -Force | Out-Null
Write-Host "OK registered IEK-IntraService-StreamlitUI"

# Start now if port free
$listen = Get-NetTCPConnection -LocalPort 8502 -State Listen -ErrorAction SilentlyContinue
if ($listen) {
    Write-Host "Port 8502 already listening (PID $($listen.OwningProcess))"
} else {
    Write-Host "Starting Streamlit now..."
    Start-Process -FilePath $py -ArgumentList $stArgs -WorkingDirectory $Root -WindowStyle Hidden
    Start-Sleep -Seconds 5
}
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8502/" -UseBasicParsing -TimeoutSec 15
    Write-Host "HTTP $($r.StatusCode) localhost:8502 OK"
} catch {
    Write-Host "HTTP check: $($_.Exception.Message)"
}
Get-ScheduledTask -TaskName "IEK-IntraService-*" | Select-Object TaskName, State | Format-Table -AutoSize
