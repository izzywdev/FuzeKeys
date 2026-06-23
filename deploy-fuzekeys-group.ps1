#!/usr/bin/env pwsh

# FuzeKeys Docker Group Deployment Script
# This script deploys the FuzeKeys platform using Docker Compose with a dedicated group

Write-Host "FuzeKeys Docker Group Deployment" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan

# Check if Docker is running
Write-Host "Checking Docker status..." -ForegroundColor Yellow
try {
    docker version | Out-Null
    Write-Host "Docker is running" -ForegroundColor Green
} catch {
    Write-Host "Docker is not running. Please start Docker Desktop." -ForegroundColor Red
    exit 1
}

# Check if FuzeInfra network exists
Write-Host "Checking FuzeInfra network..." -ForegroundColor Yellow
$fuzeinfraNetwork = docker network ls --filter name=fuzeinfra_default --format "{{.Name}}"
if (-not $fuzeinfraNetwork) {
    Write-Host "Warning: FuzeInfra network not found. Database connectivity may be limited." -ForegroundColor Yellow
} else {
    Write-Host "FuzeInfra network found" -ForegroundColor Green
}

# Stop any existing FuzeKeys containers
Write-Host "Stopping existing FuzeKeys containers..." -ForegroundColor Yellow
docker-compose -f docker-compose.fuzekeys.yml down 2>$null

# Build and start the FuzeKeys group
Write-Host "Building and starting FuzeKeys Docker group..." -ForegroundColor Yellow
$result = docker-compose -f docker-compose.fuzekeys.yml up --build -d
if ($LASTEXITCODE -eq 0) {
    Write-Host "FuzeKeys Docker group started successfully!" -ForegroundColor Green
} else {
    Write-Host "Failed to start FuzeKeys Docker group" -ForegroundColor Red
    exit 1
}

# Wait for services to be healthy
Write-Host "Waiting for services to be healthy..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# Check container status
Write-Host "Checking container status..." -ForegroundColor Yellow
$containers = docker ps --filter "label=com.docker.compose.project=FuzeKeys" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
Write-Host $containers

# Test backend health
Write-Host "Testing backend health..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost:8002/health" -Method Get -TimeoutSec 10
    if ($response.status -eq "healthy") {
        Write-Host "Backend is healthy" -ForegroundColor Green
    } else {
        Write-Host "Backend health check failed" -ForegroundColor Yellow
    }
} catch {
    Write-Host "Backend is not responding" -ForegroundColor Red
}

# Test frontend accessibility
Write-Host "Testing frontend accessibility..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:3005" -Method Get -TimeoutSec 10
    if ($response.StatusCode -eq 200) {
        Write-Host "Frontend is accessible" -ForegroundColor Green
    } else {
        Write-Host "Frontend accessibility check failed" -ForegroundColor Yellow
    }
} catch {
    Write-Host "Frontend is not responding" -ForegroundColor Red
}

Write-Host ""
Write-Host "FuzeKeys Docker Group Deployment Complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Access Information:" -ForegroundColor Cyan
Write-Host "- Backend API: http://localhost:8002" -ForegroundColor White
Write-Host "- API Documentation: http://localhost:8002/docs" -ForegroundColor White
Write-Host "- Frontend Application: http://localhost:3005" -ForegroundColor White
Write-Host "- Health Check: http://localhost:8002/health" -ForegroundColor White
Write-Host ""
Write-Host "Container Information:" -ForegroundColor Cyan
Write-Host "- Backend Container: fuzekeys-backend" -ForegroundColor White
Write-Host "- Frontend Container: fuzekeys-frontend" -ForegroundColor White
Write-Host "- Network: fuzekeys_network" -ForegroundColor White
Write-Host "- Docker Group: FuzeKeys" -ForegroundColor White
Write-Host ""
Write-Host "Management Commands:" -ForegroundColor Cyan
Write-Host "- View logs: docker-compose -f docker-compose.fuzekeys.yml logs -f" -ForegroundColor White
Write-Host "- Stop services: docker-compose -f docker-compose.fuzekeys.yml down" -ForegroundColor White
Write-Host "- Restart services: docker-compose -f docker-compose.fuzekeys.yml restart" -ForegroundColor White
Write-Host "- View status: docker ps --filter label=com.docker.compose.project=FuzeKeys" -ForegroundColor White 