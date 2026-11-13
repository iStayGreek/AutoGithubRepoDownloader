param(
    [string]$TaskName = 'GitHub Repository Archiver',
    [string]$PythonPath,
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'repositories.json')
)
$ErrorActionPreference = 'Stop'
if (-not $PythonPath) {
    $python = Get-Command python.exe -ErrorAction Stop
    $PythonPath = (& $python.Source -c 'import sys; print(sys.executable)').Trim()
    if ($LASTEXITCODE -ne 0) { throw 'A working Python 3.10+ installation is required.' }
}
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
$ConfigPath = (Resolve-Path -LiteralPath $ConfigPath).Path
$scriptPath = Join-Path $PSScriptRoot 'repo_backup.py'
& $PythonPath $scriptPath --config $ConfigPath --validate
if ($LASTEXITCODE -ne 0) { throw 'Configuration validation failed.' }
$windowless = Join-Path (Split-Path $PythonPath) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $windowless)) { throw 'pythonw.exe is required for a hidden task.' }
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    throw "Task '$TaskName' already exists. Uninstall it first to change its configuration."
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $windowless -Argument ('"' + $scriptPath + '" --config "' + $ConfigPath + '"') -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -Hidden -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
Start-ScheduledTask -TaskName $TaskName
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
