@echo off
REM Logon launcher for the PII stack: ensures Docker + containers are up, then unseals
REM Vault and bootstraps the transit engine. Location-independent (cd's to its own dir).
REM Registered as the "PII-Stack" scheduled task (AtLogon).
set "HERE=%~dp0"
"C:\Program Files\Git\bin\bash.exe" -lc "cd \"$(cygpath -u '%HERE%')\" && ./stack-up.sh >> stack-up.log 2>&1"
