import asyncio
import aiohttp
from PIL import Image
import io
import google.generativeai as genai
from config.config import config

async def fetch_image(image_url: str) -> Image.Image:
    """Download and convert image from URL to PIL Image"""
    async with aiohttp.ClientSession() as session:
        async with session.get(image_url) as response:
            if response.status != 200:
                raise Exception(f"Failed to download image: {response.status}")
            image_data = await response.read()
            return Image.open(io.BytesIO(image_data))

async def identify_items_in_images(images: list[Image.Image]) -> list[str]:
    """Use Gemini to identify OSRS items/NPCs/locations in images"""
    if not images:
        return []

    try:
        model = genai.GenerativeModel(config.gemini_model)
        prompt = """Name the OSRS items, NPCs, or locations you see in these images. Use exact wiki page names with underscores.

        Respond ONLY with comma-separated wiki page names, no explanations or other text.
        Example response format: "Dragon_scimitar,Abyssal_whip,Lumbridge_Castle"
        """
        
        content = [prompt] + images
        print("API CALL: GEMINI identify_items_in_images")
        generation = await asyncio.to_thread(
            lambda: model.generate_content(content)
        )
        return [name.strip() for name in generation.text.split(',') if name.strip()]
    except Exception as e:
        print(f"Error identifying items in images: {e}")
        return []