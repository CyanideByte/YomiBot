import asyncio
import os
import re
import time
from typing import List, Optional, Tuple
from PIL import Image
from config.config import config
from litellm import RateLimitError
from litellm import ServiceUnavailableError
from osrs.llm.model_manager import get_model_manager

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
        self.model_manager = get_model_manager()
        # Log initial status
        status = self.model_manager.get_status()
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[LLM SERVICE] Initialized. Available models: {status['available']}")
        if status['rate_limited']:
            for limited in status['rate_limited']:
                logger.info(f"[LLM SERVICE] {limited['model']} is on cooldown for {limited['seconds_remaining']:.0f}s")

    def _get_model_with_fallback(self, preferred_model: Optional[str] = None) -> Optional[str]:
        """
        Get the best available model, with fallback if rate limited.

        Args:
            preferred_model: Preferred model name (optional)

        Returns:
            Model name to use, or None if all models are rate limited
        """
        # If using local LLM, return it directly
        if hasattr(config, 'use_local_llm') and config.use_local_llm:
            return f"openai/{config.local_model}"

        # Normalize the model name - strip "gemini/" prefix if present
        normalized_model = None
        if preferred_model:
            normalized_model = preferred_model.replace("gemini/", "")

        # If a specific model is requested, check if it's a Gemini model
        if normalized_model and normalized_model.startswith("gemini-"):
            # It's a specific Gemini model - check if it's available
            status = self.model_manager.get_status()
            if normalized_model in status['available']:
                # Model is available, use it
                return f"gemini/{normalized_model}"
            else:
                # Model is rate limited, fall through to use model manager
                print(f"[MODEL FALLBACK] {normalized_model} is rate limited, using best available")

        # For non-Gemini models, use as-is
        if normalized_model and not normalized_model.startswith("gemini-"):
            return normalized_model

        # Use the model manager to get best available Gemini model
        model = self.model_manager.get_available_model()

        if model is None:
            return None

        return f"gemini/{model}"
    
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

        Uses model priority with automatic fallback on rate limits.
        """
        # Get the best available model
        litellm_model = self._get_model_with_fallback(model or config.default_model)

        if litellm_model is None:
            # All models are rate limited
            status = self.model_manager.get_status()
            error_msg = "All Gemini models are currently rate limited. "
            if status['rate_limited']:
                oldest_entry = min(status['rate_limited'], key=lambda x: x['seconds_remaining'])
                error_msg += f"Try again in {int(oldest_entry['seconds_remaining'])} seconds."
            raise LLMServiceError(error_msg, retry_after=int(oldest_entry['seconds_remaining']))

        # Log model usage
        model_name = litellm_model.replace("gemini/", "")
        self.model_manager.log_model_usage(model_name)

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
        except RateLimitError as e:
            # Mark this model as rate limited
            self.model_manager.mark_rate_limited(model_name)

            # Try with next available model (recursive call with no preferred model)
            if model is None:  # Only retry if we're using the automatic selection
                print(f"[RETRY] {model_name} rate limited, trying next model...")
                return await self.generate_text(prompt, None, max_tokens)
            else:
                # If a specific model was requested, raise the error
                raise LLMServiceError(f"Model {model_name} is rate limited", e, retry_after=3600)
        except ServiceUnavailableError as e:
            # Model is overloaded/unavailable, treat like rate limit
            self.model_manager.mark_rate_limited(model_name)

            # Try with next available model
            if model is None:
                print(f"[RETRY] {model_name} is unavailable (503), trying next model...")
                return await self.generate_text(prompt, None, max_tokens)
            else:
                raise LLMServiceError(f"Model {model_name} is currently unavailable", e, retry_after=300)
        except Exception as e:
            error_message = f"Error in generate_text: {e}"
            print(error_message)
            raise LLMServiceError("LLM service is currently unavailable or overloaded", e)

    async def generate_with_images(self,
                                  prompt: str,
                                  images: List[Image.Image],
                                  model: str = None) -> str:
        """
        Generate text response from an LLM with image inputs

        Uses model priority with automatic fallback on rate limits.
        """
        # Get the best available model
        litellm_model = self._get_model_with_fallback(model or config.default_model)

        if litellm_model is None:
            # All models are rate limited
            status = self.model_manager.get_status()
            error_msg = "All Gemini models are currently rate limited. "
            if status['rate_limited']:
                oldest_entry = min(status['rate_limited'], key=lambda x: x['seconds_remaining'])
                error_msg += f"Try again in {int(oldest_entry['seconds_remaining'])} seconds."
            raise LLMServiceError(error_msg, retry_after=int(oldest_entry['seconds_remaining']))

        # Log model usage
        model_name = litellm_model.replace("gemini/", "")
        self.model_manager.log_model_usage(model_name)

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
        except RateLimitError as e:
            # Mark this model as rate limited
            self.model_manager.mark_rate_limited(model_name)

            # Try with next available model
            if model is None:
                print(f"[RETRY] {model_name} rate limited, trying next model...")
                return await self.generate_with_images(prompt, images, None)
            else:
                raise LLMServiceError(f"Model {model_name} is rate limited", e, retry_after=3600)
        except ServiceUnavailableError as e:
            # Model is overloaded/unavailable, treat like rate limit
            self.model_manager.mark_rate_limited(model_name)

            # Try with next available model
            if model is None:
                print(f"[RETRY] {model_name} is unavailable (503), trying next model...")
                return await self.generate_with_images(prompt, images, None)
            else:
                raise LLMServiceError(f"Model {model_name} is currently unavailable", e, retry_after=300)
        except Exception as e:
            error_message = f"Error in generate_with_images: {e}"
            print(error_message)
            raise LLMServiceError("LLM service is currently unavailable or overloaded", e)

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list,
        model: str = None,
        tool_choice: str = "auto"
    ) -> dict:
        """
        Generate response with tool/function calling support.

        Args:
            prompt: The user prompt
            tools: List of tool definitions in OpenAI format
            model: Optional model override
            tool_choice: "auto", "required", "none", or specific tool name

        Returns:
            dict with keys:
                - content: str (text response if no tools called)
                - tool_calls: list of dicts (if tools were called)
                Each tool_call has: {id, type, function: {name, arguments}}

        Uses model priority with automatic fallback on rate limits.
        """
        # Get the best available model
        litellm_model = self._get_model_with_fallback(model or config.default_model)

        if litellm_model is None:
            # All models are rate limited
            status = self.model_manager.get_status()
            error_msg = "All Gemini models are currently rate limited. "
            if status['rate_limited']:
                oldest_entry = min(status['rate_limited'], key=lambda x: x['seconds_remaining'])
                error_msg += f"Try again in {int(oldest_entry['seconds_remaining'])} seconds."
            raise LLMServiceError(error_msg, retry_after=int(oldest_entry['seconds_remaining']))

        # Log model usage
        model_name = litellm_model.replace("gemini/", "")
        self.model_manager.log_model_usage(model_name)

        # Configure litellm for local model if needed
        if hasattr(config, 'use_local_llm') and config.use_local_llm:
            if hasattr(config, 'local_llm_base'):
                litellm.api_base = config.local_llm_base
            litellm_model = f"openai/{config.local_model}"

        try:
            response = await asyncio.to_thread(
                lambda: litellm.completion(
                    model=litellm_model,
                    messages=[{"role": "user", "content": prompt}],
                    tools=tools,
                    tool_choice=tool_choice
                )
            )

            if not response or not hasattr(response, "choices") or len(response.choices) == 0:
                return {"content": "", "tool_calls": []}

            message = response.choices[0].message

            # Extract content and tool_calls
            result = {
                "content": message.content or "",
                "tool_calls": []
            }

            # Extract tool_calls in normalized format
            if hasattr(message, "tool_calls") and message.tool_calls:
                for tc in message.tool_calls:
                    result["tool_calls"].append({
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    })

            return result

        except RateLimitError as e:
            # Mark this model as rate limited
            self.model_manager.mark_rate_limited(model_name)

            # Try with next available model
            if model is None:
                print(f"[RETRY] {model_name} rate limited, trying next model...")
                return await self.generate_with_tools(prompt, tools, None, tool_choice)
            else:
                raise LLMServiceError(f"Model {model_name} is rate limited", e, retry_after=3600)
        except ServiceUnavailableError as e:
            # Model is overloaded/unavailable, treat like rate limit
            self.model_manager.mark_rate_limited(model_name)

            # Try with next available model
            if model is None:
                print(f"[RETRY] {model_name} is unavailable (503), trying next model...")
                return await self.generate_with_tools(prompt, tools, None, tool_choice)
            else:
                raise LLMServiceError(f"Model {model_name} is currently unavailable", e, retry_after=300)
        except Exception as e:
            error_message = f"Error in generate_with_tools: {e}"
            print(error_message)
            raise LLMServiceError("LLM service is currently unavailable or overloaded", e)


llm_service = LLMService()