import requests
from bs4 import BeautifulSoup
import os
import os.path
import json
import time
import asyncio
import aiohttp
from config.config import PROJECT_ROOT, config, WIKI_CACHE


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

async def find_redirect_target(session, url):
    """Find the redirect target URL if a page redirects"""
    headers = {
        'User-Agent': config.user_agent,
        'Accept': '*/*',
        'Connection': 'keep-alive',
        'Accept-Encoding': 'gzip, deflate, br, zstd'
    }

    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                content = await response.text()
                soup = BeautifulSoup(content, 'html.parser')

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
    # Use wiki cache directory
    return os.path.join(WIKI_CACHE, f"{safe_name}.json")

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
    print(f"Attempting to save cache at: {cache_path}")
    
    # Create cache directory if it doesn't exist
    dir_path = os.path.dirname(cache_path)
    os.makedirs(dir_path, exist_ok=True)
    print(f"Verified directory exists: {os.path.exists(dir_path)}")
    
    cache_data = {
        'content': data,
        'timestamp': time.time(),
        'etag': headers.get('ETag'),
        'last_modified': headers.get('Last-Modified')
    }
    print(f"Cache data prepared, content length: {len(data)}")

    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False)
            print(f"Successfully wrote cache file: {cache_path}")
    except Exception as e:
        print(f"Failed to write cache file: {cache_path}")
        print(f"Directory exists: {os.path.exists(dir_path)}")
        print(f"Directory writable: {os.access(dir_path, os.W_OK)}")
        raise Exception(f"Error saving cache for {page_name}: {e}")

async def fetch_osrs_wiki(session, page_name):
    """Fetch content from OSRS wiki page, following redirects if necessary"""
    original_page_name = page_name
    url = f"https://oldschool.runescape.wiki/w/{page_name}"
    headers = {
        'User-Agent': config.user_agent,
        'Accept': '*/*',
        'Connection': 'keep-alive',
        'Accept-Encoding': 'gzip, deflate, br, zstd'
    }

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
    redirect_url = await find_redirect_target(session, url)
    if redirect_url:
        # Extract the redirected page name from the URL
        redirected_page_name = redirect_url.split("/w/")[-1]
        print(f"Page {page_name} redirects to {redirected_page_name}")
        # Update the page name and URL
        page_name = redirected_page_name
        url = redirect_url # Use the potentially new URL

    async with session.get(url, headers=headers, allow_redirects=True) as response:
        print(f"\nDEBUG: Response status code: {response.status}")
        print(f"DEBUG: Response headers: {dict(response.headers)}")
        print(f"DEBUG: Request URL: {url}")
        print(f"DEBUG: Final URL after redirects: {str(response.url)}")

        if response.status == 304 and cache_data:
            print("DEBUG: Hit 304 path")
            # Not modified, use cached content
            print(f"Server validated cache is still fresh (304 Not Modified)")
            print(f"Cache validation headers: ETag={headers.get('If-None-Match')}, Last-Modified={headers.get('If-Modified-Since')}")
            html_content = cache_data['content']
        elif response.status == 200:
            print("DEBUG: Hit 200 path")
            print("Got 200 response, preparing to save to cache")
            # Save new content to cache
            html_content = await response.text()
            print(f"Retrieved content length: {len(html_content)}")
            response_headers = response.headers
            if not cache_data:
                print(f"No cache exists for {page_name}")
            else:
                if cache_data.get('etag') != response_headers.get('ETag'):
                    print(f"Cache invalidated - ETag changed")
                elif cache_data.get('last_modified') != response_headers.get('Last-Modified'):
                    print(f"Cache invalidated - Last-Modified changed")
                else:
                    # This case shouldn't happen if 304 was handled, but good for logging
                    print(f"Cache expired or headers mismatch, fetching new content.")
            print(f"About to save to cache with headers: ETag={response_headers.get('ETag')}, Last-Modified={response_headers.get('Last-Modified')}")
            try:
                save_to_cache(page_name, html_content, response_headers)
                print("Cache save completed")
            except Exception as e:
                print(f"Failed to save cache: {e}")
                print(f"Exception details: {str(e)}")
        else:
            print(f"DEBUG: Hit error path with status {response.status}")
            error_msg = ""
            if response.status == 404:
                error_msg = f"Page not found - This item/content may be unreleased or not exist in OSRS yet."
            elif response.status == 403:
                error_msg = f"Access denied by Cloudflare anti-bot protection. Status code: 403"
            else:
                error_msg = f"Failed to download page: {url} (Status code: {response.status})"
            raise Exception(error_msg)

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

async def fetch_osrs_wiki_pages(page_names):
    """Fetch content from multiple OSRS wiki pages and return their combined content"""
    if not page_names:
        return "No wiki pages specified", {}

    combined_content = ""
    # Dictionary to track redirects: original_name -> redirected_name
    redirects = {}
    tasks = []

    # Use a single session for all requests
    async with aiohttp.ClientSession() as session:
        for page_name in page_names:
            # Create a task for each page fetch
            task = asyncio.create_task(fetch_osrs_wiki(session, page_name))
            tasks.append(task)

        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            combined_content += f"\n\n{'='*50} ERROR FETCHING PAGE {page_names[i]} {'='*50}\n\nError: {result}\n"
        else:
            page_content, original_name, redirected_name = result
            if original_name != redirected_name:
                redirects[original_name] = redirected_name
            if i > 0: # Add separator before the second page onwards
                combined_content += "\n\n" + "="*50 + " NEW WIKI PAGE " + "="*50 + "\n\n"
            combined_content += f"[SOURCE: {redirected_name}]\n\n{page_content}"

    return combined_content, redirects


# Setup function for registering commands
# This function is imported by the main bot file
def setup_osrs_commands(bot):
    # Import here to avoid circular imports
    from osrs.llm.commands import register_commands
    register_commands(bot)