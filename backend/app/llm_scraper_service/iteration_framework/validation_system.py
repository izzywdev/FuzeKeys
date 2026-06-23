"""
Validation system for testing and validating scrapers
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from ..scraper_engine.executor import scraper_executor, ExecutionResult
from ..llm_integration.code_generator import ScraperCode

logger = logging.getLogger(__name__)

class ValidationStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"

@dataclass
class TestCase:
    name: str
    test_data: Dict[str, Any]
    expected_outcome: str  # "success", "failure", "specific_result"
    timeout: int = 300
    weight: float = 1.0  # Importance of this test case

@dataclass
class ValidationRun:
    run_id: str
    scraper_id: str
    version: int
    test_cases: List[TestCase]
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: ValidationStatus = ValidationStatus.PENDING
    results: List[ExecutionResult] = None
    success_rate: float = 0.0
    overall_success: bool = False
    
    def __post_init__(self):
        if self.results is None:
            self.results = []

class ScraperValidator:
    """Validates scrapers through comprehensive testing"""
    
    def __init__(self):
        self.validation_runs: Dict[str, ValidationRun] = {}
        self.test_case_templates = self._load_test_templates()
    
    def _load_test_templates(self) -> Dict[str, List[TestCase]]:
        """Load predefined test case templates for different actions"""
        
        return {
            "signup": [
                TestCase(
                    name="basic_signup",
                    test_data={
                        "email": "test@example.com",
                        "password": "TestPassword123!",
                        "name": "Test User"
                    },
                    expected_outcome="success",
                    timeout=300,
                    weight=2.0
                ),
                TestCase(
                    name="signup_with_verification",
                    test_data={
                        "email": "verify@example.com",
                        "password": "TestPassword123!",
                        "name": "Verify User",
                        "phone": "+1234567890"
                    },
                    expected_outcome="success",
                    timeout=600,  # Longer for verification
                    weight=1.5
                ),
                TestCase(
                    name="invalid_email_signup",
                    test_data={
                        "email": "invalid-email",
                        "password": "TestPassword123!",
                        "name": "Invalid User"
                    },
                    expected_outcome="failure",
                    timeout=180,
                    weight=0.5
                )
            ],
            "signin": [
                TestCase(
                    name="valid_signin",
                    test_data={
                        "email": "existing@example.com",
                        "password": "CorrectPassword123!"
                    },
                    expected_outcome="success",
                    timeout=180,
                    weight=2.0
                ),
                TestCase(
                    name="signin_with_2fa",
                    test_data={
                        "email": "2fa@example.com",
                        "password": "CorrectPassword123!"
                    },
                    expected_outcome="success",
                    timeout=300,
                    weight=1.5
                ),
                TestCase(
                    name="invalid_credentials",
                    test_data={
                        "email": "wrong@example.com",
                        "password": "WrongPassword"
                    },
                    expected_outcome="failure",
                    timeout=120,
                    weight=0.8
                )
            ],
            "apikey_creation": [
                TestCase(
                    name="create_api_key",
                    test_data={
                        "key_name": "Test API Key",
                        "permissions": ["read", "write"]
                    },
                    expected_outcome="success",
                    timeout=240,
                    weight=2.0
                ),
                TestCase(
                    name="create_limited_key",
                    test_data={
                        "key_name": "Limited Key",
                        "permissions": ["read"]
                    },
                    expected_outcome="success",
                    timeout=240,
                    weight=1.0
                )
            ]
        }
    
    async def validate_scraper(
        self,
        scraper_code: ScraperCode,
        custom_test_cases: Optional[List[TestCase]] = None,
        min_success_rate: float = 0.8
    ) -> ValidationRun:
        """Validate a scraper with comprehensive testing"""
        
        run_id = f"{scraper_code.site_name}_{scraper_code.action_type}_v{scraper_code.version}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        # Determine test cases
        test_cases = custom_test_cases or self._get_default_test_cases(scraper_code.action_type)
        
        validation_run = ValidationRun(
            run_id=run_id,
            scraper_id=f"{scraper_code.site_name}_{scraper_code.action_type}",
            version=scraper_code.version,
            test_cases=test_cases,
            started_at=datetime.utcnow(),
            status=ValidationStatus.RUNNING
        )
        
        self.validation_runs[run_id] = validation_run
        
        logger.info(f"Starting validation run {run_id} with {len(test_cases)} test cases")
        
        try:
            # Execute all test cases
            validation_run.results = []
            
            for test_case in test_cases:
                logger.info(f"Executing test case: {test_case.name}")
                
                result = await scraper_executor.execute_scraper(
                    scraper_code=scraper_code.content,
                    scraper_id=f"{scraper_code.site_name}_{scraper_code.action_type}",
                    version=scraper_code.version,
                    test_data=test_case.test_data,
                    timeout=test_case.timeout
                )
                
                validation_run.results.append(result)
                
                # Add test case metadata to result
                result.test_case_name = test_case.name
                result.expected_outcome = test_case.expected_outcome
                result.test_weight = test_case.weight
                
                logger.info(f"Test case {test_case.name} completed: {'PASS' if result.success else 'FAIL'}")
            
            # Calculate success metrics
            validation_run.success_rate = self._calculate_success_rate(validation_run)
            validation_run.overall_success = validation_run.success_rate >= min_success_rate
            validation_run.status = ValidationStatus.PASSED if validation_run.overall_success else ValidationStatus.FAILED
            validation_run.completed_at = datetime.utcnow()
            
            logger.info(f"Validation run {run_id} completed: {validation_run.status.value} (success rate: {validation_run.success_rate:.2%})")
            
            return validation_run
            
        except Exception as e:
            logger.error(f"Validation run {run_id} failed: {e}")
            validation_run.status = ValidationStatus.FAILED
            validation_run.completed_at = datetime.utcnow()
            return validation_run
    
    def _get_default_test_cases(self, action_type: str) -> List[TestCase]:
        """Get default test cases for an action type"""
        return self.test_case_templates.get(action_type, [])
    
    def _calculate_success_rate(self, validation_run: ValidationRun) -> float:
        """Calculate weighted success rate"""
        if not validation_run.results:
            return 0.0
        
        total_weight = 0.0
        successful_weight = 0.0
        
        for i, result in enumerate(validation_run.results):
            test_case = validation_run.test_cases[i]
            weight = test_case.weight
            total_weight += weight
            
            # Check if result matches expected outcome
            if self._is_test_successful(result, test_case):
                successful_weight += weight
        
        return successful_weight / total_weight if total_weight > 0 else 0.0
    
    def _is_test_successful(self, result: ExecutionResult, test_case: TestCase) -> bool:
        """Determine if a test result is successful"""
        
        if test_case.expected_outcome == "success":
            return result.success
        elif test_case.expected_outcome == "failure":
            return not result.success
        else:
            # Custom validation logic for specific expected outcomes
            return self._validate_specific_outcome(result, test_case.expected_outcome)
    
    def _validate_specific_outcome(self, result: ExecutionResult, expected: str) -> bool:
        """Validate specific expected outcomes"""
        
        if expected.startswith("contains:"):
            # Check if result contains specific text
            search_text = expected.replace("contains:", "").strip()
            return search_text.lower() in str(result.return_data).lower()
        
        elif expected.startswith("code:"):
            # Check for specific verification code pattern
            code_pattern = expected.replace("code:", "").strip()
            return any(code_pattern in log for log in [result.logs, str(result.return_data)])
        
        elif expected.startswith("redirect:"):
            # Check for specific redirect URL
            redirect_url = expected.replace("redirect:", "").strip()
            return redirect_url in result.logs or redirect_url in str(result.return_data)
        
        return False
    
    async def run_regression_tests(
        self,
        scraper_code: ScraperCode,
        previous_results: List[ValidationRun]
    ) -> ValidationRun:
        """Run regression tests based on previous successful runs"""
        
        # Extract test cases from previous successful runs
        regression_test_cases = []
        
        for prev_run in previous_results:
            if prev_run.overall_success:
                for i, result in enumerate(prev_run.results):
                    if result.success:
                        test_case = prev_run.test_cases[i]
                        regression_test_cases.append(TestCase(
                            name=f"regression_{test_case.name}",
                            test_data=test_case.test_data,
                            expected_outcome="success",
                            timeout=test_case.timeout,
                            weight=1.0
                        ))
        
        if not regression_test_cases:
            logger.warning("No regression test cases found from previous runs")
            return await self.validate_scraper(scraper_code)
        
        logger.info(f"Running regression tests with {len(regression_test_cases)} test cases")
        
        return await self.validate_scraper(
            scraper_code=scraper_code,
            custom_test_cases=regression_test_cases,
            min_success_rate=0.9  # Higher bar for regression tests
        )
    
    async def run_stress_tests(self, scraper_code: ScraperCode) -> ValidationRun:
        """Run stress tests with concurrent executions"""
        
        base_test_cases = self._get_default_test_cases(scraper_code.action_type)
        
        # Create multiple concurrent test cases
        stress_test_cases = []
        for i in range(5):  # Run 5 concurrent instances
            for test_case in base_test_cases:
                stress_test_cases.append(TestCase(
                    name=f"stress_{i}_{test_case.name}",
                    test_data=test_case.test_data.copy(),
                    expected_outcome=test_case.expected_outcome,
                    timeout=test_case.timeout,
                    weight=0.2  # Lower weight for stress tests
                ))
        
        logger.info(f"Running stress tests with {len(stress_test_cases)} concurrent test cases")
        
        return await self.validate_scraper(
            scraper_code=scraper_code,
            custom_test_cases=stress_test_cases,
            min_success_rate=0.6  # Lower bar for stress tests
        )
    
    def get_validation_summary(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get validation run summary"""
        
        if run_id not in self.validation_runs:
            return None
        
        run = self.validation_runs[run_id]
        
        test_summaries = []
        for i, result in enumerate(run.results):
            test_case = run.test_cases[i]
            test_summaries.append({
                "name": test_case.name,
                "success": result.success,
                "expected_outcome": test_case.expected_outcome,
                "execution_time": result.execution_time,
                "error_message": result.error_message,
                "weight": test_case.weight
            })
        
        return {
            "run_id": run_id,
            "scraper_id": run.scraper_id,
            "version": run.version,
            "status": run.status.value,
            "success_rate": run.success_rate,
            "overall_success": run.overall_success,
            "started_at": run.started_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "test_cases": test_summaries,
            "total_tests": len(run.test_cases),
            "passed_tests": sum(1 for r in run.results if r.success),
            "failed_tests": sum(1 for r in run.results if not r.success)
        }
    
    def get_validation_history(self, scraper_id: str) -> List[Dict[str, Any]]:
        """Get validation history for a scraper"""
        
        history = []
        for run in self.validation_runs.values():
            if run.scraper_id == scraper_id:
                summary = self.get_validation_summary(run.run_id)
                if summary:
                    history.append(summary)
        
        # Sort by completion time
        history.sort(key=lambda x: x["started_at"], reverse=True)
        return history
    
    async def continuous_validation(self, scraper_code: ScraperCode, interval_hours: int = 24):
        """Run continuous validation checks"""
        
        logger.info(f"Starting continuous validation for {scraper_code.site_name}_{scraper_code.action_type}")
        
        while True:
            try:
                # Run validation
                validation_run = await self.validate_scraper(scraper_code)
                
                # If validation fails, alert
                if not validation_run.overall_success:
                    logger.warning(f"Continuous validation failed for {scraper_code.site_name}_{scraper_code.action_type}: {validation_run.success_rate:.2%}")
                    # TODO: Send alert/notification
                
                # Wait for next interval
                await asyncio.sleep(interval_hours * 3600)
                
            except Exception as e:
                logger.error(f"Continuous validation error: {e}")
                await asyncio.sleep(3600)  # Wait 1 hour on error

# Performance benchmarking
class PerformanceBenchmark:
    """Benchmark scraper performance metrics"""
    
    def __init__(self):
        self.benchmarks: Dict[str, List[Dict[str, Any]]] = {}
    
    def record_performance(self, scraper_id: str, result: ExecutionResult):
        """Record performance metrics"""
        
        if scraper_id not in self.benchmarks:
            self.benchmarks[scraper_id] = []
        
        self.benchmarks[scraper_id].append({
            "timestamp": datetime.utcnow().isoformat(),
            "execution_time": result.execution_time,
            "success": result.success,
            "version": result.version
        })
        
        # Keep only last 100 records
        self.benchmarks[scraper_id] = self.benchmarks[scraper_id][-100:]
    
    def get_performance_stats(self, scraper_id: str) -> Dict[str, Any]:
        """Get performance statistics"""
        
        if scraper_id not in self.benchmarks:
            return {}
        
        records = self.benchmarks[scraper_id]
        successful_records = [r for r in records if r["success"]]
        
        if not records:
            return {}
        
        execution_times = [r["execution_time"] for r in successful_records]
        
        return {
            "total_runs": len(records),
            "successful_runs": len(successful_records),
            "success_rate": len(successful_records) / len(records),
            "avg_execution_time": sum(execution_times) / len(execution_times) if execution_times else 0,
            "min_execution_time": min(execution_times) if execution_times else 0,
            "max_execution_time": max(execution_times) if execution_times else 0,
            "latest_version": max(r["version"] for r in records)
        }

# Global instances
validator = ScraperValidator()
performance_benchmark = PerformanceBenchmark() 