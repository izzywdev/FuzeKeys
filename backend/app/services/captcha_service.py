import asyncio
import base64
import io
import re
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
import logging
import aiohttp
from PIL import Image
import openai
from playwright.async_api import Page, ElementHandle
import cv2
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class CaptchaChallenge:
    """Represents a captcha challenge"""
    challenge_type: str  # 'text', 'image', 'recaptcha', 'hcaptcha', 'audio'
    image_data: Optional[bytes] = None
    image_url: Optional[str] = None
    audio_url: Optional[str] = None
    question: Optional[str] = None
    options: Optional[List[str]] = None
    context: Optional[str] = None
    difficulty: str = "medium"  # 'easy', 'medium', 'hard'

@dataclass
class CaptchaSolution:
    """Represents a captcha solution"""
    solution: str
    confidence: float
    reasoning: Optional[str] = None
    alternative_solutions: Optional[List[str]] = None

class CaptchaSolverService:
    """AI-powered captcha solving service using OpenAI Vision"""
    
    def __init__(self, openai_api_key: str):
        self.openai_client = openai.AsyncOpenAI(api_key=openai_api_key)
        self.max_retries = 3
        self.confidence_threshold = 0.7
        
    async def solve_captcha(self, challenge: CaptchaChallenge) -> Optional[CaptchaSolution]:
        """Solve a captcha challenge using appropriate method"""
        try:
            if challenge.challenge_type == 'text':
                return await self._solve_text_captcha(challenge)
            elif challenge.challenge_type == 'image':
                return await self._solve_image_captcha(challenge)
            elif challenge.challenge_type == 'recaptcha':
                return await self._solve_recaptcha(challenge)
            elif challenge.challenge_type == 'hcaptcha':
                return await self._solve_hcaptcha(challenge)
            elif challenge.challenge_type == 'audio':
                return await self._solve_audio_captcha(challenge)
            else:
                logger.warning(f"Unknown captcha type: {challenge.challenge_type}")
                return None
                
        except Exception as e:
            logger.error(f"Error solving captcha: {e}")
            return None
    
    async def _solve_text_captcha(self, challenge: CaptchaChallenge) -> Optional[CaptchaSolution]:
        """Solve text-based captcha using vision model"""
        if not challenge.image_data and not challenge.image_url:
            return None
        
        try:
            # Prepare image for analysis
            image_base64 = await self._prepare_image(challenge.image_data, challenge.image_url)
            if not image_base64:
                return None
            
            # Enhanced prompt for text extraction
            prompt = """You are an expert at reading distorted text in CAPTCHA images. 
            
            Analyze this CAPTCHA image and extract the text characters. The text may be:
            - Distorted, skewed, or rotated
            - Have noise, lines, or patterns overlaid
            - Use unusual fonts or styling
            - Contain numbers, letters, or both
            - Case sensitive or insensitive
            
            Instructions:
            1. Look carefully at each character
            2. Ignore background noise and distracting elements
            3. Focus on the main text that needs to be read
            4. Provide only the clean text without spaces unless clearly intended
            5. If unsure about a character, provide your best guess
            
            Response format:
            TEXT: [extracted text]
            CONFIDENCE: [0.0-1.0]
            REASONING: [brief explanation of what you see]
            """
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{image_base64}"}
                            }
                        ]
                    }
                ],
                max_tokens=300
            )
            
            content = response.choices[0].message.content
            return self._parse_solution_response(content)
            
        except Exception as e:
            logger.error(f"Error solving text captcha: {e}")
            return None
    
    async def _solve_image_captcha(self, challenge: CaptchaChallenge) -> Optional[CaptchaSolution]:
        """Solve image selection captcha (like 'select all traffic lights')"""
        if not challenge.image_data and not challenge.image_url:
            return None
        
        try:
            image_base64 = await self._prepare_image(challenge.image_data, challenge.image_url)
            if not image_base64:
                return None
            
            # Build prompt based on challenge question
            question = challenge.question or "Select all relevant images"
            
            prompt = f"""You are an expert at solving image selection CAPTCHAs.
            
            Task: {question}
            
            Analyze this CAPTCHA image which is typically a grid of images (usually 3x3 or 4x4).
            
            Instructions:
            1. Identify what object/concept you need to find based on the question
            2. Look at each grid square carefully
            3. Determine which squares contain the requested object
            4. Number the squares from left to right, top to bottom (1, 2, 3, etc.)
            5. Only select squares that clearly contain the requested object
            
            Common objects to identify:
            - Traffic lights, cars, buses, bicycles
            - Crosswalks, bridges, stairs
            - Fire hydrants, parking meters
            - Trees, mountains, water
            - Buildings, storefronts
            
            Response format:
            SQUARES: [comma-separated list of square numbers, e.g., "1,3,5,7"]
            CONFIDENCE: [0.0-1.0]
            REASONING: [explain what you see in each selected square]
            """
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{image_base64}"}
                            }
                        ]
                    }
                ],
                max_tokens=500
            )
            
            content = response.choices[0].message.content
            return self._parse_solution_response(content)
            
        except Exception as e:
            logger.error(f"Error solving image captcha: {e}")
            return None
    
    async def _solve_recaptcha(self, challenge: CaptchaChallenge) -> Optional[CaptchaSolution]:
        """Solve reCAPTCHA challenges"""
        # reCAPTCHA v2 invisible often requires just clicking the checkbox
        # For image challenges, delegate to image captcha solver
        if challenge.image_data or challenge.image_url:
            challenge.challenge_type = 'image'
            return await self._solve_image_captcha(challenge)
        
        # For checkbox reCAPTCHA, return indication to click
        return CaptchaSolution(
            solution="click_checkbox",
            confidence=0.9,
            reasoning="Standard reCAPTCHA checkbox interaction"
        )
    
    async def _solve_hcaptcha(self, challenge: CaptchaChallenge) -> Optional[CaptchaSolution]:
        """Solve hCaptcha challenges"""
        # Similar to reCAPTCHA but typically more image-based
        if challenge.image_data or challenge.image_url:
            challenge.challenge_type = 'image'
            return await self._solve_image_captcha(challenge)
        
        return None
    
    async def _solve_audio_captcha(self, challenge: CaptchaChallenge) -> Optional[CaptchaSolution]:
        """Solve audio captcha (placeholder - requires speech recognition)"""
        # TODO: Implement audio captcha solving using speech recognition
        logger.warning("Audio captcha solving not yet implemented")
        return None
    
    async def _prepare_image(self, image_data: Optional[bytes], image_url: Optional[str]) -> Optional[str]:
        """Prepare image for OpenAI Vision API"""
        try:
            if image_data:
                # Convert bytes to base64
                return base64.b64encode(image_data).decode('utf-8')
            elif image_url:
                # Download image and convert to base64
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as response:
                        if response.status == 200:
                            image_bytes = await response.read()
                            return base64.b64encode(image_bytes).decode('utf-8')
            
            return None
            
        except Exception as e:
            logger.error(f"Error preparing image: {e}")
            return None
    
    def _parse_solution_response(self, content: str) -> Optional[CaptchaSolution]:
        """Parse the LLM response into a structured solution"""
        try:
            lines = content.strip().split('\n')
            solution = ""
            confidence = 0.5
            reasoning = ""
            
            for line in lines:
                if line.startswith('TEXT:') or line.startswith('SQUARES:'):
                    solution = line.split(':', 1)[1].strip()
                elif line.startswith('CONFIDENCE:'):
                    try:
                        confidence = float(line.split(':', 1)[1].strip())
                    except ValueError:
                        confidence = 0.5
                elif line.startswith('REASONING:'):
                    reasoning = line.split(':', 1)[1].strip()
            
            if not solution:
                # Fallback: try to extract any meaningful text
                solution = content.strip()
            
            return CaptchaSolution(
                solution=solution,
                confidence=confidence,
                reasoning=reasoning
            )
            
        except Exception as e:
            logger.error(f"Error parsing solution response: {e}")
            return None

class CaptchaDetector:
    """Detects captchas on web pages"""
    
    @staticmethod
    async def detect_captcha(page: Page) -> Optional[CaptchaChallenge]:
        """Detect captcha on the current page"""
        try:
            # Check for reCAPTCHA
            recaptcha = await page.query_selector('.g-recaptcha, #recaptcha, [data-recaptcha]')
            if recaptcha:
                return await CaptchaDetector._analyze_recaptcha(page, recaptcha)
            
            # Check for hCaptcha
            hcaptcha = await page.query_selector('.h-captcha, #hcaptcha, [data-hcaptcha]')
            if hcaptcha:
                return await CaptchaDetector._analyze_hcaptcha(page, hcaptcha)
            
            # Check for generic captcha images
            captcha_imgs = await page.query_selector_all('img[src*="captcha"], img[alt*="captcha"], .captcha img')
            if captcha_imgs:
                return await CaptchaDetector._analyze_image_captcha(page, captcha_imgs[0])
            
            # Check for text-based captcha
            captcha_inputs = await page.query_selector_all('input[name*="captcha"], input[id*="captcha"], input[placeholder*="captcha"]')
            if captcha_inputs:
                return await CaptchaDetector._analyze_text_captcha(page, captcha_inputs[0])
            
            return None
            
        except Exception as e:
            logger.error(f"Error detecting captcha: {e}")
            return None
    
    @staticmethod
    async def _analyze_recaptcha(page: Page, element: ElementHandle) -> Optional[CaptchaChallenge]:
        """Analyze reCAPTCHA element"""
        try:
            # Check if it's the checkbox or image challenge
            checkbox = await page.query_selector('.recaptcha-checkbox')
            if checkbox:
                return CaptchaChallenge(
                    challenge_type='recaptcha',
                    question='Click the checkbox to verify you are human',
                    difficulty='easy'
                )
            
            # Look for image challenge
            challenge_img = await page.query_selector('.rc-image-tile-wrapper img, .rc-imageselect-payload img')
            if challenge_img:
                img_src = await challenge_img.get_attribute('src')
                question_elem = await page.query_selector('.rc-imageselect-desc-no-canonical, .rc-imageselect-desc')
                question = await question_elem.text_content() if question_elem else None
                
                return CaptchaChallenge(
                    challenge_type='recaptcha',
                    image_url=img_src,
                    question=question,
                    difficulty='medium'
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing reCAPTCHA: {e}")
            return None
    
    @staticmethod
    async def _analyze_hcaptcha(page: Page, element: ElementHandle) -> Optional[CaptchaChallenge]:
        """Analyze hCaptcha element"""
        try:
            # Look for hCaptcha challenge
            challenge_img = await page.query_selector('.challenge-image, .prompt img')
            if challenge_img:
                img_src = await challenge_img.get_attribute('src')
                question_elem = await page.query_selector('.challenge-text, .prompt-text')
                question = await question_elem.text_content() if question_elem else None
                
                return CaptchaChallenge(
                    challenge_type='hcaptcha',
                    image_url=img_src,
                    question=question,
                    difficulty='medium'
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing hCaptcha: {e}")
            return None
    
    @staticmethod
    async def _analyze_image_captcha(page: Page, img_element: ElementHandle) -> Optional[CaptchaChallenge]:
        """Analyze generic image captcha"""
        try:
            img_src = await img_element.get_attribute('src')
            
            # Look for associated question text
            parent = await img_element.query_selector('xpath=..')
            question_elem = await parent.query_selector('label, .question, .instruction') if parent else None
            question = await question_elem.text_content() if question_elem else "Enter the text shown in the image"
            
            return CaptchaChallenge(
                challenge_type='text',
                image_url=img_src,
                question=question,
                difficulty='medium'
            )
            
        except Exception as e:
            logger.error(f"Error analyzing image captcha: {e}")
            return None
    
    @staticmethod
    async def _analyze_text_captcha(page: Page, input_element: ElementHandle) -> Optional[CaptchaChallenge]:
        """Analyze text input captcha"""
        try:
            # Look for associated captcha image
            parent = await input_element.query_selector('xpath=..')
            img_elem = await parent.query_selector('img') if parent else None
            
            if img_elem:
                img_src = await img_elem.get_attribute('src')
                placeholder = await input_element.get_attribute('placeholder')
                
                return CaptchaChallenge(
                    challenge_type='text',
                    image_url=img_src,
                    question=placeholder or "Enter the text shown in the image",
                    difficulty='medium'
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing text captcha: {e}")
            return None

class CaptchaHandler:
    """High-level captcha handling orchestrator"""
    
    def __init__(self, captcha_solver: CaptchaSolverService):
        self.solver = captcha_solver
        self.detector = CaptchaDetector()
    
    async def handle_page_captcha(self, page: Page) -> bool:
        """Detect and solve captcha on a page"""
        try:
            # Detect captcha
            challenge = await self.detector.detect_captcha(page)
            if not challenge:
                return True  # No captcha found
            
            logger.info(f"Found {challenge.challenge_type} captcha: {challenge.question}")
            
            # Solve captcha
            solution = await self.solver.solve_captcha(challenge)
            if not solution or solution.confidence < self.solver.confidence_threshold:
                logger.warning(f"Could not solve captcha with sufficient confidence: {solution.confidence if solution else 0}")
                return False
            
            logger.info(f"Solved captcha: {solution.solution} (confidence: {solution.confidence})")
            
            # Apply solution
            success = await self._apply_solution(page, challenge, solution)
            if success:
                logger.info("Successfully applied captcha solution")
                # Wait for page to process the solution
                await asyncio.sleep(2)
            
            return success
            
        except Exception as e:
            logger.error(f"Error handling page captcha: {e}")
            return False
    
    async def _apply_solution(self, page: Page, challenge: CaptchaChallenge, solution: CaptchaSolution) -> bool:
        """Apply the captcha solution to the page"""
        try:
            if challenge.challenge_type == 'text':
                # Find captcha input and enter solution
                captcha_input = await page.query_selector('input[name*="captcha"], input[id*="captcha"], input[placeholder*="captcha"]')
                if captcha_input:
                    await captcha_input.fill(solution.solution)
                    return True
            
            elif challenge.challenge_type == 'recaptcha':
                if solution.solution == 'click_checkbox':
                    # Click reCAPTCHA checkbox
                    checkbox = await page.query_selector('.recaptcha-checkbox')
                    if checkbox:
                        await checkbox.click()
                        return True
                else:
                    # Handle image selection
                    squares = solution.solution.replace('SQUARES:', '').strip().split(',')
                    for square_num in squares:
                        try:
                            square_index = int(square_num.strip()) - 1
                            tiles = await page.query_selector_all('.rc-image-tile-wrapper')
                            if square_index < len(tiles):
                                await tiles[square_index].click()
                        except (ValueError, IndexError):
                            continue
                    
                    # Click verify button
                    verify_button = await page.query_selector('#recaptcha-verify-button')
                    if verify_button:
                        await verify_button.click()
                    
                    return True
            
            elif challenge.challenge_type == 'hcaptcha':
                # Similar to reCAPTCHA image handling
                squares = solution.solution.replace('SQUARES:', '').strip().split(',')
                for square_num in squares:
                    try:
                        square_index = int(square_num.strip()) - 1
                        tiles = await page.query_selector_all('.challenge-image')
                        if square_index < len(tiles):
                            await tiles[square_index].click()
                    except (ValueError, IndexError):
                        continue
                
                # Click submit button
                submit_button = await page.query_selector('.hcaptcha-submit, [aria-label="Submit"]')
                if submit_button:
                    await submit_button.click()
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error applying captcha solution: {e}")
            return False 