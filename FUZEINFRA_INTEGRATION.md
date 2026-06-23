# FuzeKeys + FuzeInfra Integration

This document explains how FuzeKeys has been integrated with the FuzeInfra Local Development Orchestrator for automatic port allocation, DNS management, and nginx proxy configuration.

## 🎯 What's New

FuzeKeys now supports:
- **Automatic Port Allocation**: No more port conflicts with other services
- **Clean URLs**: Access FuzeKeys at `http://fuzekeys.dev.local` instead of `localhost:3001`
- **DNS Management**: Automatic hosts file management for local development
- **Nginx Proxy**: Centralized proxy with API routing (`/api` → backend, `/` → frontend)
- **Zero Configuration**: Everything is set up automatically

## 🚀 Quick Start

### Prerequisites

- Python 3.6+
- Docker and Docker Compose
- Administrator privileges (for DNS management on Windows)

### Deploy FuzeKeys

**Windows:**
```batch
deploy-fuzekeys.bat
```

**Linux/macOS:**
```bash
./deploy-fuzekeys.sh
```

### Access Your Application

- **Main App**: http://fuzekeys.dev.local
- **API Documentation**: http://fuzekeys.dev.local/api/docs
- **Backend Health**: http://fuzekeys.dev.local/api/health

## 📊 How It Works

The deployment script automatically:

1. **Starts FuzeInfra shared services** (PostgreSQL, Redis, etc.)
2. **Analyzes your docker-compose.yml** to detect services and port requirements
3. **Allocates available ports** to avoid conflicts
4. **Updates environment variables** in `docker.env` with allocated ports
5. **Generates nginx configuration** with proper routing rules
6. **Updates DNS** to map `fuzekeys.dev.local` to `127.0.0.1`
7. **Starts all services** and performs health checks

## 🔧 Configuration

### Port Variables

The following environment variables are now used for port allocation:

```env
# Port Configuration (managed by FuzeInfra port allocator)
FRONTEND_PORT=3001
BACKEND_PORT=8002
```

These ports are automatically allocated by the FuzeInfra port allocator to avoid conflicts.

### Docker Compose Changes

The `docker-compose.yml` has been updated to use environment variables:

```yaml
services:
  fuzekeys-api:
    ports:
      - "${BACKEND_PORT:-8002}:8002"
    environment:
      - BACKEND_PORT=${BACKEND_PORT:-8002}

  fuzekeys-frontend:
    ports:
      - "${FRONTEND_PORT:-3001}:3000"
    environment:
      - FRONTEND_PORT=${FRONTEND_PORT:-3001}
      - REACT_APP_API_URL=http://fuzekeys.dev.local/api
```

### Environment Configuration

The `docker.env` file has been updated to support the new proxy setup:

```env
# Port Configuration (managed by FuzeInfra port allocator)
FRONTEND_PORT=3001
BACKEND_PORT=8002

# Frontend Configuration (updated for nginx proxy)
REACT_APP_API_URL=http://fuzekeys.dev.local/api
```

## 🌐 Nginx Proxy Configuration

The FuzeInfra nginx proxy automatically handles:

- **Frontend routing**: `http://fuzekeys.dev.local/` → Frontend container
- **API routing**: `http://fuzekeys.dev.local/api/` → Backend container
- **WebSocket support** for hot reload during development
- **Health checks** at `/nginx-health`
- **Static asset caching** for production performance

## 🛠️ Manual Operations

### Port Management

```bash
# Allocate ports for FuzeKeys
python modules/FuzeInfra/tools/port-allocator/port-allocator.py allocate fuzekeys --compose-file docker-compose.yml

# Scan available ports
python modules/FuzeInfra/tools/port-allocator/port-allocator.py scan --start-port 3000 --end-port 8000

# Validate specific ports
python modules/FuzeInfra/tools/port-allocator/port-allocator.py validate --ports "3001,8002"
```

### DNS Management

```bash
# Add DNS entry (requires admin privileges)
python modules/FuzeInfra/tools/dns-manager/dns-manager.py add fuzekeys

# Remove DNS entry
python modules/FuzeInfra/tools/dns-manager/dns-manager.py remove fuzekeys

# List managed entries
python modules/FuzeInfra/tools/dns-manager/dns-manager.py list
```

### Nginx Configuration

```bash
# Generate nginx config for FuzeKeys
python modules/FuzeInfra/tools/nginx-generator/nginx-generator.py generate --project-name fuzekeys

# Reload nginx
python modules/FuzeInfra/tools/nginx-generator/nginx-generator.py reload

# Remove project configuration
python modules/FuzeInfra/tools/nginx-generator/nginx-generator.py remove fuzekeys
```

## 🧹 Cleanup

To stop FuzeKeys and clean up all configurations:

**Windows:**
```batch
cleanup-fuzekeys.bat
```

**Linux/macOS:**
```bash
./cleanup-fuzekeys.sh
```

This will:
- Stop FuzeKeys containers
- Remove nginx configuration
- Clean up DNS entries
- Remove temporary files
- Optionally stop shared FuzeInfra services

## 🔍 Troubleshooting

### Port Conflicts

The port allocator automatically finds available ports, but if you encounter issues:

1. Check what ports are in use: `netstat -an | find "LISTENING"`
2. Modify port ranges in `modules/FuzeInfra/tools/port-allocator/config.yaml`
3. Re-run the deployment script

### DNS Issues

**Windows (requires Administrator privileges):**
- Run Command Prompt as Administrator
- Or manually add `127.0.0.1 fuzekeys.dev.local` to `C:\Windows\System32\drivers\etc\hosts`

**Linux/macOS:**
- Use `sudo` when running the deployment script
- Or manually add `127.0.0.1 fuzekeys.dev.local` to `/etc/hosts`

### Nginx Issues

Check nginx logs:
```bash
docker logs fuzeinfra-shared-nginx
```

Validate nginx configuration:
```bash
python modules/FuzeInfra/tools/nginx-generator/nginx-generator.py validate
```

Restart nginx:
```bash
docker restart fuzeinfra-shared-nginx
```

### Application Issues

Check FuzeKeys logs:
```bash
docker-compose logs -f
```

Verify containers are running:
```bash
docker ps
```

## 📋 Development Workflow

1. **Start Development**:
   ```bash
   deploy-fuzekeys.bat  # or ./deploy-fuzekeys.sh
   ```

2. **Develop**: Access your app at http://fuzekeys.dev.local

3. **View Logs**:
   ```bash
   docker-compose logs -f
   ```

4. **Make Changes**: Hot reload works automatically

5. **Stop Development**:
   ```bash
   cleanup-fuzekeys.bat  # or ./cleanup-fuzekeys.sh
   ```

## 🔗 Related Documentation

- [FuzeInfra Tools README](modules/FuzeInfra/tools/README.md)
- [Port Allocator Documentation](modules/FuzeInfra/tools/port-allocator/)
- [DNS Manager Documentation](modules/FuzeInfra/tools/dns-manager/)
- [Nginx Generator Documentation](modules/FuzeInfra/tools/nginx-generator/)

## 🤝 Contributing

When making changes to FuzeKeys that affect the deployment:

1. Update port variables in `docker-compose.yml` following the pattern `${SERVICE_NAME_PORT:-default}`
2. Test with the deployment scripts
3. Update this documentation if needed
4. Ensure cleanup script works properly

## 💡 Tips

- **Use the clean URL**: Always access via `http://fuzekeys.dev.local` for consistency
- **Check health endpoints**: Use `/api/health` for backend and `/nginx-health` for proxy status
- **Monitor logs**: Use `docker-compose logs -f` for real-time debugging
- **Keep shared services running**: Other projects may be using the same FuzeInfra services

---

**Happy development with zero port conflicts! 🎉** 