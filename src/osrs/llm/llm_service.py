import asyncio
import os
import re
import time
from typing import List, Optional, Tuple
from PIL import Image
from config.config import config

# Set provider API keys in environment before importing litellm
if hasattr(config, 'gemini_api_key') and config.gemini_api_key:
    os.environ["GEMINI_API_KEY"] = config.gemini_api_key
if hasattr(config, 'openai_api_key') and config.openai_api_key:
    os.environ["OPENAI_API_KEY"] = config.openai_api_key
if hasattr(config, 'anthropic_api_key') and config.anthropic_api_key:
    os.environ["ANTHROPIC_API_KEY"] = config.anthropic_api_key
if hasattr(config, 'groq_api_key') and config.groq_api_key:
    os.environ["GROQ_API_KEY"] = config.groq_api_key
if hasattr(config, 'openrouter_api_key') and config.openrouter_api_key:
    os.environ["OPENROUTER_API_KEY"] = config.openrouter_api_key

import litellm

class LLMServiceError(Exception):
    """Custom exception for LLM service errors"""
    def __init__(self, message, original_exception=None, retry_after=None):
        self.message = message
        self.original_exception = original_exception
        self.retry_after = retry_after  # Time in seconds to wait before retrying
        super().__init__(self.message)

class LLMService:
    """Centralized service for LLM interactions using LiteLLM"""
    
    # Class variables to track rate limiting
    _rate_limited_until = 0  # Timestamp when rate limit expires
    
    def __init__(self):
        pass
    
    def _extract_retry_delay(self, error_message: str) -> int:
        """Extract retry delay from error message"""
        # Try to find the retryDelay value in the error message
        match = re.search(r'"retryDelay":\s*"(\d+)s"', str(error_message))
        if match:
            return int(match.group(1))
        return 60  # Default to 60 seconds if we can't find the value
    
    def _is_rate_limited(self) -> Tuple[bool, int]:
        """Check if we're currently rate limited and return remaining time"""
        if self._rate_limited_until > time.time():
            remaining = int(self._rate_limited_until - time.time())
            return True, remaining
        return False, 0

    async def generate_text(self,
                                    prompt: str,
                                    model: str = None,
                                    max_tokens: int = None) -> str:
        """
        Generate text response from an LLM using LiteLLM
        """
        # Check if we're currently rate limited
        is_limited, remaining_time = self._is_rate_limited()
        if is_limited:
            error_msg = f"Rate limit in effect. Please try again in {remaining_time} seconds."
            print(error_msg)
            raise LLMServiceError(error_msg, retry_after=remaining_time)
            
        litellm_model = model or config.default_model
        
        try:
            response = await asyncio.to_thread(
                lambda: litellm.completion(
                    model=litellm_model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens
                )
            )
            if response and hasattr(response, "choices") and len(response.choices) > 0:
                return response.choices[0].message.content
            return ""
        except Exception as e:
            error_message = f"Error in generate_text_litellm: {e}"
            print(error_message)
            
            # Check if this is a rate limit error
            if "RateLimitError" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                retry_delay = self._extract_retry_delay(str(e))
                # Set the rate limit expiration time
                self._rate_limited_until = time.time() + retry_delay
                error_msg = f"LLM service rate limited. Please try again in {retry_delay} seconds."
                raise LLMServiceError(error_msg, e, retry_after=retry_delay)
            else:
                # For other errors
                raise LLMServiceError("LLM service is currently unavailable or overloaded", e)

    async def generate_with_images(self,
                                  prompt: str,
                                  images: List[Image.Image],
                                  model: str = None) -> str:
        """
        Generate text response from an LLM with image inputs
        """
        # Check if we're currently rate limited
        is_limited, remaining_time = self._is_rate_limited()
        if is_limited:
            error_msg = f"Rate limit in effect. Please try again in {remaining_time} seconds."
            print(error_msg)
            raise LLMServiceError(error_msg, retry_after=remaining_time)
            
        litellm_model = model or config.default_model

        # Convert images to base64
        image_contents = []
        for img in images:
            import io
            import base64
            buffered = io.BytesIO()
            img.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            image_contents.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_str}"
                }
            })

        content = [{"type": "text", "text": prompt}] + image_contents

        try:
            response = await asyncio.to_thread(
                lambda: litellm.completion(
                    model=litellm_model,
                    messages=[{"role": "user", "content": content}]
                )
            )
            if response and hasattr(response, "choices") and len(response.choices) > 0:
                return response.choices[0].message.content
            return ""
        except Exception as e:
            error_message = f"Error in generate_with_images: {e}"
            print(error_message)
            
            # Check if this is a rate limit error
            if "RateLimitError" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                retry_delay = self._extract_retry_delay(str(e))
                # Set the rate limit expiration time
                self._rate_limited_until = time.time() + retry_delay
                error_msg = f"LLM service rate limited. Please try again in {retry_delay} seconds."
                raise LLMServiceError(error_msg, e, retry_after=retry_delay)
            else:
                # For other errors
                raise LLMServiceError("LLM service is currently unavailable or overloaded", e)


llm_service = LLMService()