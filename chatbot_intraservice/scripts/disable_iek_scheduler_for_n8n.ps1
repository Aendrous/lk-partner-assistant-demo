# Отключить Windows Task Scheduler watch-задачи при переходе на n8n.
# Не удаляет задачи — только Disable (можно вернуть Enable-ScheduledTask).

param(
    [switch]$WhatIf
)

$names = @(
    "IEK-IntraService-WatchNew",
    "IEK-IntraService-WatchUserReply",
    "IEK-IntraService-WatchOverdue",
    "IEK-IntraService-WatchLearn",
    "IEK-IntraService-GapDigest",
    "IEK-IntraService-DraftsReview",
    "IEK-IntraService-StreamlitUI"
)

foreach ($name in $names) {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Host "SKIP $name (нет задачи)"
        continue
    }
    if ($WhatIf) {
        Write-Host "WOULD DISABLE $name (State=$($task.State))"
        continue
    }
    Disable-ScheduledTask -TaskName $name | Out-Null
    Write-Host "DISABLED $name"
}

Write-Host ""
Write-Host "Проверка: Get-ScheduledTask IEK-IntraService-* | Format-Table TaskName, State"
