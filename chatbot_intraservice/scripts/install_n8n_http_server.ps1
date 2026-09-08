# Локальный HTTP API для n8n (ноутбук). Запуск при входе в Windows.
#   powershell -ExecutionPolicy Bypass -File scripts\install_n8n_http_server.ps1
#
# После установки обновите workflow (IP ноутбука мог смениться):
#   python scripts\n8n_setup_helpdesk_watch.py --bot-url http://<ваш-ip>:8765

param(
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
    $venvPyw = Join-Path (Split-Path -Parent $Root) ".venv\Scripts\pythonw.exe"
    if (Test-Path $venvPyw) { $Python = $venvPyw }
    else { $Python = (Get-Command pythonw -ErrorAction SilentlyContinue).Source }
    if (-not $Python) { $Python = (Get-Command python).Source }
}

$scriptPath = Join-Path $Root "scripts\n8n_http_server.py"
$arg = "`"$scriptPath`" --host 0.0.0.0 --port 8765"
$action = New-ScheduledTaskAction -Execute $Python -Argument $arg -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew -Hidden `
    -ExecutionTimeLimit (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName "IEK-IntraService-N8nHttp" -Action $action -Trigger $trigger `
    -Settings $settings -Description "n8n HTTP API :8765 for HelpDesk bot" -Force | Out-Null
Write-Host "OK IEK-IntraService-N8nHttp at logon -> $Python $arg"

# Firewall (нужны права администратора)
$ruleName = "IEK n8n_http_server 8765"
$existing = netsh advfirewall firewall show rule name="$ruleName" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Firewall: запустите от администратора:"
    Write-Host "  netsh advfirewall firewall add rule name=`"$ruleName`" dir=in action=allow protocol=TCP localport=8765"
}

# Текущий IP и обновление workflow
$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' -and $_.IPAddress -notlike '169.254.*'
} | Select-Object -First 1).IPAddress
if ($ip) {
    Write-Host ""
    Write-Host "LAN IP: $ip"
    Write-Host "Обновить n8n workflow:"
    Write-Host "  python scripts\n8n_setup_helpdesk_watch.py --bot-url http://${ip}:8765"
}
