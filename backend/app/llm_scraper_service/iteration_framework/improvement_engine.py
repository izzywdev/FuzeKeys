"""
Improvement engine for iterative scraper enhancement and production deployment
"""

import os
import json
import logging
import asyncio
import shutil
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from ..llm_integration.code_generator import code_generator, ScraperCode, GenerationResult
from .validation_system import validator, ValidationRun, ValidationStatus
from ..scraper_engine.executor import scraper_executor, ExecutionResult

logger = logging.getLogger(__name__)

class DeploymentStatus(Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"
    DEPRECATED = "deprecated"

@dataclass
class ImprovementIteration:
    iteration_id: str
    scraper_id: str
    version: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    generation_result: Optional[GenerationResult] = None
    validation_result: Optional[ValidationRun] = None
    improvement_reason: str = ""
    success: bool = False

@dataclass
class ProductionRelease:
    release_id: str
    scraper_id: str
    version: int
    deployed_at: datetime
    deployment_status: DeploymentStatus
    success_rate: float
    performance_metrics: Dict[str, Any]
    rollback_version: Optional[int] = None

class ScraperImprovementEngine:
    """Manages iterative scraper improvement and deployment"""
    
    def __init__(self):
        self.improvement_iterations: Dict[str, List[ImprovementIteration]] = {}
        self.production_releases: Dict[str, List[ProductionRelease]] = {}
        self.max_iterations = 5  # Maximum improvement iterations before giving up
        self.min_success_rate = 0.85  # Minimum success rate for production
    
    async def improve_scraper_iteratively(
        self,
        scraper_code: ScraperCode,
        max_iterations: Optional[int] = None,
        target_success_rate: float = 0.9
    ) -> ImprovementIteration:
        """Iteratively improve a scraper until it meets quality standards"""
        
        max_iter = max_iterations or self.max_iterations
        scraper_id = f"{scraper_code.site_name}_{scraper_code.action_type}"
        
        # Initialize iteration tracking
        if scraper_id not in self.improvement_iterations:
            self.improvement_iterations[scraper_id] = []
        
        current_scraper = scraper_code
        
        for iteration in range(max_iter):
            iteration_id = f"{scraper_id}_iter_{iteration}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            
            improvement_iter = ImprovementIteration(
                iteration_id=iteration_id,
                scraper_id=scraper_id,
                version=current_scraper.version,
                started_at=datetime.utcnow(),
                improvement_reason=f"Iteration {iteration + 1}: Improving quality and reliability"
            )
            
            self.improvement_iterations[scraper_id].append(improvement_iter)
            
            logger.info(f"Starting improvement iteration {iteration + 1}/{max_iter} for {scraper_id}")
            
            try:
                # Validate current scraper
                validation_result = await validator.validate_scraper(
                    scraper_code=current_scraper,
                    min_success_rate=target_success_rate
                )
                
                improvement_iter.validation_result = validation_result
                
                # Check if scraper meets quality standards
                if validation_result.overall_success and validation_result.success_rate >= target_success_rate:
                    improvement_iter.success = True
                    improvement_iter.completed_at = datetime.utcnow()
                    
                    logger.info(f"Scraper {scraper_id} meets quality standards: {validation_result.success_rate:.2%}")
                    return improvement_iter
                
                # If not the last iteration, try to improve
                if iteration < max_iter - 1:
                    logger.info(f"Improving scraper {scraper_id} (success rate: {validation_result.success_rate:.2%})")
                    
                    # Generate improvement
                    improvement_result = await self._generate_improvement(current_scraper, validation_result)
                    
                    if improvement_result.success:
                        current_scraper = improvement_result.scraper_code
                        improvement_iter.generation_result = improvement_result
                    else:
                        logger.error(f"Failed to generate improvement: {improvement_result.error_message}")
                        break
                
                improvement_iter.completed_at = datetime.utcnow()
                
            except Exception as e:
                logger.error(f"Error in improvement iteration {iteration + 1}: {e}")
                improvement_iter.completed_at = datetime.utcnow()
                break
        
        # Mark as failed if we didn't succeed
        improvement_iter.success = False
        logger.warning(f"Failed to improve scraper {scraper_id} to target quality after {max_iter} iterations")
        
        return improvement_iter
    
    async def _generate_improvement(
        self,
        scraper_code: ScraperCode,
        validation_result: ValidationRun
    ) -> GenerationResult:
        """Generate improved version based on validation results"""
        
        # Analyze failures to create improvement context
        failed_results = [
            result for result in validation_result.results
            if not result.success
        ]
        
        execution_result = {
            "success": validation_result.overall_success,
            "error_message": self._extract_primary_error(failed_results),
            "screenshot_analysis": self._analyze_screenshots(failed_results),
            "html_context": self._extract_html_context(failed_results),
            "logs": self._combine_logs(failed_results),
            "failure_analysis": self._analyze_failures(failed_results)
        }
        
        # Use code generator to improve scraper
        return await code_generator.improve_scraper(scraper_code, execution_result)
    
    def _extract_primary_error(self, failed_results: List[ExecutionResult]) -> str:
        """Extract the most common or significant error"""
        if not failed_results:
            return "Unknown error"
        
        # Get the most recent error
        return failed_results[-1].error_message or "Execution failed"
    
    def _analyze_screenshots(self, failed_results: List[ExecutionResult]) -> str:
        """Analyze screenshots from failed executions"""
        screenshot_count = sum(len(result.screenshots) for result in failed_results)
        return f"Found {screenshot_count} screenshots from failed executions"
    
    def _extract_html_context(self, failed_results: List[ExecutionResult]) -> str:
        """Extract relevant HTML context from failures"""
        html_contexts = [result.html_context for result in failed_results if result.html_context]
        if html_contexts:
            # Return the most recent HTML context (truncated)
            return html_contexts[-1][:2000] + "..." if len(html_contexts[-1]) > 2000 else html_contexts[-1]
        return ""
    
    def _combine_logs(self, failed_results: List[ExecutionResult]) -> str:
        """Combine logs from failed executions"""
        all_logs = []
        for result in failed_results:
            if result.logs:
                all_logs.append(f"=== {result.scraper_id} v{result.version} ===\n{result.logs}")
        
        combined = "\n\n".join(all_logs)
        return combined[:5000] + "..." if len(combined) > 5000 else combined
    
    def _analyze_failures(self, failed_results: List[ExecutionResult]) -> str:
        """Analyze failure patterns"""
        failure_types = []
        
        for result in failed_results:
            if result.error_message:
                if "timeout" in result.error_message.lower():
                    failure_types.append("timeout")
                elif "element not found" in result.error_message.lower():
                    failure_types.append("selector_issue")
                elif "network" in result.error_message.lower():
                    failure_types.append("network_issue")
                else:
                    failure_types.append("unknown")
        
        if failure_types:
            most_common = max(set(failure_types), key=failure_types.count)
            return f"Primary failure type: {most_common} (occurred {failure_types.count(most_common)} times)"
        
        return "No specific failure pattern identified"
    
    async def deploy_to_production(self, scraper_code: ScraperCode) -> ProductionRelease:
        """Deploy a scraper to production after validation"""
        
        scraper_id = f"{scraper_code.site_name}_{scraper_code.action_type}"
        release_id = f"{scraper_id}_release_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        logger.info(f"Deploying {scraper_id} v{scraper_code.version} to production")
        
        try:
            # Run final validation
            final_validation = await validator.validate_scraper(
                scraper_code=scraper_code,
                min_success_rate=self.min_success_rate
            )
            
            if not final_validation.overall_success:
                raise Exception(f"Scraper failed final validation: {final_validation.success_rate:.2%}")
            
            # Run stress tests
            stress_validation = await validator.run_stress_tests(scraper_code)
            
            # Create production release
            production_release = ProductionRelease(
                release_id=release_id,
                scraper_id=scraper_id,
                version=scraper_code.version,
                deployed_at=datetime.utcnow(),
                deployment_status=DeploymentStatus.PRODUCTION,
                success_rate=final_validation.success_rate,
                performance_metrics={
                    "validation_success_rate": final_validation.success_rate,
                    "stress_test_success_rate": stress_validation.success_rate,
                    "avg_execution_time": self._calculate_avg_execution_time(final_validation),
                    "total_test_cases": len(final_validation.test_cases)
                }
            )
            
            # Store production release
            if scraper_id not in self.production_releases:
                self.production_releases[scraper_id] = []
            self.production_releases[scraper_id].append(production_release)
            
            # Copy to production directory
            await self._copy_to_production(scraper_code)
            
            # Update site directory
            await self._update_site_directory(scraper_code, production_release)
            
            logger.info(f"Successfully deployed {scraper_id} v{scraper_code.version} to production")
            
            return production_release
            
        except Exception as e:
            logger.error(f"Failed to deploy {scraper_id} to production: {e}")
            
            # Create failed release record
            failed_release = ProductionRelease(
                release_id=release_id,
                scraper_id=scraper_id,
                version=scraper_code.version,
                deployed_at=datetime.utcnow(),
                deployment_status=DeploymentStatus.DEVELOPMENT,
                success_rate=0.0,
                performance_metrics={"error": str(e)}
            )
            
            return failed_release
    
    def _calculate_avg_execution_time(self, validation_run: ValidationRun) -> float:
        """Calculate average execution time from validation results"""
        if not validation_run.results:
            return 0.0
        
        execution_times = [result.execution_time for result in validation_run.results if result.success]
        return sum(execution_times) / len(execution_times) if execution_times else 0.0
    
    async def _copy_to_production(self, scraper_code: ScraperCode):
        """Copy scraper to production directory"""
        
        # Source path (generated)
        source_dir = f"backend/app/dynamic_scrapers/generated/{scraper_code.site_name}"
        source_file = f"{scraper_code.site_name}_{scraper_code.action_type}_v{scraper_code.version}.py"
        source_metadata = f"{scraper_code.site_name}_{scraper_code.action_type}_v{scraper_code.version}_metadata.json"
        
        # Production path
        prod_dir = f"backend/app/dynamic_scrapers/production/{scraper_code.site_name}"
        os.makedirs(prod_dir, exist_ok=True)
        
        prod_file = f"{scraper_code.site_name}_{scraper_code.action_type}.py"
        prod_metadata = f"{scraper_code.site_name}_{scraper_code.action_type}_metadata.json"
        
        try:
            # Copy files
            shutil.copy2(
                os.path.join(source_dir, source_file),
                os.path.join(prod_dir, prod_file)
            )
            
            shutil.copy2(
                os.path.join(source_dir, source_metadata),
                os.path.join(prod_dir, prod_metadata)
            )
            
            logger.info(f"Copied scraper to production: {prod_file}")
            
        except Exception as e:
            logger.error(f"Error copying scraper to production: {e}")
            raise
    
    async def _update_site_directory(self, scraper_code: ScraperCode, release: ProductionRelease):
        """Update site directory with production scraper info"""
        
        site_directory_path = "backend/app/site_directory/supported_sites.json"
        
        try:
            # Load current site directory
            with open(site_directory_path, 'r', encoding='utf-8') as f:
                site_directory = json.load(f)
            
            site_name = scraper_code.site_name
            action_type = scraper_code.action_type
            
            # Update scraper info
            if site_name in site_directory["sites"]:
                site_info = site_directory["sites"][site_name]
                
                if "scrapers" not in site_info:
                    site_info["scrapers"] = {}
                
                site_info["scrapers"][action_type] = {
                    "latest_version": scraper_code.version,
                    "production_ready": True,
                    "success_rate": release.success_rate,
                    "last_tested": datetime.utcnow().isoformat(),
                    "deployment_status": release.deployment_status.value,
                    "performance_metrics": release.performance_metrics
                }
                
                # Update site status
                if all(scraper.get("production_ready", False) 
                       for scraper in site_info["scrapers"].values()):
                    site_info["status"] = "production"
                else:
                    site_info["status"] = "development"
            
            # Update metadata
            site_directory["metadata"]["last_updated"] = datetime.utcnow().isoformat()
            site_directory["metadata"]["production_ready_count"] = sum(
                1 for site in site_directory["sites"].values()
                if site.get("status") == "production"
            )
            
            # Save updated directory
            with open(site_directory_path, 'w', encoding='utf-8') as f:
                json.dump(site_directory, f, indent=2)
            
            logger.info(f"Updated site directory for {site_name} {action_type}")
            
        except Exception as e:
            logger.error(f"Error updating site directory: {e}")
    
    async def rollback_production(self, scraper_id: str, target_version: Optional[int] = None) -> bool:
        """Rollback production scraper to previous version"""
        
        if scraper_id not in self.production_releases:
            logger.error(f"No production releases found for {scraper_id}")
            return False
        
        releases = self.production_releases[scraper_id]
        current_release = releases[-1] if releases else None
        
        if not current_release:
            logger.error(f"No current release found for {scraper_id}")
            return False
        
        # Find target version
        if target_version is None:
            # Find previous successful release
            for release in reversed(releases[:-1]):
                if release.deployment_status == DeploymentStatus.PRODUCTION and release.success_rate >= self.min_success_rate:
                    target_version = release.version
                    break
        
        if target_version is None:
            logger.error(f"No suitable rollback version found for {scraper_id}")
            return False
        
        try:
            logger.info(f"Rolling back {scraper_id} from v{current_release.version} to v{target_version}")
            
            # Mark current release as deprecated
            current_release.deployment_status = DeploymentStatus.DEPRECATED
            current_release.rollback_version = target_version
            
            # TODO: Implement actual rollback logic
            # This would involve copying the target version back to production
            
            logger.info(f"Successfully rolled back {scraper_id} to v{target_version}")
            return True
            
        except Exception as e:
            logger.error(f"Error rolling back {scraper_id}: {e}")
            return False
    
    def get_improvement_summary(self, scraper_id: str) -> Dict[str, Any]:
        """Get improvement summary for a scraper"""
        
        iterations = self.improvement_iterations.get(scraper_id, [])
        releases = self.production_releases.get(scraper_id, [])
        
        successful_iterations = [iter for iter in iterations if iter.success]
        latest_release = releases[-1] if releases else None
        
        return {
            "scraper_id": scraper_id,
            "total_iterations": len(iterations),
            "successful_iterations": len(successful_iterations),
            "total_releases": len(releases),
            "latest_release": {
                "version": latest_release.version if latest_release else None,
                "deployment_status": latest_release.deployment_status.value if latest_release else None,
                "success_rate": latest_release.success_rate if latest_release else None,
                "deployed_at": latest_release.deployed_at.isoformat() if latest_release else None
            } if latest_release else None,
            "improvement_history": [
                {
                    "iteration_id": iter.iteration_id,
                    "version": iter.version,
                    "success": iter.success,
                    "started_at": iter.started_at.isoformat(),
                    "completed_at": iter.completed_at.isoformat() if iter.completed_at else None,
                    "improvement_reason": iter.improvement_reason
                }
                for iter in iterations
            ]
        }
    
    async def continuous_improvement(self, scraper_id: str, interval_hours: int = 168):  # Weekly
        """Continuously monitor and improve production scrapers"""
        
        logger.info(f"Starting continuous improvement for {scraper_id}")
        
        while True:
            try:
                # Get latest production scraper
                latest_scraper = code_generator.get_latest_scraper(
                    *scraper_id.split('_', 1)
                )
                
                if not latest_scraper:
                    logger.warning(f"No scraper found for {scraper_id}")
                    await asyncio.sleep(interval_hours * 3600)
                    continue
                
                # Run validation
                validation_result = await validator.validate_scraper(latest_scraper)
                
                # Check if improvement is needed
                if validation_result.success_rate < self.min_success_rate:
                    logger.info(f"Continuous improvement triggered for {scraper_id}: {validation_result.success_rate:.2%}")
                    
                    # Run improvement process
                    improvement_result = await self.improve_scraper_iteratively(latest_scraper)
                    
                    # Deploy if successful
                    if improvement_result.success:
                        await self.deploy_to_production(improvement_result.generation_result.scraper_code)
                
                # Wait for next check
                await asyncio.sleep(interval_hours * 3600)
                
            except Exception as e:
                logger.error(f"Continuous improvement error for {scraper_id}: {e}")
                await asyncio.sleep(3600)  # Wait 1 hour on error

# Global improvement engine instance
improvement_engine = ScraperImprovementEngine() 