import os
import json
import logging
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
import openai
import anthropic
import requests

logger = logging.getLogger(__name__)

# PII/secret tokenization for the LLM data path is provided by the standalone
# `pii-tokenizer/` stack (Presidio + Vault + Redis behind a LiteLLM proxy). To
# route prompts through it so the upstream model only ever sees opaque tokens,
# set LITELLM_PROXY_URL (e.g. http://localhost:4000) and point the provider keys
# at the proxy's master key. When unset, clients call the providers directly.
LITELLM_PROXY_URL = os.getenv("LITELLM_PROXY_URL")

class LLMProvider(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"

@dataclass
class LLMResponse:
    content: str
    model: str
    tokens_used: int
    cost: float
    success: bool
    error_message: Optional[str] = None

class BaseLLMClient(ABC):
    """Abstract base class for LLM clients"""
    
    @abstractmethod
    async def generate_code(self, prompt: str, **kwargs) -> LLMResponse:
        """Generate code using the LLM"""
        pass
    
    @abstractmethod
    async def improve_code(self, prompt: str, **kwargs) -> LLMResponse:
        """Improve existing code using the LLM"""
        pass

class OpenAIClient(BaseLLMClient):
    """OpenAI GPT client for code generation"""
    
    def __init__(self, api_key: str, model: str = "gpt-4", base_url: Optional[str] = None):
        # base_url routes through the pii-tokenizer LiteLLM proxy when configured.
        self.client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.cost_per_token = {
            "gpt-4": {"input": 0.03/1000, "output": 0.06/1000},
            "gpt-4-turbo": {"input": 0.01/1000, "output": 0.03/1000},
            "gpt-3.5-turbo": {"input": 0.0015/1000, "output": 0.002/1000}
        }
    
    async def generate_code(self, prompt: str, **kwargs) -> LLMResponse:
        """Generate code using OpenAI GPT"""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert web automation engineer. Generate clean, production-ready Python code for web scraping and automation."},
                    {"role": "user", "content": prompt}
                ],
                temperature=kwargs.get("temperature", 0.1),
                max_tokens=kwargs.get("max_tokens", 4000)
            )
            
            content = response.choices[0].message.content
            tokens_used = response.usage.total_tokens
            cost = self._calculate_cost(tokens_used, response.usage.prompt_tokens, response.usage.completion_tokens)
            
            return LLMResponse(
                content=content,
                model=self.model,
                tokens_used=tokens_used,
                cost=cost,
                success=True
            )
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return LLMResponse(
                content="",
                model=self.model,
                tokens_used=0,
                cost=0.0,
                success=False,
                error_message=str(e)
            )
    
    async def improve_code(self, prompt: str, **kwargs) -> LLMResponse:
        """Improve existing code using OpenAI GPT"""
        return await self.generate_code(prompt, **kwargs)
    
    def _calculate_cost(self, total_tokens: int, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost based on token usage"""
        if self.model not in self.cost_per_token:
            return 0.0
        
        rates = self.cost_per_token[self.model]
        return (input_tokens * rates["input"]) + (output_tokens * rates["output"])

class AnthropicClient(BaseLLMClient):
    """Anthropic Claude client for code generation"""
    
    def __init__(self, api_key: str, model: str = "claude-3-sonnet-20240229", base_url: Optional[str] = None):
        # base_url routes through the pii-tokenizer LiteLLM proxy when configured.
        self.client = anthropic.AsyncAnthropic(api_key=api_key, base_url=base_url)
        self.model = model
        self.cost_per_token = {
            "claude-3-opus-20240229": {"input": 0.015/1000, "output": 0.075/1000},
            "claude-3-sonnet-20240229": {"input": 0.003/1000, "output": 0.015/1000},
            "claude-3-haiku-20240307": {"input": 0.00025/1000, "output": 0.00125/1000}
        }
    
    async def generate_code(self, prompt: str, **kwargs) -> LLMResponse:
        """Generate code using Anthropic Claude"""
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=kwargs.get("max_tokens", 4000),
                temperature=kwargs.get("temperature", 0.1),
                system="You are an expert web automation engineer. Generate clean, production-ready Python code for web scraping and automation.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            content = response.content[0].text
            tokens_used = response.usage.input_tokens + response.usage.output_tokens
            cost = self._calculate_cost(response.usage.input_tokens, response.usage.output_tokens)
            
            return LLMResponse(
                content=content,
                model=self.model,
                tokens_used=tokens_used,
                cost=cost,
                success=True
            )
            
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            return LLMResponse(
                content="",
                model=self.model,
                tokens_used=0,
                cost=0.0,
                success=False,
                error_message=str(e)
            )
    
    async def improve_code(self, prompt: str, **kwargs) -> LLMResponse:
        """Improve existing code using Anthropic Claude"""
        return await self.generate_code(prompt, **kwargs)
    
    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost based on token usage"""
        if self.model not in self.cost_per_token:
            return 0.0
        
        rates = self.cost_per_token[self.model]
        return (input_tokens * rates["input"]) + (output_tokens * rates["output"])

class LocalLLMClient(BaseLLMClient):
    """Local LLM client (e.g., Ollama, local API)"""
    
    def __init__(self, base_url: str, model: str = "codellama"):
        self.base_url = base_url
        self.model = model
    
    async def generate_code(self, prompt: str, **kwargs) -> LLMResponse:
        """Generate code using local LLM"""
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": kwargs.get("temperature", 0.1),
                    "num_predict": kwargs.get("max_tokens", 4000)
                }
            }
            
            response = requests.post(f"{self.base_url}/api/generate", json=payload)
            response.raise_for_status()
            
            result = response.json()
            content = result.get("response", "")
            
            return LLMResponse(
                content=content,
                model=self.model,
                tokens_used=0,  # Local models don't track tokens
                cost=0.0,       # No cost for local models
                success=True
            )
            
        except Exception as e:
            logger.error(f"Local LLM API error: {e}")
            return LLMResponse(
                content="",
                model=self.model,
                tokens_used=0,
                cost=0.0,
                success=False,
                error_message=str(e)
            )
    
    async def improve_code(self, prompt: str, **kwargs) -> LLMResponse:
        """Improve existing code using local LLM"""
        return await self.generate_code(prompt, **kwargs)

class LLMClientManager:
    """Manager class to handle multiple LLM providers"""
    
    def __init__(self):
        self.clients: Dict[LLMProvider, BaseLLMClient] = {}
        self.default_provider = LLMProvider.OPENAI
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize LLM clients based on available API keys"""
        # OpenAI
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            self.clients[LLMProvider.OPENAI] = OpenAIClient(
                api_key=openai_key,
                model=os.getenv("OPENAI_MODEL", "gpt-4"),
                base_url=LITELLM_PROXY_URL,
            )
            logger.info("OpenAI client initialized")
        
        # Anthropic
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key:
            self.clients[LLMProvider.ANTHROPIC] = AnthropicClient(
                api_key=anthropic_key,
                model=os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229"),
                base_url=LITELLM_PROXY_URL,
            )
            logger.info("Anthropic client initialized")
        
        # Local LLM
        local_url = os.getenv("LOCAL_LLM_URL")
        if local_url:
            self.clients[LLMProvider.LOCAL] = LocalLLMClient(
                base_url=local_url,
                model=os.getenv("LOCAL_LLM_MODEL", "codellama")
            )
            logger.info("Local LLM client initialized")
        
        # Set default provider based on availability
        if LLMProvider.ANTHROPIC in self.clients:
            self.default_provider = LLMProvider.ANTHROPIC
        elif LLMProvider.OPENAI in self.clients:
            self.default_provider = LLMProvider.OPENAI
        elif LLMProvider.LOCAL in self.clients:
            self.default_provider = LLMProvider.LOCAL
    
    async def generate_code(self, prompt: str, provider: Optional[LLMProvider] = None, **kwargs) -> LLMResponse:
        """Generate code using specified or default provider"""
        provider = provider or self.default_provider

        if provider not in self.clients:
            return LLMResponse(
                content="",
                model="none",
                tokens_used=0,
                cost=0.0,
                success=False,
                error_message=f"Provider {provider.value} not available"
            )

        return await self.clients[provider].generate_code(prompt, **kwargs)

    async def improve_code(self, prompt: str, provider: Optional[LLMProvider] = None, **kwargs) -> LLMResponse:
        """Improve code using specified or default provider"""
        provider = provider or self.default_provider

        if provider not in self.clients:
            return LLMResponse(
                content="",
                model="none",
                tokens_used=0,
                cost=0.0,
                success=False,
                error_message=f"Provider {provider.value} not available"
            )

        return await self.clients[provider].improve_code(prompt, **kwargs)
    
    def get_available_providers(self) -> List[LLMProvider]:
        """Get list of available LLM providers"""
        return list(self.clients.keys())
    
    def set_default_provider(self, provider: LLMProvider):
        """Set default LLM provider"""
        if provider in self.clients:
            self.default_provider = provider
        else:
            raise ValueError(f"Provider {provider.value} not available")

# Global LLM client manager instance
llm_manager = LLMClientManager() 