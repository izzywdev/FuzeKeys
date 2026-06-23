#!/usr/bin/env python3
"""
Complete LLM-Driven Scraper Generation Workflow Demo

This script demonstrates the entire process:
1. Generate initial scraper using LLM
2. Execute and test scraper
3. Iteratively improve based on failures  
4. Deploy to production when ready
5. Monitor and maintain in production

Usage: python demo_complete_workflow.py
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any

# Import our LLM scraper system components
from backend.app.llm_scraper_service.llm_integration.code_generator import code_generator
from backend.app.llm_scraper_service.llm_integration.prompt_templates import SiteInfo
from backend.app.llm_scraper_service.scraper_engine.executor import scraper_executor
from backend.app.llm_scraper_service.iteration_framework.validation_system import validator
from backend.app.llm_scraper_service.iteration_framework.improvement_engine import improvement_engine

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ScraperWorkflowDemo:
    """Demo class for the complete scraper generation workflow"""
    
    def __init__(self):
        self.demo_sites = {
            "github": {
                "name": "github",
                "url": "https://github.com/signup",
                "action_type": "signup",
                "patterns": {
                    "email_field": "#user_email",
                    "password_field": "#user_password",
                    "username_field": "#user_login"
                },
                "test_data": {
                    "email": "demo@example.com",
                    "password": "DemoPassword123!",
                    "username": "demo_user_12345"
                }
            },
            "google": {
                "name": "google",
                "url": "https://accounts.google.com/signup",
                "action_type": "signup",
                "patterns": {
                    "email_field": "#identifierId",
                    "password_field": "[name='password']",
                    "next_button": "#identifierNext"
                },
                "test_data": {
                    "email": "demo@gmail.com",
                    "password": "DemoPassword123!"
                }
            }
        }
    
    async def run_complete_demo(self, site_name: str = "github"):
        """Run the complete workflow for a site"""
        
        logger.info("🚀 Starting Complete LLM-Driven Scraper Generation Demo")
        logger.info(f"Target Site: {site_name}")
        
        try:
            # Step 1: Generate Initial Scraper
            scraper_code = await self.step1_generate_initial_scraper(site_name)
            if not scraper_code:
                return
            
            # Step 2: Execute and Test
            validation_result = await self.step2_execute_and_test(scraper_code)
            
            # Step 3: Iterative Improvement (if needed)
            if not validation_result.overall_success:
                scraper_code = await self.step3_iterative_improvement(scraper_code)
                if not scraper_code:
                    return
            
            # Step 4: Deploy to Production
            production_release = await self.step4_deploy_to_production(scraper_code)
            
            # Step 5: Monitor and Maintain
            await self.step5_monitoring_demo(scraper_code)
            
            logger.info("✅ Complete workflow demo finished successfully!")
            
        except Exception as e:
            logger.error(f"❌ Demo failed: {e}")
    
    async def step1_generate_initial_scraper(self, site_name: str):
        """Step 1: Generate initial scraper using LLM"""
        
        logger.info("\n" + "="*50)
        logger.info("STEP 1: GENERATE INITIAL SCRAPER")
        logger.info("="*50)
        
        site_config = self.demo_sites.get(site_name)
        if not site_config:
            logger.error(f"Site {site_name} not configured for demo")
            return None
        
        # Create site info
        site_info = SiteInfo(
            name=site_config["name"],
            url=site_config["url"],
            action_type=site_config["action_type"],
            patterns=site_config["patterns"],
            previous_attempts=[],
            test_data=site_config["test_data"]
        )
        
        logger.info(f"🤖 Generating scraper for {site_name} {site_config['action_type']}")
        logger.info(f"🎯 Target URL: {site_config['url']}")
        
        # Generate scraper
        generation_result = await code_generator.generate_initial_scraper(site_info)
        
        if generation_result.success:
            scraper_code = generation_result.scraper_code
            logger.info(f"✅ Scraper generated successfully!")
            logger.info(f"📝 Version: {scraper_code.version}")
            logger.info(f"💰 Cost: ${generation_result.llm_response.cost:.4f}")
            logger.info(f"🔤 Tokens: {generation_result.llm_response.tokens_used}")
            
            # Show code preview
            self._show_code_preview(scraper_code.content)
            
            return scraper_code
        else:
            logger.error(f"❌ Failed to generate scraper: {generation_result.error_message}")
            return None
    
    async def step2_execute_and_test(self, scraper_code):
        """Step 2: Execute and test the scraper"""
        
        logger.info("\n" + "="*50)
        logger.info("STEP 2: EXECUTE AND TEST SCRAPER")
        logger.info("="*50)
        
        logger.info(f"🧪 Running validation tests for {scraper_code.site_name}")
        
        # Run validation
        validation_result = await validator.validate_scraper(
            scraper_code=scraper_code,
            min_success_rate=0.8
        )
        
        logger.info(f"📊 Validation Results:")
        logger.info(f"   Success Rate: {validation_result.success_rate:.1%}")
        logger.info(f"   Overall Success: {validation_result.overall_success}")
        logger.info(f"   Total Tests: {len(validation_result.test_cases)}")
        logger.info(f"   Passed: {sum(1 for r in validation_result.results if r.success)}")
        logger.info(f"   Failed: {sum(1 for r in validation_result.results if not r.success)}")
        
        # Show test details
        for i, result in enumerate(validation_result.results):
            test_case = validation_result.test_cases[i]
            status = "✅ PASS" if result.success else "❌ FAIL"
            logger.info(f"   {test_case.name}: {status} ({result.execution_time:.1f}s)")
            if not result.success and result.error_message:
                logger.info(f"      Error: {result.error_message}")
        
        return validation_result
    
    async def step3_iterative_improvement(self, scraper_code):
        """Step 3: Iteratively improve the scraper"""
        
        logger.info("\n" + "="*50)
        logger.info("STEP 3: ITERATIVE IMPROVEMENT")
        logger.info("="*50)
        
        logger.info(f"🔧 Starting iterative improvement for {scraper_code.site_name}")
        
        # Run improvement process
        improvement_result = await improvement_engine.improve_scraper_iteratively(
            scraper_code=scraper_code,
            max_iterations=3,
            target_success_rate=0.9
        )
        
        if improvement_result.success:
            final_scraper = improvement_result.generation_result.scraper_code
            logger.info(f"✅ Improvement successful!")
            logger.info(f"📈 Final version: {final_scraper.version}")
            logger.info(f"🎯 Final success rate: {improvement_result.validation_result.success_rate:.1%}")
            
            return final_scraper
        else:
            logger.error(f"❌ Improvement failed after maximum iterations")
            return None
    
    async def step4_deploy_to_production(self, scraper_code):
        """Step 4: Deploy to production"""
        
        logger.info("\n" + "="*50)
        logger.info("STEP 4: DEPLOY TO PRODUCTION")
        logger.info("="*50)
        
        logger.info(f"🚀 Deploying {scraper_code.site_name} v{scraper_code.version} to production")
        
        # Deploy to production
        production_release = await improvement_engine.deploy_to_production(scraper_code)
        
        if production_release.deployment_status.value == "production":
            logger.info(f"✅ Successfully deployed to production!")
            logger.info(f"🏷️  Release ID: {production_release.release_id}")
            logger.info(f"📊 Success Rate: {production_release.success_rate:.1%}")
            logger.info(f"⚡ Avg Execution Time: {production_release.performance_metrics.get('avg_execution_time', 0):.1f}s")
        else:
            logger.error(f"❌ Deployment failed: {production_release.performance_metrics.get('error', 'Unknown error')}")
        
        return production_release
    
    async def step5_monitoring_demo(self, scraper_code):
        """Step 5: Show monitoring capabilities"""
        
        logger.info("\n" + "="*50)
        logger.info("STEP 5: MONITORING AND MAINTENANCE")
        logger.info("="*50)
        
        scraper_id = f"{scraper_code.site_name}_{scraper_code.action_type}"
        
        # Show improvement summary
        improvement_summary = improvement_engine.get_improvement_summary(scraper_id)
        
        logger.info(f"📈 Improvement Summary for {scraper_id}:")
        logger.info(f"   Total Iterations: {improvement_summary['total_iterations']}")
        logger.info(f"   Successful Iterations: {improvement_summary['successful_iterations']}")
        logger.info(f"   Total Releases: {improvement_summary['total_releases']}")
        
        if improvement_summary['latest_release']:
            release = improvement_summary['latest_release']
            logger.info(f"   Latest Release:")
            logger.info(f"      Version: {release['version']}")
            logger.info(f"      Status: {release['deployment_status']}")
            logger.info(f"      Success Rate: {release['success_rate']:.1%}")
        
        # Show validation history
        validation_history = validator.get_validation_history(scraper_id)
        logger.info(f"🧪 Validation History: {len(validation_history)} runs")
        
        for run in validation_history[:3]:  # Show last 3
            logger.info(f"   {run['status'].upper()}: {run['success_rate']:.1%} ({run['total_tests']} tests)")
        
        logger.info(f"🔄 Continuous monitoring would run every 24 hours")
        logger.info(f"🔔 Alerts would be sent if success rate drops below 85%")
    
    def _show_code_preview(self, code: str, max_lines: int = 20):
        """Show a preview of the generated code"""
        
        lines = code.split('\n')
        preview_lines = lines[:max_lines]
        
        logger.info(f"📄 Code Preview (showing {len(preview_lines)}/{len(lines)} lines):")
        logger.info("   " + "-" * 50)
        
        for i, line in enumerate(preview_lines, 1):
            logger.info(f"   {i:2d}: {line}")
        
        if len(lines) > max_lines:
            logger.info(f"   ... ({len(lines) - max_lines} more lines)")
        
        logger.info("   " + "-" * 50)
    
    async def demo_infrastructure_apis(self):
        """Demo the infrastructure APIs"""
        
        logger.info("\n" + "="*50)
        logger.info("INFRASTRUCTURE APIS DEMO")
        logger.info("="*50)
        
        logger.info("📱 SMS Verification API:")
        logger.info("   POST /api/infrastructure/sms/request-verification")
        logger.info("   GET  /api/infrastructure/sms/get-verification/{request_id}")
        
        logger.info("📧 Email Monitoring API:")
        logger.info("   POST /api/infrastructure/email/setup-monitoring")
        logger.info("   GET  /api/infrastructure/email/get-verification/{monitor_id}")
        
        logger.info("📱 Mobile Communication API:")
        logger.info("   POST /api/infrastructure/mobile/send-command")
        logger.info("   GET  /api/infrastructure/mobile/get-command-result/{command_id}")
        
        # Demo SMS request (mock)
        logger.info("\n🔄 Mock SMS Verification Request:")
        sms_request = {
            "site": "github",
            "phone_number": "+1234567890",
            "timeout_seconds": 300
        }
        logger.info(f"   Request: {json.dumps(sms_request, indent=2)}")
        
        # Demo Email monitoring (mock)
        logger.info("\n🔄 Mock Email Monitoring Setup:")
        email_request = {
            "email": "demo@example.com",
            "sender_patterns": ["github.com", "noreply@github.com"],
            "subject_patterns": ["verify", "confirmation"],
            "timeout_seconds": 300
        }
        logger.info(f"   Request: {json.dumps(email_request, indent=2)}")

async def main():
    """Main demo function"""
    
    demo = ScraperWorkflowDemo()
    
    print("🎯 LLM-Driven Scraper Generation System Demo")
    print("=" * 60)
    print()
    print("Available demos:")
    print("1. Complete Workflow (GitHub)")
    print("2. Complete Workflow (Google)")
    print("3. Infrastructure APIs Demo")
    print("4. All Demos")
    
    choice = input("\nSelect demo (1-4): ").strip()
    
    if choice == "1":
        await demo.run_complete_demo("github")
    elif choice == "2":
        await demo.run_complete_demo("google")
    elif choice == "3":
        await demo.demo_infrastructure_apis()
    elif choice == "4":
        await demo.demo_infrastructure_apis()
        await demo.run_complete_demo("github")
        await demo.run_complete_demo("google")
    else:
        print("Invalid choice. Running GitHub demo...")
        await demo.run_complete_demo("github")

if __name__ == "__main__":
    # Set environment variables for demo
    import os
    os.environ.setdefault("OPENAI_API_KEY", "demo-key-set-your-real-key")
    os.environ.setdefault("ANTHROPIC_API_KEY", "demo-key-set-your-real-key")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 Demo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc() 