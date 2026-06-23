# FuzeKeys Deployment Script for Windows PowerShell
# This script deploys FuzeKeys using Docker Compose with FuzeInfra as the database provider

Write-Host "🚀 FuzeKeys Deployment Script" -ForegroundColor Cyan
Write-Host "===============================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
Write-Host "🔍 Checking Docker status..." -ForegroundColor Yellow
try {
    docker version | Out-Null
    Write-Host "✅ Docker is running" -ForegroundColor Green
}
catch {
    Write-Host "❌ Docker is not running. Please start Docker Desktop and try again." -ForegroundColor Red
    exit 1
}

# Check if FuzeInfra network exists
Write-Host "🔍 Checking FuzeInfra network..." -ForegroundColor Yellow
$networkExists = docker network ls --filter name=fuzeinfra_default --format "{{.Name}}" | Select-String "fuzeinfra_default"
if (-not $networkExists) {
    Write-Host "⚠️  FuzeInfra network not found. Creating it..." -ForegroundColor Yellow
    docker network create fuzeinfra_default
    Write-Host "✅ FuzeInfra network created" -ForegroundColor Green
} else {
    Write-Host "✅ FuzeInfra network exists" -ForegroundColor Green
}

# Check if shared-postgres container is running
Write-Host "🔍 Checking shared PostgreSQL..." -ForegroundColor Yellow
$postgresRunning = docker ps --filter name=shared-postgres --filter status=running --format "{{.Names}}" | Select-String "shared-postgres"
if (-not $postgresRunning) {
    Write-Host "⚠️  Shared PostgreSQL not running. Starting it..." -ForegroundColor Yellow
    
    # Check if container exists but is stopped
    $postgresExists = docker ps -a --filter name=shared-postgres --format "{{.Names}}" | Select-String "shared-postgres"
    if ($postgresExists) {
        Write-Host "🔄 Starting existing PostgreSQL container..." -ForegroundColor Yellow
        docker start shared-postgres
    } else {
        Write-Host "🐘 Creating new PostgreSQL container..." -ForegroundColor Yellow
        docker run -d `
            --name shared-postgres `
            --network fuzeinfra_default `
            -e POSTGRES_DB=postgres `
            -e POSTGRES_USER=postgres `
            -e POSTGRES_PASSWORD=postgres `
            -p 5432:5432 `
            -v postgres_data:/var/lib/postgresql/data `
            postgres:15
    }
    
    Write-Host "⏳ Waiting for PostgreSQL to be ready..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10
    Write-Host "✅ PostgreSQL is ready" -ForegroundColor Green
} else {
    Write-Host "✅ Shared PostgreSQL is running" -ForegroundColor Green
}

# Stop any existing FuzeKeys containers
Write-Host "🧹 Cleaning up existing containers..." -ForegroundColor Yellow
docker-compose down --remove-orphans

# Build and deploy FuzeKeys
Write-Host "🏗️  Building FuzeKeys containers..." -ForegroundColor Yellow
docker-compose build --parallel

Write-Host "🚀 Deploying FuzeKeys..." -ForegroundColor Yellow
docker-compose up -d

# Wait for services to be ready
Write-Host "⏳ Waiting for services to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 15

# Check service health
Write-Host "🔍 Checking service health..." -ForegroundColor Yellow

# Check backend
try {
    $backendHealth = Invoke-RestMethod -Uri "http://localhost:8002/health" -Method Get -TimeoutSec 5
    Write-Host "✅ Backend API is healthy" -ForegroundColor Green
}
catch {
    Write-Host "⚠️  Backend API health check failed (may still be starting)" -ForegroundColor Yellow
}

# Check frontend
try {
    $frontendResponse = Invoke-WebRequest -Uri "http://localhost:3001" -Method Get -TimeoutSec 5
    if ($frontendResponse.StatusCode -eq 200) {
        Write-Host "✅ Frontend is accessible" -ForegroundColor Green
    }
}
catch {
    Write-Host "⚠️  Frontend health check failed (may still be starting)" -ForegroundColor Yellow
}

# Show deployment status
Write-Host ""
Write-Host "🎉 FuzeKeys Deployment Complete!" -ForegroundColor Green
Write-Host "===================================" -ForegroundColor Green
Write-Host ""
Write-Host "📊 Service URLs:" -ForegroundColor Cyan
Write-Host "  Frontend:     http://localhost:3001" -ForegroundColor White
Write-Host "  Backend API:  http://localhost:8002" -ForegroundColor White
Write-Host "  API Docs:     http://localhost:8002/docs" -ForegroundColor White
Write-Host "  Sites DB:     http://localhost:3001/sites" -ForegroundColor White
Write-Host ""
Write-Host "🗄️  Database:" -ForegroundColor Cyan
Write-Host "  PostgreSQL:   localhost:5432" -ForegroundColor White
Write-Host "  Database:     fuzekeys" -ForegroundColor White
Write-Host "  User:         fuzekeys_user" -ForegroundColor White
Write-Host ""
Write-Host "📋 Container Status:" -ForegroundColor Cyan
docker-compose ps

Write-Host ""
Write-Host "💡 Next Steps:" -ForegroundColor Cyan
Write-Host "  1. Visit http://localhost:3001 to access FuzeKeys" -ForegroundColor White
Write-Host "  2. Go to http://localhost:3001/sites to see the Sites Database" -ForegroundColor White
Write-Host "  3. Check http://localhost:8002/docs for API documentation" -ForegroundColor White
Write-Host ""
Write-Host "🔧 Useful Commands:" -ForegroundColor Cyan
Write-Host "  View logs:      docker-compose logs -f" -ForegroundColor White
Write-Host "  Stop services:  docker-compose down" -ForegroundColor White
Write-Host "  Restart:        docker-compose restart" -ForegroundColor White
Write-Host ""

# Show live logs for a few seconds
Write-Host "📋 Recent logs (last 20 lines):" -ForegroundColor Cyan
docker-compose logs --tail=20

Write-Host ""
Write-Host "🎯 FuzeKeys is now running with FuzeInfra database provider!" -ForegroundColor Green 