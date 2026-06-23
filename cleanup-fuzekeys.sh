#!/bin/bash

# FuzeKeys Cleanup Script
# This script stops FuzeKeys and cleans up DNS entries and nginx configuration

set -e  # Exit on any error

echo "🧹 Cleaning up FuzeKeys deployment..."
echo

PROJECT_NAME="fuzekeys"
PROJECT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FUZEINFRA_PATH="$PROJECT_PATH/modules/FuzeInfra"
TOOLS_DIR="$FUZEINFRA_PATH/tools"

# Stop FuzeKeys containers
echo "ℹ️ Stopping FuzeKeys containers..."
cd "$PROJECT_PATH"
if docker-compose down; then
    echo "✅ FuzeKeys containers stopped"
else
    echo "⚠️ Warning: Some containers may not have stopped cleanly"
fi
echo

# Remove nginx configuration
echo "ℹ️ Removing nginx configuration..."
if [ -d "$FUZEINFRA_PATH" ]; then
    python3 "$TOOLS_DIR/nginx-generator/nginx-generator.py" remove "$PROJECT_NAME" > /dev/null 2>&1 || true
    python3 "$TOOLS_DIR/nginx-generator/nginx-generator.py" reload > /dev/null 2>&1 || true
    echo "✅ Nginx configuration removed"
else
    echo "⚠️ FuzeInfra tools not found, skipping nginx cleanup"
fi
echo

# Remove DNS entries
echo "ℹ️ Removing DNS entries for fuzekeys.dev.local..."
if [ -d "$FUZEINFRA_PATH" ]; then
    if python3 "$TOOLS_DIR/dns-manager/dns-manager.py" remove "$PROJECT_NAME" > /dev/null 2>&1; then
        echo "✅ DNS entries removed"
    else
        echo "⚠️ Failed to remove DNS entries (may require sudo privileges)"
        echo "ℹ️ You can manually remove this entry from your hosts file:"
        echo "ℹ️ 127.0.0.1    fuzekeys.dev.local"
    fi
else
    echo "⚠️ FuzeInfra tools not found, skipping DNS cleanup"
fi
echo

# Clean up temporary files
echo "ℹ️ Cleaning up temporary files..."
rm -f temp_*.json 2>/dev/null || true
echo "✅ Temporary files cleaned up"
echo

# Optional: Stop shared services
echo "ℹ️ Do you want to stop shared FuzeInfra services? (y/N)"
read -r STOP_SHARED
if [[ "$STOP_SHARED" =~ ^[Yy]$ ]]; then
    echo "ℹ️ Stopping shared FuzeInfra services..."
    cd "$FUZEINFRA_PATH"
    docker-compose -f docker-compose.FuzeInfra.yml down || true
    cd "$FUZEINFRA_PATH/infrastructure/shared-nginx"
    docker-compose down || true
    echo "✅ Shared services stopped"
else
    echo "ℹ️ Shared services left running (other projects may be using them)"
fi

echo
echo "✅ 🎉 FuzeKeys cleanup completed!"
echo
echo "📋 Summary:"
echo "   • FuzeKeys containers stopped"
echo "   • Nginx configuration removed"
echo "   • DNS entries cleaned up"
echo "   • Temporary files removed"
echo
echo "💡 To redeploy FuzeKeys, run: ./deploy-fuzekeys.sh"
echo

exit 0 