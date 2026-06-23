#!/usr/bin/env python3
"""
FuzeKeys Setup Script
This script helps set up the FuzeKeys development environment.
"""

import os
import subprocess
import sys
from pathlib import Path

# Import version information
try:
    from version import get_version
except ImportError:
    def get_version():
        return "1.0.0"

def run_command(command, cwd=None, check=True):
    """Run a shell command and return the result."""
    print(f"Running: {command}")
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            cwd=cwd, 
            check=check,
            capture_output=True,
            text=True
        )
        if result.stdout:
            print(result.stdout)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        if e.stderr:
            print(f"Error output: {e.stderr}")
        return None

def setup_backend():
    """Set up the Python backend."""
    print("\n🐍 Setting up Python backend...")
    
    backend_dir = Path("backend")
    if not backend_dir.exists():
        print("Backend directory not found!")
        return False
    
    # Create virtual environment
    venv_path = backend_dir / "venv"
    if not venv_path.exists():
        run_command("python -m venv venv", cwd=backend_dir)
    
    # Determine activation script based on OS
    if os.name == 'nt':  # Windows
        activate_script = venv_path / "Scripts" / "activate"
        pip_path = venv_path / "Scripts" / "pip"
    else:  # Unix/Linux/macOS
        activate_script = venv_path / "bin" / "activate"
        pip_path = venv_path / "bin" / "pip"
    
    # Install dependencies
    run_command(f"{pip_path} install -r requirements.txt", cwd=backend_dir)
    
    print("✅ Backend setup complete!")
    return True

def setup_frontend():
    """Set up the React frontend."""
    print("\n⚛️ Setting up React frontend...")
    
    frontend_dir = Path("frontend")
    if not frontend_dir.exists():
        print("Frontend directory not found!")
        return False
    
    # Install npm dependencies
    run_command("npm install", cwd=frontend_dir)
    
    print("✅ Frontend setup complete!")
    return True

def setup_database():
    """Set up the database using Docker Compose."""
    print("\n🐘 Setting up database...")
    
    # Check if Docker is available
    docker_check = run_command("docker --version", check=False)
    if not docker_check:
        print("Docker not found. Please install Docker to continue.")
        return False
    
    # Start database services
    run_command("docker-compose up -d postgres redis")
    
    print("✅ Database setup complete!")
    return True

def create_env_file():
    """Create environment file from template."""
    print("\n📝 Creating environment file...")
    
    backend_dir = Path("backend")
    env_example = backend_dir / "env.example"
    env_file = backend_dir / ".env"
    
    if env_example.exists() and not env_file.exists():
        # Copy example to .env
        with open(env_example, 'r') as f:
            content = f.read()
        
        # Update database URL for local development
        content = content.replace(
            "DATABASE_URL=postgresql://username:password@localhost/fuzekeys",
            "DATABASE_URL=postgresql://fuzekeys_user:fuzekeys_password@localhost/fuzekeys"
        )
        content = content.replace(
            "DATABASE_URL_ASYNC=postgresql+asyncpg://username:password@localhost/fuzekeys",
            "DATABASE_URL_ASYNC=postgresql+asyncpg://fuzekeys_user:fuzekeys_password@localhost/fuzekeys"
        )
        
        with open(env_file, 'w') as f:
            f.write(content)
        
        print("✅ Environment file created!")
        print("⚠️  Please update the .env file with your actual API keys and secrets!")
    else:
        print("Environment file already exists or template not found.")
    
    return True

def main():
    """Main setup function."""
    print("🚀 Welcome to FuzeKeys Setup!")
    print(f"Version: {get_version()}")
    print("This script will help you set up the development environment.\n")
    
    # Check Python version
    if sys.version_info < (3, 9):
        print("❌ Python 3.9+ is required!")
        sys.exit(1)
    
    success = True
    
    # Setup steps
    success &= create_env_file()
    success &= setup_database()
    success &= setup_backend()
    success &= setup_frontend()
    
    if success:
        print("\n🎉 Setup complete!")
        print("\nNext steps:")
        print("1. Update backend/.env with your API keys")
        print("2. Run database migrations:")
        print("   cd backend && python -m alembic upgrade head")
        print("3. Start the backend:")
        print("   cd backend && python -m uvicorn app.main:app --reload")
        print("4. Start the frontend:")
        print("   cd frontend && npm start")
        print("\nHappy coding! 🎯")
    else:
        print("\n❌ Setup encountered some issues. Please check the output above.")
        sys.exit(1)

if __name__ == "__main__":
    main() 