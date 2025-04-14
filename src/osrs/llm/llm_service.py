import asyncio
import os
from typing import List, Optional
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

class LLMService:
    """Centralized service for LLM interactions using LiteLLM"""

    def __init__(self):
        pass

    async def generate_text(self,
                                    prompt: str,
                                    model: str = None,
                                    max_tokens: int = None) -> str:
        """
        Generate text response from an LLM using LiteLLM
        """
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
            print(f"Error in generate_text_litellm: {e}")
            raise

    async def generate_with_images(self,
                                  prompt: str,
                                  images: List[Image.Image],
                                  model: str = None) -> str:
        """
        Generate text response from an LLM with image inputs
        """
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
            print(f"Error in generate_with_images: {e}")
            raise


llm_service = LLMService()