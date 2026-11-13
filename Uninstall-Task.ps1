param([string]$TaskName = 'GitHub Repository Archiver')
$ErrorActionPreference = 'Stop'
Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null
Stop-ScheduledTask -TaskName $TaskName
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Output 'Task removed. Archives and configuration have been kept.'
