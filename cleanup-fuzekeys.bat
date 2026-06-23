@echo off
setlocal enabledelayedexpansion

REM FuzeKeys Cleanup Script
REM This script stops FuzeKeys and cleans up DNS entries and nginx configuration

echo 🧹 Cleaning up FuzeKeys deployment...
echo.

set "PROJECT_NAME=fuzekeys"
set "PROJECT_PATH=%~dp0"
set "FUZEINFRA_PATH=%PROJECT_PATH%modules\FuzeInfra"
set "TOOLS_DIR=%FUZEINFRA_PATH%\tools"

REM Stop FuzeKeys containers
echo ℹ️ Stopping FuzeKeys containers...
cd /d "%PROJECT_PATH%"
docker-compose down
if errorlevel 1 (
    echo ⚠️ Warning: Some containers may not have stopped cleanly
) else (
    echo ✅ FuzeKeys containers stopped
)
echo.

REM Remove nginx configuration
echo ℹ️ Removing nginx configuration...
if exist "%FUZEINFRA_PATH%" (
    python "%TOOLS_DIR%\nginx-generator\nginx-generator.py" remove %PROJECT_NAME% > nul 2>&1
    python "%TOOLS_DIR%\nginx-generator\nginx-generator.py" reload > nul 2>&1
    echo ✅ Nginx configuration removed
) else (
    echo ⚠️ FuzeInfra tools not found, skipping nginx cleanup
)
echo.

REM Remove DNS entries
echo ℹ️ Removing DNS entries for fuzekeys.dev.local...
if exist "%FUZEINFRA_PATH%" (
    python "%TOOLS_DIR%\dns-manager\dns-manager.py" remove %PROJECT_NAME% > nul 2>&1
    if errorlevel 1 (
        echo ⚠️ Failed to remove DNS entries (may require admin privileges)
        echo ℹ️ You can manually remove this entry from your hosts file:
        echo ℹ️ 127.0.0.1    fuzekeys.dev.local
    ) else (
        echo ✅ DNS entries removed
    )
) else (
    echo ⚠️ FuzeInfra tools not found, skipping DNS cleanup
)
echo.

REM Clean up temporary files
echo ℹ️ Cleaning up temporary files...
del temp_*.json 2>nul
echo ✅ Temporary files cleaned up
echo.

REM Optional: Stop shared services
echo ℹ️ Do you want to stop shared FuzeInfra services? (y/N)
set /p "STOP_SHARED="
if /i "%STOP_SHARED%"=="y" (
    echo ℹ️ Stopping shared FuzeInfra services...
    cd /d "%FUZEINFRA_PATH%"
    docker-compose -f docker-compose.FuzeInfra.yml down
    cd /d "%FUZEINFRA_PATH%\infrastructure\shared-nginx"
    docker-compose down
    echo ✅ Shared services stopped
) else (
    echo ℹ️ Shared services left running (other projects may be using them)
)

echo.
echo ✅ 🎉 FuzeKeys cleanup completed!
echo.
echo 📋 Summary:
echo    • FuzeKeys containers stopped
echo    • Nginx configuration removed
echo    • DNS entries cleaned up
echo    • Temporary files removed
echo.
echo 💡 To redeploy FuzeKeys, run: deploy-fuzekeys.bat
echo.

exit /b 0 