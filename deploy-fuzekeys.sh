#!/bin/bash

# FuzeKeys Deployment Script using FuzeInfra Orchestrator
# This script deploys FuzeKeys with automatic port allocation, nginx proxy, and DNS routing

set -e  # Exit on any error

echo "🔑 Deploying FuzeKeys with FuzeInfra Orchestrator..."
echo

PROJECT_NAME="fuzekeys"
PROJECT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="docker-compose.yml"
FUZEINFRA_PATH="$PROJECT_PATH/modules/FuzeInfra"
TOOLS_DIR="$FUZEINFRA_PATH/tools"

# Check if FuzeInfra is available
if [ ! -d "$FUZEINFRA_PATH" ]; then
    echo "❌ FuzeInfra not found at $FUZEINFRA_PATH"
    echo "Please ensure FuzeInfra submodule is initialized"
    exit 1
fi

echo "ℹ️ Using FuzeInfra at: $FUZEINFRA_PATH"
echo

# Check requirements
echo "ℹ️ Checking requirements..."

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed"
    exit 1
fi

# Check Docker
if ! docker info &> /dev/null; then
    echo "❌ Docker is not running or not accessible"
    exit 1
fi

# Check if we need to create fuzeinfra network
if ! docker network ls | grep -q "fuzeinfra_default"; then
    echo "⚠️ FuzeInfra network not found, creating it..."
    docker network create fuzeinfra_default
fi

echo "✅ Requirements check passed"
echo

# Start FuzeInfra shared services first
echo "ℹ️ Starting FuzeInfra shared services..."
cd "$FUZEINFRA_PATH"
docker-compose -f docker-compose.FuzeInfra.yml up -d || {
    echo "⚠️ Warning: Failed to start some FuzeInfra services (may already be running)"
}
echo "✅ FuzeInfra shared services ready"
echo

# Allocate ports for FuzeKeys
echo "ℹ️ Analyzing FuzeKeys and allocating ports..."
cd "$PROJECT_PATH"
PORT_ALLOCATION=$(python3 "$TOOLS_DIR/port-allocator/port-allocator.py" allocate "$PROJECT_NAME" --compose-file "$COMPOSE_FILE")
if [ $? -ne 0 ]; then
    echo "❌ Failed to allocate ports"
    exit 1
fi
echo "✅ Ports allocated successfully"
echo

# Inject environment variables
echo "ℹ️ Updating environment configuration..."
python3 "$TOOLS_DIR/env-manager/env-injector.py" inject "$PROJECT_PATH" --ports "$PORT_ALLOCATION" > /dev/null
if [ $? -ne 0 ]; then
    echo "❌ Failed to inject environment variables"
    exit 1
fi
echo "✅ Environment variables updated"
echo

# Generate nginx configuration
echo "ℹ️ Generating nginx proxy configuration..."
python3 "$TOOLS_DIR/nginx-generator/nginx-generator.py" generate --project-name "$PROJECT_NAME" --compose-file "$COMPOSE_FILE" > /dev/null
if [ $? -ne 0 ]; then
    echo "❌ Failed to generate nginx configuration"
    exit 1
fi
echo "✅ Nginx configuration generated"
echo

# Update DNS routing
echo "ℹ️ Setting up DNS routing for fuzekeys.dev.local..."
if ! python3 "$TOOLS_DIR/dns-manager/dns-manager.py" add "$PROJECT_NAME" > /dev/null 2>&1; then
    echo "⚠️ Failed to update DNS routing (may require sudo privileges)"
    echo "ℹ️ You can manually add this entry to your hosts file:"
    echo "ℹ️ 127.0.0.1    fuzekeys.dev.local"
else
    echo "✅ DNS routing configured"
fi
echo

# Start shared nginx
echo "ℹ️ Starting shared nginx proxy..."
if ! docker ps | grep -q "fuzeinfra-shared-nginx"; then
    cd "$FUZEINFRA_PATH/infrastructure/shared-nginx"
    docker-compose up -d
    sleep 5
    echo "✅ Shared nginx started"
else
    echo "ℹ️ Shared nginx already running"
fi

# Reload nginx configuration
echo "ℹ️ Reloading nginx configuration..."
python3 "$TOOLS_DIR/nginx-generator/nginx-generator.py" reload > /dev/null
echo "✅ Nginx configuration reloaded"
echo

# Start FuzeKeys
echo "ℹ️ Starting FuzeKeys containers..."
cd "$PROJECT_PATH"
export COMPOSE_PROJECT_NAME="fuzekeys"
docker-compose --env-file docker.env up -d
if [ $? -ne 0 ]; then
    echo "❌ Failed to start FuzeKeys containers"
    exit 1
fi
echo "✅ FuzeKeys containers started"
echo

# Health checks
echo "ℹ️ Performing health checks..."
sleep 15

if curl -s -f "http://fuzekeys.dev.local" > /dev/null 2>&1; then
    echo "✅ Frontend health check passed"
else
    echo "⚠️ Frontend health check failed - may need more time to start"
fi

if curl -s -f "http://fuzekeys.dev.local/api/health" > /dev/null 2>&1; then
    echo "✅ Backend health check passed"
else
    echo "⚠️ Backend health check failed - may need more time to start"
fi

# Success message
echo
echo "✅ 🎉 FuzeKeys deployment completed successfully!"
echo
echo "📊 Deployment Summary:"
echo "   Project: FuzeKeys"
echo "   Frontend URL: http://fuzekeys.dev.local"
echo "   Backend API: http://fuzekeys.dev.local/api"
echo "   Environment: Production (with hot reload)"
echo
echo "🌐 Access your application:"
echo "   Main App: http://fuzekeys.dev.local"
echo "   API Docs: http://fuzekeys.dev.local/api/docs"
echo
echo "📋 Useful commands:"
echo "   • View logs: docker-compose logs -f"
echo "   • Stop FuzeKeys: docker-compose down"
echo "   • Restart: $0"
echo

exit 0 