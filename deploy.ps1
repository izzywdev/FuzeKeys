# FuzeKeys Deployment Script
Write-Host "FuzeKeys Deployment Script" -ForegroundColor Cyan
Write-Host "==========================" -ForegroundColor Cyan

# Check Docker
Write-Host "Checking Docker..." -ForegroundColor Yellow
try {
    docker version | Out-Null
    Write-Host "Docker is running" -ForegroundColor Green
}
catch {
    Write-Host "Docker is not running. Please start Docker Desktop." -ForegroundColor Red
    exit 1
}

# Create network if needed
Write-Host "Setting up FuzeInfra network..." -ForegroundColor Yellow
$networkExists = docker network ls --filter name=fuzeinfra_default --format "{{.Name}}" | Select-String "fuzeinfra_default"
if (-not $networkExists) {
    docker network create fuzeinfra_default
    Write-Host "Created FuzeInfra network" -ForegroundColor Green
}

# Start PostgreSQL if needed
Write-Host "Starting shared PostgreSQL..." -ForegroundColor Yellow
$postgresRunning = docker ps --filter name=shared-postgres --filter status=running --format "{{.Names}}" | Select-String "shared-postgres"
if (-not $postgresRunning) {
    $postgresExists = docker ps -a --filter name=shared-postgres --format "{{.Names}}" | Select-String "shared-postgres"
    if ($postgresExists) {
        docker start shared-postgres
    } else {
        docker run -d --name shared-postgres --network fuzeinfra_default -e POSTGRES_DB=postgres -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -p 5432:5432 -v postgres_data:/var/lib/postgresql/data postgres:15
    }
    Start-Sleep -Seconds 10
}

# Deploy FuzeKeys
Write-Host "Building and deploying FuzeKeys..." -ForegroundColor Yellow
docker-compose down --remove-orphans
docker-compose build
docker-compose up -d

Write-Host ""
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "Frontend: http://localhost:3001" -ForegroundColor White
Write-Host "Backend:  http://localhost:8002" -ForegroundColor White
Write-Host "API Docs: http://localhost:8002/docs" -ForegroundColor White
Write-Host "Sites DB: http://localhost:3001/sites" -ForegroundColor White 