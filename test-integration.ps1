# FuzeKeys Integration Test Script
# Starts containerized services and runs frontend tests against live backend

Write-Host "🚀 Starting FuzeKeys Integration Test Suite" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green

# Function to check if a service is healthy
function Test-ServiceHealth {
    param([string]$Url, [string]$ServiceName, [int]$MaxRetries = 30)
    
    Write-Host "🔍 Checking $ServiceName health at $Url..." -ForegroundColor Yellow
    
    for ($i = 1; $i -le $MaxRetries; $i++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
            if ($response.StatusCode -eq 200) {
                Write-Host "✅ $ServiceName is healthy!" -ForegroundColor Green
                return $true
            }
        }
        catch {
            Write-Host "⏳ Attempt $i/$MaxRetries - $ServiceName not ready yet..." -ForegroundColor Gray
            Start-Sleep -Seconds 2
        }
    }
    
    Write-Host "❌ $ServiceName failed to become healthy!" -ForegroundColor Red
    return $false
}

# Step 1: Clean up any existing containers
Write-Host "`n🧹 Cleaning up existing test containers..." -ForegroundColor Cyan
docker-compose -f docker-compose.test.yml down --volumes --remove-orphans

# Step 2: Build and start the services
Write-Host "`n🏗️ Building and starting test services..." -ForegroundColor Cyan
docker-compose -f docker-compose.test.yml up -d --build

# Step 3: Wait for services to be healthy
Write-Host "`n⏱️ Waiting for services to be ready..." -ForegroundColor Cyan

# Check database health
if (-not (Test-ServiceHealth "http://localhost:5433" "PostgreSQL Database")) {
    Write-Host "❌ Database failed to start. Exiting..." -ForegroundColor Red
    exit 1
}

# Check backend health
if (-not (Test-ServiceHealth "http://localhost:8003/health" "Backend API")) {
    Write-Host "❌ Backend API failed to start. Exiting..." -ForegroundColor Red
    exit 1
}

# Check frontend health  
if (-not (Test-ServiceHealth "http://localhost:3006/health" "Frontend App")) {
    Write-Host "❌ Frontend app failed to start. Exiting..." -ForegroundColor Red
    exit 1
}

# Step 4: Test the integration
Write-Host "`n🧪 Testing API integration..." -ForegroundColor Cyan

# Test sites API endpoint
try {
    Write-Host "📡 Testing sites API endpoint..." -ForegroundColor Yellow
    $sitesResponse = Invoke-WebRequest -Uri "http://localhost:8003/api/v1/sites?limit=5" -UseBasicParsing
    if ($sitesResponse.StatusCode -eq 200) {
        $sitesData = $sitesResponse.Content | ConvertFrom-Json
        Write-Host "✅ Sites API returned $($sitesData.Count) sites" -ForegroundColor Green
        
        # Display first few sites
        foreach ($site in $sitesData | Select-Object -First 3) {
            Write-Host "  - $($site.display_name): $($site.description)" -ForegroundColor White
        }
    }
}
catch {
    Write-Host "❌ Sites API test failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Test stats API endpoint
try {
    Write-Host "📊 Testing stats API endpoint..." -ForegroundColor Yellow
    $statsResponse = Invoke-WebRequest -Uri "http://localhost:8003/api/v1/sites/stats/overview" -UseBasicParsing
    if ($statsResponse.StatusCode -eq 200) {
        $statsData = $statsResponse.Content | ConvertFrom-Json
        Write-Host "✅ Stats API returned data for $($statsData.total_sites) sites" -ForegroundColor Green
    }
}
catch {
    Write-Host "❌ Stats API test failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Step 5: Run the Jest tests
Write-Host "`n🎯 Running Jest tests against containerized services..." -ForegroundColor Cyan

# Update test environment to point to containerized backend
$env:REACT_APP_API_URL = "http://localhost:8003"

# Run the tests
Write-Host "🧪 Executing SitesDatabase tests..." -ForegroundColor Yellow
docker-compose -f docker-compose.test.yml exec -T fuzekeys-test-runner npm test -- --testPathPattern=SitesDatabase --watchAll=false --verbose

# Step 6: Display results
Write-Host "`n📋 Test Results Summary" -ForegroundColor Green
Write-Host "======================" -ForegroundColor Green

# Check container logs for any errors
Write-Host "`n📄 Backend logs (last 10 lines):" -ForegroundColor Cyan
docker-compose -f docker-compose.test.yml logs --tail=10 fuzekeys-backend-test

Write-Host "`n📄 Frontend logs (last 10 lines):" -ForegroundColor Cyan
docker-compose -f docker-compose.test.yml logs --tail=10 fuzekeys-frontend-test

# Step 7: Cleanup option
Write-Host "`n🗑️ Cleanup Options:" -ForegroundColor Yellow
Write-Host "1. Keep containers running for manual testing" -ForegroundColor White
Write-Host "2. Stop and remove containers" -ForegroundColor White
Write-Host ""

$cleanup = Read-Host "Choose option (1/2)"
if ($cleanup -eq "2") {
    Write-Host "🧹 Cleaning up containers..." -ForegroundColor Cyan
    docker-compose -f docker-compose.test.yml down --volumes
    Write-Host "✅ Cleanup completed!" -ForegroundColor Green
} else {
    Write-Host "🔄 Containers left running. Access them at:" -ForegroundColor Green
    Write-Host "  Frontend: http://localhost:3006" -ForegroundColor White
    Write-Host "  Backend:  http://localhost:8003" -ForegroundColor White
    Write-Host "  Database: localhost:5433" -ForegroundColor White
    Write-Host ""
    Write-Host "To stop later, run: docker-compose -f docker-compose.test.yml down --volumes" -ForegroundColor Gray
}

Write-Host "`n🎉 Integration test suite completed!" -ForegroundColor Green 