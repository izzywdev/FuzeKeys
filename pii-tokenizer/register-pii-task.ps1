# Registers the "PII-Stack" scheduled task (AtLogon) to bring up the PII stack and
# unseal Vault automatically after every reboot/logon. Re-run with -Force to update.
$cmd = Join-Path $PSScriptRoot "start-pii-stack.cmd"
$action    = New-ScheduledTaskAction -Execute $cmd
$trigger   = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName "PII-Stack" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Output ("registered: PII-Stack -> " + $cmd)
Write-Output ("state: " + (Get-ScheduledTask -TaskName 'PII-Stack').State)
