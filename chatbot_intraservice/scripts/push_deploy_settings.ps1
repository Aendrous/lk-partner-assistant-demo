# Скопировать настройки Streamlit на сервер выполнения (n8n).
# Streamlit на ноутбуке пишет config/settings.local.json;
# watch_* на сервере читают тот же файл из каталога пакета.

param(
    [string]$DeployHost = $env:N8N_BOT_DEPLOY_HOST,
    [string]$RemotePath = $(if ($env:N8N_BOT_DEPLOY_PATH) { $env:N8N_BOT_DEPLOY_PATH } else { "/opt/iek-chatbot-intraservice" }),
    [string]$LocalSettings = "config/settings.local.json"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$src = Join-Path $root $LocalSettings

if (-not $DeployHost) {
    Write-Host "Задайте хост: -DeployHost n8n.iek.local или env N8N_BOT_DEPLOY_HOST"
    exit 1
}
if (-not (Test-Path $src)) {
    Write-Host "Нет файла $src — сначала сохраните настройки в Streamlit"
    exit 1
}

$dest = "${DeployHost}:${RemotePath}/config/settings.local.json"
Write-Host "scp $src -> $dest"
scp $src $dest
Write-Host "OK"
