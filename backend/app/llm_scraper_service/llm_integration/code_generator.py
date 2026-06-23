"""
Code generator for LLM-driven scraper creation
"""

import os
import logging
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from .llm_client import llm_manager, LLMResponse
from .prompt_templates import PromptTemplates, SiteInfo

logger = logging.getLogger(__name__)

@dataclass
class ScraperCode:
    content: str
    version: int
    site_name: str
    action_type: str
    created_at: datetime
    parent_version: Optional[int] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

@dataclass
class GenerationResult:
    success: bool
    scraper_code: Optional[ScraperCode] = None
    error_message: Optional[str] = None
    llm_response: Optional[LLMResponse] = None

class ScraperCodeGenerator:
    """Main class for generating and improving scraper code using LLMs"""
    
    def __init__(self):
        self.generation_history: Dict[str, List[ScraperCode]] = {}
        self.templates = PromptTemplates()
    
    async def generate_initial_scraper(self, site_info: SiteInfo) -> GenerationResult:
        """Generate initial scraper code for a site"""
        try:
            logger.info(f"Generating initial scraper for {site_info.name} {site_info.action_type}")
            
            # Build generation prompt
            prompt = self.templates.build_generation_prompt(site_info)
            
            # Generate code using LLM
            llm_response = await llm_manager.generate_code(
                prompt=prompt,
                temperature=0.1,
                max_tokens=4000
            )
            
            if not llm_response.success:
                return GenerationResult(
                    success=False,
                    error_message=f"LLM generation failed: {llm_response.error_message}",
                    llm_response=llm_response
                )
            
            # Create scraper code object
            scraper_code = ScraperCode(
                content=llm_response.content,
                version=1,
                site_name=site_info.name,
                action_type=site_info.action_type,
                created_at=datetime.utcnow(),
                metadata={
                    "site_url": site_info.url,
                    "patterns": site_info.patterns,
                    "test_data": site_info.test_data,
                    "llm_model": llm_response.model,
                    "tokens_used": llm_response.tokens_used,
                    "cost": llm_response.cost
                }
            )
            
            # Store in history
            scraper_id = f"{site_info.name}_{site_info.action_type}"
            if scraper_id not in self.generation_history:
                self.generation_history[scraper_id] = []
            self.generation_history[scraper_id].append(scraper_code)
            
            # Save to file
            await self._save_scraper_code(scraper_code)
            
            logger.info(f"Successfully generated initial scraper for {site_info.name}")
            
            return GenerationResult(
                success=True,
                scraper_code=scraper_code,
                llm_response=llm_response
            )
            
        except Exception as e:
            logger.error(f"Error generating initial scraper: {e}")
            return GenerationResult(
                success=False,
                error_message=str(e)
            )
    
    async def improve_scraper(self, scraper_code: ScraperCode, execution_result: Dict[str, Any]) -> GenerationResult:
        """Improve existing scraper based on execution results"""
        try:
            logger.info(f"Improving scraper {scraper_code.site_name} v{scraper_code.version}")
            
            # If execution was successful, no improvement needed
            if execution_result.get("success", False):
                logger.info("Scraper execution was successful, no improvement needed")
                return GenerationResult(
                    success=True,
                    scraper_code=scraper_code
                )
            
            # Build iteration prompt
            prompt = self.templates.build_iteration_prompt(
                previous_code=scraper_code.content,
                execution_result=execution_result
            )
            
            # Generate improved code using LLM
            llm_response = await llm_manager.improve_code(
                prompt=prompt,
                temperature=0.1,
                max_tokens=4000
            )
            
            if not llm_response.success:
                return GenerationResult(
                    success=False,
                    error_message=f"LLM improvement failed: {llm_response.error_message}",
                    llm_response=llm_response
                )
            
            # Create improved scraper code object
            improved_code = ScraperCode(
                content=llm_response.content,
                version=scraper_code.version + 1,
                site_name=scraper_code.site_name,
                action_type=scraper_code.action_type,
                created_at=datetime.utcnow(),
                parent_version=scraper_code.version,
                metadata={
                    **scraper_code.metadata,
                    "improvement_reason": execution_result.get("error_message", ""),
                    "llm_model": llm_response.model,
                    "tokens_used": llm_response.tokens_used,
                    "cost": llm_response.cost,
                    "execution_result": execution_result
                }
            )
            
            # Store in history
            scraper_id = f"{scraper_code.site_name}_{scraper_code.action_type}"
            self.generation_history[scraper_id].append(improved_code)
            
            # Save to file
            await self._save_scraper_code(improved_code)
            
            logger.info(f"Successfully improved scraper to v{improved_code.version}")
            
            return GenerationResult(
                success=True,
                scraper_code=improved_code,
                llm_response=llm_response
            )
            
        except Exception as e:
            logger.error(f"Error improving scraper: {e}")
            return GenerationResult(
                success=False,
                error_message=str(e)
            )
    
    async def debug_scraper(self, scraper_code: ScraperCode, error: str, context: Dict[str, Any]) -> GenerationResult:
        """Debug specific issues in scraper code"""
        try:
            logger.info(f"Debugging scraper {scraper_code.site_name} v{scraper_code.version}")
            
            # Build debugging prompt
            prompt = self.templates.build_debugging_prompt(
                code=scraper_code.content,
                error=error,
                context=context
            )
            
            # Generate debugged code using LLM
            llm_response = await llm_manager.improve_code(
                prompt=prompt,
                temperature=0.05,  # Lower temperature for debugging
                max_tokens=4000
            )
            
            if not llm_response.success:
                return GenerationResult(
                    success=False,
                    error_message=f"LLM debugging failed: {llm_response.error_message}",
                    llm_response=llm_response
                )
            
            # Create debugged scraper code object
            debugged_code = ScraperCode(
                content=llm_response.content,
                version=scraper_code.version + 1,
                site_name=scraper_code.site_name,
                action_type=scraper_code.action_type,
                created_at=datetime.utcnow(),
                parent_version=scraper_code.version,
                metadata={
                    **scraper_code.metadata,
                    "debug_reason": error,
                    "debug_context": context,
                    "llm_model": llm_response.model,
                    "tokens_used": llm_response.tokens_used,
                    "cost": llm_response.cost
                }
            )
            
            # Store in history
            scraper_id = f"{scraper_code.site_name}_{scraper_code.action_type}"
            if scraper_id not in self.generation_history:
                self.generation_history[scraper_id] = []
            self.generation_history[scraper_id].append(debugged_code)
            
            # Save to file
            await self._save_scraper_code(debugged_code)
            
            logger.info(f"Successfully debugged scraper to v{debugged_code.version}")
            
            return GenerationResult(
                success=True,
                scraper_code=debugged_code,
                llm_response=llm_response
            )
            
        except Exception as e:
            logger.error(f"Error debugging scraper: {e}")
            return GenerationResult(
                success=False,
                error_message=str(e)
            )
    
    async def _save_scraper_code(self, scraper_code: ScraperCode):
        """Save scraper code to file system"""
        try:
            # Create directory structure
            base_dir = "backend/app/dynamic_scrapers/generated"
            site_dir = os.path.join(base_dir, scraper_code.site_name)
            os.makedirs(site_dir, exist_ok=True)
            
            # Generate filename
            filename = f"{scraper_code.site_name}_{scraper_code.action_type}_v{scraper_code.version}.py"
            filepath = os.path.join(site_dir, filename)
            
            # Save code file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(scraper_code.content)
            
            # Save metadata
            metadata_filename = f"{scraper_code.site_name}_{scraper_code.action_type}_v{scraper_code.version}_metadata.json"
            metadata_filepath = os.path.join(site_dir, metadata_filename)
            
            metadata = {
                "version": scraper_code.version,
                "site_name": scraper_code.site_name,
                "action_type": scraper_code.action_type,
                "created_at": scraper_code.created_at.isoformat(),
                "parent_version": scraper_code.parent_version,
                "metadata": scraper_code.metadata
            }
            
            with open(metadata_filepath, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            
            logger.info(f"Saved scraper code to {filepath}")
            
        except Exception as e:
            logger.error(f"Error saving scraper code: {e}")
            raise
    
    def get_latest_scraper(self, site_name: str, action_type: str) -> Optional[ScraperCode]:
        """Get the latest version of a scraper"""
        scraper_id = f"{site_name}_{action_type}"
        if scraper_id in self.generation_history:
            return self.generation_history[scraper_id][-1]
        return None
    
    def get_scraper_history(self, site_name: str, action_type: str) -> List[ScraperCode]:
        """Get the full history of a scraper"""
        scraper_id = f"{site_name}_{action_type}"
        return self.generation_history.get(scraper_id, [])
    
    def get_generation_stats(self) -> Dict[str, Any]:
        """Get statistics about code generation"""
        total_scrapers = len(self.generation_history)
        total_versions = sum(len(versions) for versions in self.generation_history.values())
        
        stats = {
            "total_scrapers": total_scrapers,
            "total_versions": total_versions,
            "scrapers": {}
        }
        
        for scraper_id, versions in self.generation_history.items():
            latest = versions[-1]
            stats["scrapers"][scraper_id] = {
                "latest_version": latest.version,
                "total_versions": len(versions),
                "created_at": latest.created_at.isoformat(),
                "site_name": latest.site_name,
                "action_type": latest.action_type
            }
        
        return stats
    
    async def load_existing_scrapers(self):
        """Load existing scrapers from file system"""
        try:
            base_dir = "backend/app/dynamic_scrapers/generated"
            if not os.path.exists(base_dir):
                return
            
            for site_name in os.listdir(base_dir):
                site_dir = os.path.join(base_dir, site_name)
                if not os.path.isdir(site_dir):
                    continue
                
                # Load metadata files
                for filename in os.listdir(site_dir):
                    if filename.endswith("_metadata.json"):
                        metadata_path = os.path.join(site_dir, filename)
                        code_filename = filename.replace("_metadata.json", ".py")
                        code_path = os.path.join(site_dir, code_filename)
                        
                        if os.path.exists(code_path):
                            # Load metadata
                            with open(metadata_path, 'r', encoding='utf-8') as f:
                                metadata = json.load(f)
                            
                            # Load code
                            with open(code_path, 'r', encoding='utf-8') as f:
                                code_content = f.read()
                            
                            # Create scraper code object
                            scraper_code = ScraperCode(
                                content=code_content,
                                version=metadata["version"],
                                site_name=metadata["site_name"],
                                action_type=metadata["action_type"],
                                created_at=datetime.fromisoformat(metadata["created_at"]),
                                parent_version=metadata.get("parent_version"),
                                metadata=metadata.get("metadata", {})
                            )
                            
                            # Add to history
                            scraper_id = f"{scraper_code.site_name}_{scraper_code.action_type}"
                            if scraper_id not in self.generation_history:
                                self.generation_history[scraper_id] = []
                            self.generation_history[scraper_id].append(scraper_code)
            
            # Sort versions for each scraper
            for scraper_id in self.generation_history:
                self.generation_history[scraper_id].sort(key=lambda x: x.version)
            
            logger.info(f"Loaded {len(self.generation_history)} existing scrapers")
            
        except Exception as e:
            logger.error(f"Error loading existing scrapers: {e}")

# Global code generator instance
code_generator = ScraperCodeGenerator() 