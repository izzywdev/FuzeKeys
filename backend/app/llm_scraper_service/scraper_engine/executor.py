"""
Scraper execution engine for running generated scrapers in isolated environments
"""

import os
import json
import logging
import asyncio
import tempfile
import shutil
import subprocess
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import docker
import base64

logger = logging.getLogger(__name__)

@dataclass
class ExecutionResult:
    success: bool
    scraper_id: str
    version: int
    execution_time: float
    logs: str
    screenshots: List[str]
    html_context: str
    error_message: Optional[str] = None
    return_data: Optional[Dict[str, Any]] = None
    execution_metadata: Optional[Dict[str, Any]] = None

class DockerScraperExecutor:
    """Execute scrapers in isolated Docker containers"""
    
    def __init__(self):
        try:
            self.docker_client = docker.from_env()
            logger.info("Docker client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            self.docker_client = None
    
    async def execute_scraper(
        self,
        scraper_code: str,
        scraper_id: str,
        version: int,
        test_data: Dict[str, Any],
        timeout: int = 300
    ) -> ExecutionResult:
        """Execute scraper in Docker container"""
        
        if not self.docker_client:
            return ExecutionResult(
                success=False,
                scraper_id=scraper_id,
                version=version,
                execution_time=0.0,
                logs="Docker client not available",
                screenshots=[],
                html_context="",
                error_message="Docker not available"
            )
        
        start_time = datetime.utcnow()
        container = None
        temp_dir = None
        
        try:
            # Create temporary directory for scraper files
            temp_dir = tempfile.mkdtemp(prefix=f"scraper_{scraper_id}_v{version}_")
            
            # Prepare scraper environment
            await self._prepare_scraper_environment(temp_dir, scraper_code, test_data)
            
            # Create and run Docker container
            container = await self._create_container(temp_dir, timeout)
            
            # Execute scraper
            execution_logs = await self._run_scraper(container, timeout)
            
            # Collect results
            result = await self._collect_results(container, temp_dir, execution_logs)
            
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            return ExecutionResult(
                success=result["success"],
                scraper_id=scraper_id,
                version=version,
                execution_time=execution_time,
                logs=result["logs"],
                screenshots=result["screenshots"],
                html_context=result["html_context"],
                error_message=result.get("error_message"),
                return_data=result.get("return_data"),
                execution_metadata={
                    "container_id": container.id if container else None,
                    "temp_dir": temp_dir,
                    "execution_start": start_time.isoformat()
                }
            )
            
        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Error executing scraper {scraper_id}: {e}")
            
            return ExecutionResult(
                success=False,
                scraper_id=scraper_id,
                version=version,
                execution_time=execution_time,
                logs=str(e),
                screenshots=[],
                html_context="",
                error_message=str(e)
            )
            
        finally:
            # Cleanup
            if container:
                try:
                    container.stop()
                    container.remove()
                except:
                    pass
            
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass
    
    async def _prepare_scraper_environment(self, temp_dir: str, scraper_code: str, test_data: Dict[str, Any]):
        """Prepare the scraper execution environment"""
        
        # Write scraper code
        scraper_file = os.path.join(temp_dir, "scraper.py")
        with open(scraper_file, 'w', encoding='utf-8') as f:
            f.write(scraper_code)
        
        # Write test data
        test_data_file = os.path.join(temp_dir, "test_data.json")
        with open(test_data_file, 'w', encoding='utf-8') as f:
            json.dump(test_data, f, indent=2)
        
        # Create requirements file for the container
        requirements_file = os.path.join(temp_dir, "requirements.txt")
        with open(requirements_file, 'w', encoding='utf-8') as f:
            f.write("""
selenium==4.15.2
requests==2.31.0
beautifulsoup4==4.12.2
pillow==10.1.0
""".strip())
        
        # Create execution script
        execution_script = os.path.join(temp_dir, "run_scraper.py")
        with open(execution_script, 'w', encoding='utf-8') as f:
            f.write("""
import json
import sys
import traceback
import asyncio
from datetime import datetime
from scraper import main

def run_scraper():
    try:
        # Load test data
        with open('/app/test_data.json', 'r') as f:
            test_data = json.load(f)
        
        # Run scraper
        result = asyncio.run(main(**test_data))
        
        # Save result
        with open('/app/result.json', 'w') as f:
            json.dump({
                "success": True,
                "result": result,
                "timestamp": datetime.utcnow().isoformat()
            }, f, indent=2)
        
        print("SCRAPER_SUCCESS")
        sys.exit(0)
        
    except Exception as e:
        error_result = {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        with open('/app/result.json', 'w') as f:
            json.dump(error_result, f, indent=2)
        
        print(f"SCRAPER_ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_scraper()
""".strip())
        
        # Create Dockerfile
        dockerfile = os.path.join(temp_dir, "Dockerfile")
        with open(dockerfile, 'w', encoding='utf-8') as f:
            f.write("""
FROM python:3.11-slim

# Install Chrome and ChromeDriver
RUN apt-get update && apt-get install -y \\
    wget \\
    gnupg \\
    unzip \\
    curl \\
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \\
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \\
    && apt-get update \\
    && apt-get install -y google-chrome-stable \\
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver
RUN CHROMEDRIVER_VERSION=`curl -sS chromedriver.storage.googleapis.com/LATEST_RELEASE` && \\
    mkdir -p /opt/chromedriver-$CHROMEDRIVER_VERSION && \\
    curl -sS -o /tmp/chromedriver_linux64.zip http://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip && \\
    unzip -qq /tmp/chromedriver_linux64.zip -d /opt/chromedriver-$CHROMEDRIVER_VERSION && \\
    rm /tmp/chromedriver_linux64.zip && \\
    chmod +x /opt/chromedriver-$CHROMEDRIVER_VERSION/chromedriver && \\
    ln -fs /opt/chromedriver-$CHROMEDRIVER_VERSION/chromedriver /usr/local/bin/chromedriver

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy scraper files
COPY . .

# Run scraper
CMD ["python", "run_scraper.py"]
""".strip())
    
    async def _create_container(self, temp_dir: str, timeout: int):
        """Create Docker container for scraper execution"""
        
        # Build Docker image
        image_tag = f"scraper-executor:{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        try:
            # Build image
            image, build_logs = self.docker_client.images.build(
                path=temp_dir,
                tag=image_tag,
                rm=True,
                forcerm=True
            )
            
            # Create container
            container = self.docker_client.containers.create(
                image=image_tag,
                detach=True,
                mem_limit="1g",
                cpu_quota=100000,  # 1 CPU
                network_mode="bridge",
                volumes={
                    temp_dir: {"bind": "/app", "mode": "rw"}
                },
                environment={
                    "DISPLAY": ":99",
                    "PYTHONUNBUFFERED": "1"
                }
            )
            
            return container
            
        except Exception as e:
            logger.error(f"Error creating container: {e}")
            raise
    
    async def _run_scraper(self, container, timeout: int):
        """Run the scraper in the container"""
        
        try:
            # Start container
            container.start()
            
            # Wait for completion with timeout
            result = container.wait(timeout=timeout)
            
            # Get logs
            logs = container.logs(stdout=True, stderr=True).decode('utf-8')
            
            return logs
            
        except Exception as e:
            logger.error(f"Error running scraper: {e}")
            return f"Container execution error: {e}"
    
    async def _collect_results(self, container, temp_dir: str, execution_logs: str) -> Dict[str, Any]:
        """Collect execution results from container"""
        
        result = {
            "success": False,
            "logs": execution_logs,
            "screenshots": [],
            "html_context": "",
            "error_message": None,
            "return_data": None
        }
        
        try:
            # Check if result file exists
            result_file = os.path.join(temp_dir, "result.json")
            if os.path.exists(result_file):
                with open(result_file, 'r') as f:
                    scraper_result = json.load(f)
                
                result["success"] = scraper_result.get("success", False)
                result["return_data"] = scraper_result.get("result")
                
                if not result["success"]:
                    result["error_message"] = scraper_result.get("error", "Unknown error")
            
            # Collect screenshots
            screenshots_dir = os.path.join(temp_dir, "screenshots")
            if os.path.exists(screenshots_dir):
                for screenshot_file in os.listdir(screenshots_dir):
                    if screenshot_file.endswith(('.png', '.jpg', '.jpeg')):
                        screenshot_path = os.path.join(screenshots_dir, screenshot_file)
                        with open(screenshot_path, 'rb') as f:
                            screenshot_data = base64.b64encode(f.read()).decode('utf-8')
                            result["screenshots"].append(screenshot_data)
            
            # Collect HTML context
            html_file = os.path.join(temp_dir, "page_source.html")
            if os.path.exists(html_file):
                with open(html_file, 'r', encoding='utf-8') as f:
                    result["html_context"] = f.read()
            
            # Determine success from logs if not explicitly set
            if "SCRAPER_SUCCESS" in execution_logs:
                result["success"] = True
            elif "SCRAPER_ERROR" in execution_logs:
                result["success"] = False
                if not result["error_message"]:
                    result["error_message"] = "Scraper execution failed"
            
        except Exception as e:
            logger.error(f"Error collecting results: {e}")
            result["error_message"] = f"Result collection failed: {e}"
        
        return result

class LocalScraperExecutor:
    """Execute scrapers locally (fallback when Docker is not available)"""
    
    async def execute_scraper(
        self,
        scraper_code: str,
        scraper_id: str,
        version: int,
        test_data: Dict[str, Any],
        timeout: int = 300
    ) -> ExecutionResult:
        """Execute scraper locally with basic isolation"""
        
        start_time = datetime.utcnow()
        temp_dir = None
        
        try:
            # Create temporary directory
            temp_dir = tempfile.mkdtemp(prefix=f"scraper_{scraper_id}_v{version}_")
            
            # Write scraper code
            scraper_file = os.path.join(temp_dir, "scraper.py")
            with open(scraper_file, 'w', encoding='utf-8') as f:
                f.write(scraper_code)
            
            # Create execution environment
            env = os.environ.copy()
            env["PYTHONPATH"] = temp_dir
            
            # Run scraper
            process = await asyncio.create_subprocess_exec(
                "python", "-c", f"""
import sys
sys.path.insert(0, '{temp_dir}')
import json
import asyncio
from scraper import main

try:
    result = asyncio.run(main(**{json.dumps(test_data)}))
    print(json.dumps({{"success": True, "result": result}}))
except Exception as e:
    print(json.dumps({{"success": False, "error": str(e)}}))
""",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            # Wait with timeout
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            # Parse result
            try:
                result_data = json.loads(stdout.decode('utf-8'))
                success = result_data.get("success", False)
                error_message = result_data.get("error") if not success else None
                return_data = result_data.get("result")
            except:
                success = False
                error_message = "Failed to parse scraper output"
                return_data = None
            
            logs = f"STDOUT:\n{stdout.decode('utf-8')}\n\nSTDERR:\n{stderr.decode('utf-8')}"
            
            return ExecutionResult(
                success=success,
                scraper_id=scraper_id,
                version=version,
                execution_time=execution_time,
                logs=logs,
                screenshots=[],
                html_context="",
                error_message=error_message,
                return_data=return_data
            )
            
        except asyncio.TimeoutError:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            return ExecutionResult(
                success=False,
                scraper_id=scraper_id,
                version=version,
                execution_time=execution_time,
                logs="Execution timeout",
                screenshots=[],
                html_context="",
                error_message="Scraper execution timed out"
            )
            
        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            return ExecutionResult(
                success=False,
                scraper_id=scraper_id,
                version=version,
                execution_time=execution_time,
                logs=str(e),
                screenshots=[],
                html_context="",
                error_message=str(e)
            )
            
        finally:
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass

class ScraperExecutor:
    """Main scraper executor that chooses between Docker and local execution"""
    
    def __init__(self):
        self.docker_executor = DockerScraperExecutor()
        self.local_executor = LocalScraperExecutor()
        self.use_docker = self.docker_executor.docker_client is not None
        
        if self.use_docker:
            logger.info("Using Docker executor for scraper execution")
        else:
            logger.warning("Docker not available, using local executor (less secure)")
    
    async def execute_scraper(
        self,
        scraper_code: str,
        scraper_id: str,
        version: int,
        test_data: Dict[str, Any],
        timeout: int = 300,
        force_local: bool = False
    ) -> ExecutionResult:
        """Execute scraper using the best available method"""
        
        if self.use_docker and not force_local:
            return await self.docker_executor.execute_scraper(
                scraper_code, scraper_id, version, test_data, timeout
            )
        else:
            return await self.local_executor.execute_scraper(
                scraper_code, scraper_id, version, test_data, timeout
            )

# Global executor instance
scraper_executor = ScraperExecutor() 