import asyncio
import requests
from bs4 import BeautifulSoup
import aiohttp
import google.generativeai as genai
from PIL import Image
import io
import os
import os.path
import json
import time

from config.config import config

# Configure the Gemini API
if config.gemini_api_key:
    genai.configure(api_key=config.gemini_api_key)

# System prompt for Gemini
SYSTEM_PROMPT = """
You are an Old School RuneScape (OSRS) expert assistant. Your task is to answer questions about OSRS using information provided from the OSRS Wiki.

Formatting Rules:
1. Use * for bullet points (they format correctly in Discord)
2. Bold ONLY the following with **text**:
   * Section headers
   * Item names (e.g., **Abyssal whip**)
   * Boss/monster names (e.g., **Zulrah**)
   * Location names (e.g., **Wilderness**)
3. Do NOT bold:
   * Drop rates or percentages
   * Prices or numerical values
   * Statistics or combat levels
4. Break information into clear sections
5. Keep answers concise (under 2000 characters)

Content Rules:
1. Use only the provided wiki information
2. Prioritize key information the player needs
3. Format information clearly and consistently
4. State clearly if information isn't available

Remember: Create clear, easy-to-read responses that focus on the key information.
"""

# Helper functions for OSRS Wiki integration
def clean_text(text):
    """Clean text by removing extra whitespace and newlines"""
    return ' '.join(text.split())

def render_table_to_text(table):
    """Render an HTML table element into a text-formatted table"""
    def process_img(img):
        # Check if parent is <a> with title
        parent = img.parent
        if parent.name == 'a' and parent.get('title'):
            return f"IMG: [{parent['title']}]"
        # Check for href
        if parent.name == 'a' and parent.get('href'):
            href = parent['href']
            if href.startswith('/w/'):
                href = href[3:]  # Remove '/w/' prefix
            return f"IMG: [{href}]"
        # Check for alt text
        if img.get('alt'):
            return f"IMG: [{img['alt']}]"
        return "IMG: [no description]"

    rows = table.find_all('tr')
    lines = []
    for row in rows:
        cells = row.find_all(['th', 'td'])
        cell_texts = []
        for cell in cells:
            # Process any img tags first
            for img in cell.find_all('img'):
                img_text = process_img(img)
                img.replace_with(img_text)
            cell_texts.append(clean_text(cell.get_text()))
        line = " | ".join(cell_texts)
        lines.append(line)
    return "\n".join(lines)

def extract_item_info(html_content):
    """Extract item information from OSRS Wiki HTML content"""
    soup = BeautifulSoup(html_content, 'html.parser')
    content = soup.find(id="mw-content-text")
    if not content:
        return "Could not find main content"
    info = {}
    infobox = content.find('table', class_='infobox')
    if infobox:
        header_row = infobox.find('th', class_='infobox-header')
        if header_row:
            info['name'] = header_row.get_text().strip()
        for row in infobox.find_all('tr'):
            header = row.find('th')
            data = row.find('td')
            if header and data and header.get_text().strip():
                key = header.get_text().strip()
                value = data.get_text().strip()
                if key == "Exchange":
                    value = value.replace(" (info)", "")
                info[key] = value
    bonuses_table = content.find('table', class_='infobox-bonuses')
    if bonuses_table:
        combat_stats = {
            "Attack bonuses": {},
            "Defence bonuses": {},
            "Other bonuses": {}
        }
        current_section = None
        rows = bonuses_table.find_all('tr')
        for row in rows:
            header = row.find('th', class_='infobox-subheader')
            if header:
                text = header.get_text().strip()
                if "Attack bonus" in text:
                    current_section = "Attack bonuses"
                elif "Defence bonus" in text:
                    current_section = "Defence bonuses"
                elif "Other bonus" in text:
                    current_section = "Other bonuses"
                continue
            values = row.find_all('td', class_='infobox-nested')
            if current_section and values:
                if current_section in ["Attack bonuses", "Defence bonuses"] and len(values) == 5:
                    combat_stats[current_section].update({
                        "Stab": values[0].text.strip(),
                        "Slash": values[1].text.strip(),
                        "Crush": values[2].text.strip(),
                        "Magic": values[3].text.strip(),
                        "Ranged": values[4].text.strip()
                    })
                elif current_section == "Other bonuses" and len(values) >= 4:
                    combat_stats[current_section].update({
                        "Strength": values[0].text.strip(),
                        "Ranged Strength": values[1].text.strip(),
                        "Magic Damage": values[2].text.strip(),
                        "Prayer": values[3].text.strip()
                    })
        info['combat_stats'] = combat_stats
    return info

def find_redirect_target(url):
    """Find the redirect target URL if a page redirects"""
    headers = {
        'User-Agent': 'OSRS Wiki Assistant/1.0'
    }
    
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Check for canonical link which indicates the "true" URL
        canonical = soup.find('link', attrs={'rel': 'canonical'})
        if canonical and canonical['href'] != url:
            return canonical['href']
        
        # Alternative method: check for redirect notice in content
        redirect_notice = soup.find('div', class_='redirectMsg')
        if redirect_notice:
            redirect_link = redirect_notice.find('a')
            if redirect_link and redirect_link.get('href'):
                return f"https://oldschool.runescape.wiki{redirect_link['href']}"
        
        return None
    except Exception as e:
        print(f"Error checking for redirect: {e}")
        return None

def get_cache_path(page_name):
    """Get the cache file path for a given page name"""
    safe_name = page_name.replace('/', '_').replace('\\', '_')
    # Use project root directory for cache folder
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(root_dir, 'cache', f"{safe_name}.json")

def load_cached_page(page_name):
    """Load a page from cache if it exists and is valid"""
    cache_path = get_cache_path(page_name)
    if not os.path.exists(cache_path):
        print(f"No cache file exists at {cache_path}")
        return None

    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)

        current_time = time.time()
        cache_age = current_time - cache_data['timestamp']

        # If cache is less than 1 hour old, mark it as fresh
        if cache_age < 60 * 60:
            print(f"Using fresh cache for {page_name} (less than 1 hour old)")
            cache_data['fresh'] = True
            return cache_data

        # Check if cache has expired (24 hours)
        if cache_age > 24 * 60 * 60:
            print(f"Cache expired for {page_name} (older than 24 hours)")
            return None

        cache_data['fresh'] = False
        return cache_data
    except Exception as e:
        print(f"Error loading cache for {page_name}: {e}")
        return None

def save_to_cache(page_name, data, headers):
    """Save page data and headers to cache"""
    cache_path = get_cache_path(page_name)
    # Create cache directory if it doesn't exist
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    
    cache_data = {
        'content': data,
        'timestamp': time.time(),
        'etag': headers.get('ETag'),
        'last_modified': headers.get('Last-Modified')
    }

    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving cache for {page_name}: {e}")

def fetch_osrs_wiki(page_name):
    """Fetch content from OSRS wiki page, following redirects if necessary"""
    original_page_name = page_name
    url = f"https://oldschool.runescape.wiki/w/{page_name}"
    headers = {"User-Agent": "OSRS Wiki Assistant/1.0"}

    # Try to load from cache first
    cache_data = load_cached_page(page_name)
    if cache_data:
        if cache_data.get('fresh'):
            # Cache is less than an hour old, use it without checking server
            print(f"Using fresh cache without server validation")
            return cache_data['content'], original_page_name, page_name

        # For older cache, add conditional headers if available
        if cache_data.get('etag'):
            headers['If-None-Match'] = cache_data['etag']
        if cache_data.get('last_modified'):
            headers['If-Modified-Since'] = cache_data['last_modified']
    
    # First check if the page redirects
    redirect_url = find_redirect_target(url)
    if redirect_url:
        # Extract the redirected page name from the URL
        redirected_page_name = redirect_url.split("/w/")[-1]
        print(f"Page {page_name} redirects to {redirected_page_name}")
        # Update the page name and URL
        page_name = redirected_page_name
        url = redirect_url
    response = requests.get(url, headers=headers)
    if response.status_code == 304 and cache_data:
        # Not modified, use cached content
        print(f"Server validated cache is still fresh (304 Not Modified)")
        print(f"Cache validation headers: ETag={headers.get('If-None-Match')}, Last-Modified={headers.get('If-Modified-Since')}")
        html_content = cache_data['content']
    elif response.status_code == 200:
        # Save new content to cache
        html_content = response.text
        if not cache_data:
            print(f"No cache exists for {page_name}")
        else:
            if cache_data.get('etag') != response.headers.get('ETag'):
                print(f"Cache invalidated - ETag changed")
            elif cache_data.get('last_modified') != response.headers.get('Last-Modified'):
                print(f"Cache invalidated - Last-Modified changed")
            else:
                print(f"Cache expired (older than 24 hours)")
        print(f"Saving new content to cache with headers: ETag={response.headers.get('ETag')}, Last-Modified={response.headers.get('Last-Modified')}")
        save_to_cache(page_name, html_content, response.headers)
    else:
        if response.status_code == 404:
            return f"Page not found - This item/content may be unreleased or not exist in OSRS yet.", original_page_name, page_name
        return f"Failed to download page: {url} (Status code: {response.status_code})", original_page_name, page_name

    info = extract_item_info(html_content)
    output = ""
    output += f"=== {info.get('name', 'Item')} Information ===\n\n"
    basic_info_keys = ['Members', 'Tradeable', 'Equipable', 'High alch', 'Weight', 'Buy limit']
    for key in basic_info_keys:
        if key in info:
            output += f"{key}: {info[key]}\n"
    if 'Exchange' in info:
        output += f"Grand Exchange (GE) Price: {info['Exchange']}\n"
    output += "\n"
    output += "===Combat Stats===\n"
    if 'combat_stats' in info:
        for section, bonuses in info['combat_stats'].items():
            output += f"\n{section}:\n"
            for stat, value in bonuses.items():
                output += f"  {stat}: {value:>5}\n"
    soup = BeautifulSoup(html_content, 'html.parser')
    content = soup.find(id="mw-content-text")
    if content:
        output += "\n===Description===\n"
        elements = content.find_all(["p", "span", "td", "li", "div", "table"], recursive=True)
        skip_section = False
        in_changes = False
        special_attack_printed = False
        for el in elements:
            if el.name == 'div' and el.get('id') == 'toc':
                skip_section = True
                continue
            if el.name == 'table' and ('navbox' in el.get('class', [])):
                skip_section = True
                continue
            if el.name == 'span' and ('mw-headline' in el.get('class', [])):
                header_text = el.get_text().strip()
                if header_text == "Changes":
                    skip_section = False
                    in_changes = True
                    output += f"\n==={header_text}===\n"
                elif header_text in ["Combat stats", "Used in recommended equipment", "Gallery", "Gallery (historical)", "References", "Sound effects", "Transcript"]:
                    skip_section = True
                    in_changes = False
                    continue
                elif header_text == "Special attack":
                    in_changes = False
                    if not special_attack_printed:
                        special_attack_printed = True
                        skip_section = False
                        output += f"\n==={header_text}===\n"
                    else:
                        skip_section = True
                        continue
                else:
                    skip_section = False
                    in_changes = False
                    output += f"\n==={header_text}===\n"
            elif el.name == 'p' and not skip_section:
                output += el.get_text().strip() + "\n"
            elif el.name == 'li' and not skip_section:
                output += f"• {el.get_text().strip()}\n"
            elif el.name == 'table' and not skip_section:
                # Render tables inline with the content
                table_text = render_table_to_text(el)
                output += "\n" + table_text + "\n"
            elif in_changes and el.name == 'td':
                if el.has_attr('data-sort-value'):
                    output += "\n" + el['data-sort-value'] + "\n"

    # Return the content, the original page name, and the potentially redirected page name
    return output, original_page_name, page_name

def fetch_osrs_wiki_pages(page_names):
    """Fetch content from multiple OSRS wiki pages and return their combined content"""
    if not page_names:
        return "No wiki pages specified", {}
    
    combined_content = ""
    # Dictionary to track redirects: original_name -> redirected_name
    redirects = {}
    
    for i, page_name in enumerate(page_names):
        # Add a very distinct separator between wiki pages
        if i > 0:
            combined_content += "\n\n" + "="*50 + " NEW WIKI PAGE " + "="*50 + "\n\n"
        
        # Fetch page content and get redirect information
        page_content, original_name, redirected_name = fetch_osrs_wiki(page_name)
        
        # Record any redirects that occurred
        if original_name != redirected_name:
            redirects[original_name] = redirected_name
        
        combined_content += f"[SOURCE: {redirected_name}]\n\n{page_content}"
    
    return combined_content, redirects

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
        generation = await asyncio.to_thread(
            lambda: model.generate_content(content)
        )
        return [name.strip() for name in generation.text.split(',') if name.strip()]
    except Exception as e:
        print(f"Error identifying items in images: {e}")
        return []

async def identify_wiki_pages(user_query: str, image_urls: list[str] = None):
    """Use Gemini to identify relevant wiki pages for the query"""
    if not config.gemini_api_key:
        print("Gemini API key not set")
        return []
    
    try:
        model = genai.GenerativeModel(config.gemini_model)
        
        # Stage 1: Process images if present
        identified_items = []
        if image_urls:
            # Download and convert images to PIL format
            images = []
            for url in image_urls:
                try:
                    image = await fetch_image(url)
                    images.append(image)
                except Exception as e:
                    print(f"Error processing image {url}: {e}")
                    continue

            if images:
                identified_items = await identify_items_in_images(images)
                print(f"Items identified in images: {identified_items}")
                if identified_items:
                    # Add identified items to user query
                    user_query = f"{user_query}\nItems in images: {', '.join(identified_items)}"

        # Stage 2: Process query (now including identified items if any)
        prompt = f"""
        You are an assistant that helps determine which Old School RuneScape (OSRS) wiki pages to fetch based on user queries.

        Important Rules:
        1. ONLY include pages that are EXPLICITLY mentioned in the query or identified from images
        2. Do NOT guess or infer related pages unless absolutely certain
        3. For items, use exact names with underscores (e.g., "Dragon_scimitar")
        4. For NPCs/bosses, include their Strategies page if available
        5. For skill pages, include their Training page
        6. Limit to maximum 2 pages per source unless more are explicitly mentioned

        Query: {user_query}
        
        Respond ONLY with page names separated by commas. No additional text.
        Example: "Dragon_scimitar,Abyssal_whip"
        """
        
        generation = await asyncio.to_thread(
            lambda: model.generate_content(prompt)
        )
        page_names = [name.strip() for name in generation.text.split(',') if name.strip()]
        print(f"Identified wiki pages: {page_names}")
        return page_names
        
    except Exception as e:
        print(f"Error identifying wiki pages: {e}")
        return []

async def process_user_query(user_query: str, image_urls: list[str] = None) -> str:
    """Process a user query about OSRS using Gemini and the OSRS Wiki, optionally with images"""
    if not config.gemini_api_key:
        return "Sorry, the OSRS Wiki assistant is not available because the Gemini API key is not set."
        
    try:
        # Identify relevant wiki pages, potentially using image analysis
        page_names = await identify_wiki_pages(user_query, image_urls)
        
        if not page_names:
            return "I couldn't determine which wiki pages to search. Please try rephrasing your query to be more specific about OSRS content."
        
        print(f"Fetching wiki pages: {', '.join(page_names)}")
        
        # Fetch content from identified wiki pages
        wiki_content, redirects = await asyncio.to_thread(
            fetch_osrs_wiki_pages, page_names
        )
        
        # Update page_names with redirected names for correct source URLs
        updated_page_names = []
        for page in page_names:
            if page in redirects:
                updated_page_names.append(redirects[page])
            else:
                updated_page_names.append(page)
        
        print(f"Retrieved content from {len(page_names)} wiki pages")
        if redirects:
            print(f"Followed redirects: {redirects}")
        
        # Use text-based approach for response formatting
        # Function calling works for page identification but not for response formatting
        model = genai.GenerativeModel(config.gemini_model)
        
        prompt = f"""
        {SYSTEM_PROMPT}
        
        User Query: {user_query}
        
        OSRS Wiki Information:
        {wiki_content}
        
        Provide a response following these specific formatting rules:
        1. Start with a **Section Header**
        2. Use * for list items (not bullet points)
        3. Bold ONLY:
           * Item names (e.g., **Abyssal whip**)
           * Monster/boss names (e.g., **Abyssal demon**)
           * Location names (e.g., **Wilderness**)
           * Section headers
        4. Do NOT bold:
           * Drop rates
           * Prices
           * Combat stats
           * Other numerical values
        5. Include sources at the end using the URL format: https://oldschool.runescape.wiki/w/[page_name]
        """
        
        response = await asyncio.to_thread(
            lambda: model.generate_content(prompt).text
        )
        
        # Add source citations if not already included
        if not any(f"https://oldschool.runescape.wiki/w/{page.replace(' ', '_')}" in response for page in updated_page_names):
            sources = "\n\nSources:"
            for page in updated_page_names:
                # Clean the page name and add URL
                clean_page = page.replace(' ', '_').strip('[]')
                sources += f"\n- <https://oldschool.runescape.wiki/w/{clean_page}>"
            
            # Make sure the response with sources doesn't exceed Discord's limit
            if len(response) + len(sources) <= 1990:
                response += sources
        else:
            # Clean any URLs in the response to use angle brackets
            for page in updated_page_names:
                clean_page = page.replace(' ', '_').strip('[]')
                base_url = f"https://oldschool.runescape.wiki/w/{clean_page}"
                # Handle various URL patterns
                patterns = [
                    (f"[{base_url}]({base_url})", base_url),  # Markdown style
                    (f"[<{base_url}>]", base_url),  # Bracketed angle brackets
                    (f"(<{base_url}>)", base_url),  # Parenthesized angle brackets
                    (f"[{base_url}]", base_url),  # Simple brackets
                ]
                # First remove any special formatting
                for pattern, replacement in patterns:
                    response = response.replace(pattern, replacement)
                # Then add the single angle brackets if the URL is bare
                response = response.replace(base_url, f"<{base_url}>")
        
        return response
        
    except Exception as e:
        print(f"Error processing query: {e}")
        return f"Error processing your query: {str(e)}"

# Register OSRS commands
def setup_osrs_commands(bot):
    @bot.command(name='askyomi', aliases=['yomi', 'ask'])
    async def askyomi(ctx, *, user_query: str = ""):
        # Check for image attachments
        image_urls = []
        if ctx.message.attachments:
            for attachment in ctx.message.attachments:
                if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    image_urls.append(attachment.url)

        # If no query text and no images, show error
        if not user_query and not image_urls:
            await ctx.send("Please provide a question or attach an image to analyze.")
            return

        # Let the user know we're processing their request
        if image_urls:
            await ctx.send("Processing your image(s) and request, this may take a moment...")
        else:
            await ctx.send("Processing your request, this may take a moment...")

        try:
            response = await process_user_query(user_query or "What is this OSRS item?", image_urls)
            await ctx.send(response)
        except Exception as e:
            await ctx.send(f"Error processing your request: {str(e)}")