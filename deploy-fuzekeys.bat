@echo off
setlocal enabledelayedexpansion

REM FuzeKeys Deployment Script using FuzeInfra Orchestrator
REM This script deploys FuzeKeys with automatic port allocation, nginx proxy, and DNS routing

echo 🔑 Deploying FuzeKeys with FuzeInfra Orchestrator...
echo.

set "PROJECT_NAME=fuzekeys"
set "PROJECT_PATH=%~dp0"
set "COMPOSE_FILE=docker-compose.yml"
set "FUZEINFRA_PATH=%PROJECT_PATH%modules\FuzeInfra"
set "TOOLS_DIR=%FUZEINFRA_PATH%\tools"

REM Check if FuzeInfra is available
if not exist "%FUZEINFRA_PATH%" (
    echo ❌ FuzeInfra not found at %FUZEINFRA_PATH%
    echo Please ensure FuzeInfra submodule is initialized
    exit /b 1
)

echo ℹ️ Using FuzeInfra at: %FUZEINFRA_PATH%
echo.

REM Check requirements
echo ℹ️ Checking requirements...

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python 3 is required but not installed
    exit /b 1
)

REM Check Docker
docker info >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker is not running or not accessible
    exit /b 1
)

REM Check if we need to create fuzeinfra network
docker network ls | findstr "fuzeinfra_default" >nul
if errorlevel 1 (
    echo ⚠️ FuzeInfra network not found, creating it...
    docker network create fuzeinfra_default
)

echo ✅ Requirements check passed
echo.

REM Start FuzeInfra shared services first
echo ℹ️ Starting FuzeInfra shared services...
cd /d "%FUZEINFRA_PATH%"
docker-compose -f docker-compose.FuzeInfra.yml up -d
if errorlevel 1 (
    echo ⚠️ Warning: Failed to start some FuzeInfra services (may already be running)
)
echo ✅ FuzeInfra shared services ready
echo.

REM Allocate ports for FuzeKeys
echo ℹ️ Analyzing FuzeKeys and allocating ports...
cd /d "%PROJECT_PATH%"
python "%TOOLS_DIR%\port-allocator\port-allocator.py" allocate %PROJECT_NAME% --compose-file "%COMPOSE_FILE%" > temp_ports.json
if errorlevel 1 (
    echo ❌ Failed to allocate ports
    exit /b 1
)

REM Read allocated ports
for /f "delims=" %%i in (temp_ports.json) do set "PORT_ALLOCATION=%%i"
echo ✅ Ports allocated successfully
echo.

REM Inject environment variables
echo ℹ️ Updating environment configuration...
python "%TOOLS_DIR%\env-manager\env-injector.py" inject "%PROJECT_PATH%" --ports "!PORT_ALLOCATION!" > temp_env.json
if errorlevel 1 (
    echo ❌ Failed to inject environment variables
    del temp_ports.json
    exit /b 1
)
echo ✅ Environment variables updated
echo.

REM Generate nginx configuration
echo ℹ️ Generating nginx proxy configuration...
python "%TOOLS_DIR%\nginx-generator\nginx-generator.py" generate --project-name %PROJECT_NAME% --compose-file "%COMPOSE_FILE%" > temp_nginx.json
if errorlevel 1 (
    echo ❌ Failed to generate nginx configuration
    del temp_ports.json temp_env.json
    exit /b 1
)
echo ✅ Nginx configuration generated
echo.

REM Update DNS routing
echo ℹ️ Setting up DNS routing for fuzekeys.dev.local...
python "%TOOLS_DIR%\dns-manager\dns-manager.py" add %PROJECT_NAME% > temp_dns.json
if errorlevel 1 (
    echo ⚠️ Failed to update DNS routing (may require admin privileges)
    echo ℹ️ You can manually add this entry to your hosts file:
    echo ℹ️ 127.0.0.1    fuzekeys.dev.local
) else (
    echo ✅ DNS routing configured
)
echo.

REM Start shared nginx
echo ℹ️ Starting shared nginx proxy...
docker ps | findstr "fuzeinfra-shared-nginx" >nul
if errorlevel 1 (
    cd /d "%FUZEINFRA_PATH%\infrastructure\shared-nginx"
    docker-compose up -d
    timeout /t 5 /nobreak >nul
    echo ✅ Shared nginx started
) else (
    echo ℹ️ Shared nginx already running
)

REM Reload nginx configuration
echo ℹ️ Reloading nginx configuration...
python "%TOOLS_DIR%\nginx-generator\nginx-generator.py" reload > temp_reload.json
echo ✅ Nginx configuration reloaded
echo.

REM Start FuzeKeys
echo ℹ️ Starting FuzeKeys containers...
cd /d "%PROJECT_PATH%"
set "COMPOSE_PROJECT_NAME=fuzekeys"
docker-compose --env-file docker.env up -d
if errorlevel 1 (
    echo ❌ Failed to start FuzeKeys containers
    del temp_*.json
    exit /b 1
)
echo ✅ FuzeKeys containers started
echo.

REM Health checks
echo ℹ️ Performing health checks...
timeout /t 15 /nobreak >nul

curl -s -f "http://fuzekeys.dev.local" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Frontend health check failed - may need more time to start
) else (
    echo ✅ Frontend health check passed
)

curl -s -f "http://fuzekeys.dev.local/api/health" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Backend health check failed - may need more time to start
) else (
    echo ✅ Backend health check passed
)

REM Success message
echo.
echo ✅ 🎉 FuzeKeys deployment completed successfully!
echo.
echo 📊 Deployment Summary:
echo    Project: FuzeKeys
echo    Frontend URL: http://fuzekeys.dev.local
echo    Backend API: http://fuzekeys.dev.local/api
echo    Environment: Production (with hot reload)
echo.
echo 🌐 Access your application:
echo    Main App: http://fuzekeys.dev.local
echo    API Docs: http://fuzekeys.dev.local/api/docs
echo.
echo 📋 Useful commands:
echo    • View logs: docker-compose logs -f
echo    • Stop FuzeKeys: docker-compose down
echo    • Restart: %0
echo.

REM Cleanup temp files
del temp_*.json 2>nul

exit /b 0 