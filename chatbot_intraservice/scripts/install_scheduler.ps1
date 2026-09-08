# Install Windows Task Scheduler jobs for local IntraService chatbot.
# Hidden window (no CMD flash). Run:
#   powershell -ExecutionPolicy Bypass -File scripts\install_scheduler.ps1
# Optional: -WithStreamlit  -OverdueMinutes 15  -NewMinutes 15

param(
    [string]$Python = "",
    [int]$OverdueMinutes = 15,
    [int]$NewMinutes = 15,
    [int]$ReplyMinutes = 15,
    [int]$LearnMinutes = 30,
    [switch]$WithStreamlit
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
    $venvPy = Join-Path (Split-Path -Parent $Root) ".venv\Scripts\python.exe"
    $venvPyw = Join-Path (Split-Path -Parent $Root) ".venv\Scripts\pythonw.exe"
    if (Test-Path $venvPyw) { $Python = $venvPyw }
    elseif (Test-Path $venvPy) { $Python = $venvPy }
    else {
        $pyw = (Get-Command pythonw -ErrorAction SilentlyContinue)
        if ($pyw) { $Python = $pyw.Source }
        else { $Python = (Get-Command python).Source }
    }
}

# Prefer pythonw.exe (no console) when user passed python.exe
if ($Python -match 'python\.exe$') {
    $pyw = $Python -replace 'python\.exe$', 'pythonw.exe'
    if (Test-Path $pyw) { $Python = $pyw }
}

$tasks = @(
    @{
        Name = "IEK-IntraService-WatchNew"
        Script = "scripts\watch_new.py"
        Minutes = $NewMinutes
        Desc = "New/transferred tickets 31/38/121 -> analyze (post if auto_post_comment)"
    },
    @{
        Name = "IEK-IntraService-WatchUserReply"
        Script = "scripts\watch_user_reply.py"
        Minutes = $ReplyMinutes
        Desc = "Awaiting reply 46/120 + new user comment -> re-analyze"
    },
    @{
        Name = "IEK-IntraService-WatchOverdue"
        Script = "scripts\watch_overdue.py"
        Minutes = $OverdueMinutes
        Desc = "Overdue escalation LK/BP -> take in work + private comment (hidden)"
    },
    @{
        Name = "IEK-IntraService-WatchLearn"
        Script = "scripts\pipeline_watch.py"
        Minutes = $LearnMinutes
        Desc = "Closed tickets -> AI-KB learning (hidden)"
    }
)

foreach ($t in $tasks) {
    $scriptPath = Join-Path $Root $t.Script
    $arg = "`"$scriptPath`""
    $action = New-ScheduledTaskAction -Execute $Python -Argument $arg -WorkingDirectory $Root
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(1) `
        -RepetitionInterval (New-TimeSpan -Minutes $t.Minutes) `
        -RepetitionDuration (New-TimeSpan -Days 3650)
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 20) `
        -Hidden
    Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger `
        -Settings $settings -Description $t.Desc -Force | Out-Null
    Write-Host "OK $($t.Name) every $($t.Minutes) min (hidden) -> $Python $scriptPath"
}

# Weekly gap digest (Sunday 09:00)
$digestScript = Join-Path $Root "scripts\weekly_gap_digest.py"
$digestAction = New-ScheduledTaskAction -Execute $Python -Argument "`"$digestScript`"" -WorkingDirectory $Root
$digestTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "09:00"
$digestSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -Hidden
Register-ScheduledTask -TaskName "IEK-IntraService-GapDigest" -Action $digestAction -Trigger $digestTrigger `
    -Settings $digestSettings -Description "Weekly KB gap digest for closed tickets" -Force | Out-Null
Write-Host "OK IEK-IntraService-GapDigest weekly Sunday 09:00 -> $Python $digestScript"

# Drafts pending review (Sunday 09:05)
$draftsScript = Join-Path $Root "scripts\drafts_review_digest.py"
$draftsAction = New-ScheduledTaskAction -Execute $Python -Argument "`"$draftsScript`"" -WorkingDirectory $Root
$draftsTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "09:05"
Register-ScheduledTask -TaskName "IEK-IntraService-DraftsReview" -Action $draftsAction -Trigger $draftsTrigger `
    -Settings $digestSettings -Description "AI-KB drafts pending human review" -Force | Out-Null
Write-Host "OK IEK-IntraService-DraftsReview weekly Sunday 09:05 -> $Python $draftsScript"

if ($WithStreamlit) {
    $app = Join-Path $Root "app.py"
    # pythonw плохо тянет streamlit UI — для UI всегда console python.exe из venv
    $pyConsole = $Python
    if ($pyConsole -match 'pythonw\.exe$') {
        $cand = $pyConsole -replace 'pythonw\.exe$', 'python.exe'
        if (Test-Path $cand) { $pyConsole = $cand }
    }
    $stArgs = "-m streamlit run `"$app`" --server.headless true --server.port 8502 --browser.gatherUsageStats false"
    $action = New-ScheduledTaskAction -Execute $pyConsole -Argument $stArgs -WorkingDirectory $Root
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -MultipleInstances IgnoreNew -Hidden
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName "IEK-IntraService-StreamlitUI" -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal `
        -Description "Local Streamlit UI chatbot on port 8502" -Force | Out-Null
    Write-Host "OK IEK-IntraService-StreamlitUI at logon ($env:USERNAME) -> $pyConsole -m streamlit :8502"
}

Write-Host ""
Write-Host "Check: Get-ScheduledTask IEK-IntraService-*"
Write-Host "Manual: cd `"$Root`"; python scripts\watch_new.py --dry-run"
Write-Host "Manual: python scripts\watch_user_reply.py --dry-run"
Write-Host "Manual: python scripts\watch_overdue.py --dry-run"
Write-Host "Manual: python scripts\weekly_gap_digest.py --dry-run"
Write-Host "After review: python scripts\sync_kb_after_review.py --task-id <id>"
Write-Host "Note: IntraService has no outbound webhook API - poll or ask HD admins for email/n8n bridge."
