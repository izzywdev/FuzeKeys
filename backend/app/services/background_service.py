import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager
import aiofiles
import signal
import os

from .email_service import EmailVerificationService, EmailConfig, VerificationEmail
from .captcha_service import CaptchaSolverService, CaptchaHandler
from ..automation.web_scraper import WebScraper
from ..utils.encryption import EncryptionManager

logger = logging.getLogger(__name__)

@dataclass
class BackgroundTask:
    """Represents a background task"""
    task_id: str
    task_type: str  # 'email_monitor', 'signup_automation', 'verification_handler'
    status: str  # 'pending', 'running', 'completed', 'failed'
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

@dataclass
class AutomationJob:
    """Represents an automation job"""
    job_id: str
    website: str
    identity_id: int
    email_account: str
    signup_data: Dict[str, Any]
    status: str = 'pending'
    verification_required: bool = False
    verification_email: Optional[VerificationEmail] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

class BackgroundServiceManager:
    """Manages all background services and tasks"""
    
    def __init__(self, 
                 openai_api_key: str,
                 encryption_manager: EncryptionManager,
                 data_dir: str = "data"):
        self.openai_api_key = openai_api_key
        self.encryption_manager = encryption_manager
        self.data_dir = data_dir
        
        # Services
        self.email_service: Optional[EmailVerificationService] = None
        self.captcha_solver = CaptchaSolverService(openai_api_key)
        self.captcha_handler = CaptchaHandler(self.captcha_solver)
        self.web_scraper = WebScraper()
        
        # Task management
        self.tasks: Dict[str, BackgroundTask] = {}
        self.automation_jobs: Dict[str, AutomationJob] = {}
        self.running = False
        self.task_queue = asyncio.Queue()
        
        # Email configs
        self.email_configs: List[EmailConfig] = []
        
        # Ensure data directory exists
        os.makedirs(data_dir, exist_ok=True)
    
    async def start(self):
        """Start all background services"""
        if self.running:
            return
        
        self.running = True
        logger.info("Starting background service manager...")
        
        try:
            # Load saved data
            await self._load_state()
            
            # Start email monitoring if configs available
            if self.email_configs:
                self.email_service = EmailVerificationService(self.email_configs)
                asyncio.create_task(self.email_service.start_monitoring())
                logger.info(f"Started email monitoring for {len(self.email_configs)} accounts")
            
            # Start task processor
            asyncio.create_task(self._process_tasks())
            
            # Start automation job processor
            asyncio.create_task(self._process_automation_jobs())
            
            # Setup graceful shutdown
            self._setup_signal_handlers()
            
            logger.info("Background service manager started successfully")
            
        except Exception as e:
            logger.error(f"Error starting background service manager: {e}")
            self.running = False
    
    async def stop(self):
        """Stop all background services"""
        if not self.running:
            return
        
        logger.info("Stopping background service manager...")
        self.running = False
        
        # Stop email monitoring
        if self.email_service:
            self.email_service.stop_monitoring()
        
        # Save state
        await self._save_state()
        
        logger.info("Background service manager stopped")
    
    def add_email_config(self, email_config: EmailConfig):
        """Add email configuration for monitoring"""
        self.email_configs.append(email_config)
        logger.info(f"Added email config for {email_config.email_address}")
    
    async def create_automation_job(self, 
                                  website: str,
                                  identity_id: int,
                                  email_account: str,
                                  signup_data: Dict[str, Any]) -> str:
        """Create a new automation job"""
        job_id = f"job_{len(self.automation_jobs)}_{int(datetime.now().timestamp())}"
        
        job = AutomationJob(
            job_id=job_id,
            website=website,
            identity_id=identity_id,
            email_account=email_account,
            signup_data=signup_data,
            created_at=datetime.now()
        )
        
        self.automation_jobs[job_id] = job
        
        # Add to task queue
        task = BackgroundTask(
            task_id=f"automation_{job_id}",
            task_type='signup_automation',
            status='pending',
            created_at=datetime.now(),
            data={'job_id': job_id}
        )
        
        await self.task_queue.put(task)
        logger.info(f"Created automation job: {job_id} for {website}")
        
        return job_id
    
    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get status of an automation job"""
        job = self.automation_jobs.get(job_id)
        if not job:
            return None
        
        return {
            'job_id': job.job_id,
            'website': job.website,
            'status': job.status,
            'created_at': job.created_at.isoformat() if job.created_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'verification_required': job.verification_required,
            'error': job.error
        }
    
    async def _process_tasks(self):
        """Process background tasks from the queue"""
        logger.info("Started task processor")
        
        while self.running:
            try:
                # Wait for tasks with timeout
                task = await asyncio.wait_for(self.task_queue.get(), timeout=5.0)
                
                task.started_at = datetime.now()
                task.status = 'running'
                self.tasks[task.task_id] = task
                
                logger.info(f"Processing task: {task.task_id} ({task.task_type})")
                
                # Process based on task type
                success = False
                if task.task_type == 'signup_automation':
                    success = await self._handle_signup_automation(task)
                elif task.task_type == 'email_verification':
                    success = await self._handle_email_verification(task)
                elif task.task_type == 'captcha_solving':
                    success = await self._handle_captcha_solving(task)
                
                # Update task status
                task.completed_at = datetime.now()
                if success:
                    task.status = 'completed'
                    logger.info(f"Task completed successfully: {task.task_id}")
                else:
                    task.status = 'failed'
                    task.retry_count += 1
                    logger.warning(f"Task failed: {task.task_id} (attempt {task.retry_count})")
                    
                    # Retry if under limit
                    if task.retry_count < task.max_retries:
                        task.status = 'pending'
                        await asyncio.sleep(30)  # Wait before retry
                        await self.task_queue.put(task)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing task: {e}")
                if 'task' in locals():
                    task.status = 'failed'
                    task.error = str(e)
    
    async def _process_automation_jobs(self):
        """Monitor and update automation jobs"""
        logger.info("Started automation job processor")
        
        while self.running:
            try:
                # Check for jobs waiting for email verification
                for job in self.automation_jobs.values():
                    if job.status == 'awaiting_verification' and job.verification_email:
                        # Check if enough time has passed to retry verification
                        if job.verification_email.received_date:
                            time_diff = datetime.now() - job.verification_email.received_date
                            if time_diff.total_seconds() > 300:  # 5 minutes
                                await self._retry_verification(job)
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Error in automation job processor: {e}")
                await asyncio.sleep(60)
    
    async def _handle_signup_automation(self, task: BackgroundTask) -> bool:
        """Handle signup automation task"""
        try:
            job_id = task.data.get('job_id')
            job = self.automation_jobs.get(job_id)
            if not job:
                logger.error(f"Job not found: {job_id}")
                return False
            
            job.status = 'running'
            
            # Execute signup automation
            result = await self._execute_signup(job)
            
            if result.get('success'):
                if result.get('verification_required'):
                    job.status = 'awaiting_verification'
                    job.verification_required = True
                    logger.info(f"Signup completed, awaiting email verification: {job_id}")
                else:
                    job.status = 'completed'
                    job.completed_at = datetime.now()
                    logger.info(f"Signup completed successfully: {job_id}")
                
                return True
            else:
                job.status = 'failed'
                job.error = result.get('error', 'Unknown error')
                return False
                
        except Exception as e:
            logger.error(f"Error handling signup automation: {e}")
            return False
    
    async def _execute_signup(self, job: AutomationJob) -> Dict[str, Any]:
        """Execute the actual signup process"""
        try:
            # Start browser automation
            browser_context = await self.web_scraper.create_browser_context()
            page = await browser_context.new_page()
            
            try:
                # Navigate to signup page
                signup_url = f"https://{job.website}.com/signup"  # Simplified
                await page.goto(signup_url)
                
                # Handle potential captcha
                captcha_handled = await self.captcha_handler.handle_page_captcha(page)
                if not captcha_handled:
                    return {'success': False, 'error': 'Failed to solve captcha'}
                
                # Fill signup form
                success = await self._fill_signup_form(page, job.signup_data)
                if not success:
                    return {'success': False, 'error': 'Failed to fill signup form'}
                
                # Submit form
                await page.click('button[type="submit"], input[type="submit"], .signup-button')
                
                # Wait for response
                await page.wait_for_load_state('networkidle')
                
                # Check if verification is required
                verification_elements = await page.query_selector_all(
                    'text="verify", text="check your email", text="confirmation"'
                )
                
                verification_required = len(verification_elements) > 0
                
                return {
                    'success': True,
                    'verification_required': verification_required,
                    'final_url': page.url
                }
                
            finally:
                await browser_context.close()
                
        except Exception as e:
            logger.error(f"Error executing signup: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _fill_signup_form(self, page, signup_data: Dict[str, Any]) -> bool:
        """Fill signup form with provided data"""
        try:
            # Common form field mappings
            field_mappings = {
                'email': ['input[name="email"]', 'input[type="email"]', '#email'],
                'username': ['input[name="username"]', 'input[name="user"]', '#username'],
                'password': ['input[name="password"]', 'input[type="password"]', '#password'],
                'first_name': ['input[name="first_name"]', 'input[name="firstname"]', '#firstname'],
                'last_name': ['input[name="last_name"]', 'input[name="lastname"]', '#lastname'],
                'phone': ['input[name="phone"]', 'input[type="tel"]', '#phone']
            }
            
            for field, selectors in field_mappings.items():
                if field in signup_data:
                    for selector in selectors:
                        element = await page.query_selector(selector)
                        if element:
                            await element.fill(str(signup_data[field]))
                            break
            
            return True
            
        except Exception as e:
            logger.error(f"Error filling signup form: {e}")
            return False
    
    async def _handle_email_verification(self, task: BackgroundTask) -> bool:
        """Handle email verification task"""
        try:
            verification_email = task.data.get('verification_email')
            if not verification_email:
                return False
            
            # Auto-click verification link
            if verification_email.get('verification_link'):
                # Use aiohttp to click the link
                async with aiohttp.ClientSession() as session:
                    async with session.get(verification_email['verification_link']) as response:
                        if response.status == 200:
                            logger.info("Email verification link clicked successfully")
                            return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error handling email verification: {e}")
            return False
    
    async def _handle_captcha_solving(self, task: BackgroundTask) -> bool:
        """Handle captcha solving task"""
        # This would be called when captcha solving is needed independently
        # Most captcha solving happens inline during signup automation
        return True
    
    async def _retry_verification(self, job: AutomationJob):
        """Retry email verification for a job"""
        if job.verification_email and job.verification_email.verification_link:
            task = BackgroundTask(
                task_id=f"verification_retry_{job.job_id}",
                task_type='email_verification',
                status='pending',
                created_at=datetime.now(),
                data={'verification_email': asdict(job.verification_email)}
            )
            await self.task_queue.put(task)
    
    async def _load_state(self):
        """Load saved state from disk"""
        try:
            state_file = os.path.join(self.data_dir, 'background_service_state.json')
            if os.path.exists(state_file):
                async with aiofiles.open(state_file, 'r') as f:
                    data = json.loads(await f.read())
                    
                    # Load tasks
                    for task_data in data.get('tasks', []):
                        task = BackgroundTask(**task_data)
                        self.tasks[task.task_id] = task
                    
                    # Load jobs
                    for job_data in data.get('jobs', []):
                        job = AutomationJob(**job_data)
                        self.automation_jobs[job.job_id] = job
                
                logger.info("Loaded background service state")
                
        except Exception as e:
            logger.error(f"Error loading state: {e}")
    
    async def _save_state(self):
        """Save current state to disk"""
        try:
            state_file = os.path.join(self.data_dir, 'background_service_state.json')
            
            # Prepare data for serialization
            tasks_data = []
            for task in self.tasks.values():
                task_dict = asdict(task)
                # Convert datetime objects to strings
                for key, value in task_dict.items():
                    if isinstance(value, datetime):
                        task_dict[key] = value.isoformat()
                tasks_data.append(task_dict)
            
            jobs_data = []
            for job in self.automation_jobs.values():
                job_dict = asdict(job)
                # Convert datetime objects to strings
                for key, value in job_dict.items():
                    if isinstance(value, datetime):
                        job_dict[key] = value.isoformat()
                jobs_data.append(job_dict)
            
            data = {
                'tasks': tasks_data,
                'jobs': jobs_data,
                'saved_at': datetime.now().isoformat()
            }
            
            async with aiofiles.open(state_file, 'w') as f:
                await f.write(json.dumps(data, indent=2))
            
            logger.info("Saved background service state")
            
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating shutdown...")
            asyncio.create_task(self.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

# Global background service manager instance
background_manager: Optional[BackgroundServiceManager] = None

async def get_background_manager() -> BackgroundServiceManager:
    """Get the global background service manager"""
    global background_manager
    if not background_manager:
        raise RuntimeError("Background service manager not initialized")
    return background_manager

async def initialize_background_manager(openai_api_key: str, encryption_manager: EncryptionManager):
    """Initialize the global background service manager"""
    global background_manager
    if not background_manager:
        background_manager = BackgroundServiceManager(openai_api_key, encryption_manager)
        await background_manager.start()
    return background_manager

@asynccontextmanager
async def background_service_context(openai_api_key: str, encryption_manager: EncryptionManager):
    """Context manager for background services"""
    manager = None
    try:
        manager = await initialize_background_manager(openai_api_key, encryption_manager)
        yield manager
    finally:
        if manager:
            await manager.stop() 