import os
import requests
import aiohttp
import trafilatura
from bs4 import BeautifulSoup
import re
from pathlib import Path
import asyncio
import json
import time
import hashlib
from config.config import config, PROJECT_ROOT, SEARCH_CACHE, PAGES_CACHE

# Rate limiter for Brave Search API (1 request per second)
_last_search_time = 0
_search_lock = asyncio.Lock()

# URLs to exclude from search results
EXCLUDED_TERMS = [
    "fandom.com", "reddit.com", "quora.com", "youtube.com", "twitch.tv", "support.runescape.com",
    "facebook.com", "github.com", "github.io", "x.com", "twitter.com",
    "runehq.com", "zybez.net", "melvoridle.com", "osrsbestinslot.com",
    "playerauctions.com", "rpgstash.com", "eldorado.gg", "probemas.com",
    "chicksgold.com", "g2g.com", "food4rs.com", "partypeteshop.com",
    "rsorder.com", "ezrsgold.com", "rsgoldfast.com", "virtgold.com",
    "luckycharmgold.com", "osbuddy.com", "osbot.org", "runemate.com",
    "osrsbots.com", "oldschoolscripts.com", "dreambot.org", "epicbot.com",
    "tribot.org", "robotzindisguise.com", "topg.org", "runelocus.com",
    "rsps-list.com", "sythe.org", "top100arena.com", "moparscape.org",
    "sherpasboosting.com", "1v9.gg"
]

# Allowed RuneScape wiki domains
ALLOWED_WIKI_DOMAINS = [
    "oldschool.runescape.wiki",
    "prices.runescape.wiki"
]


# Sanitize filename to avoid filesystem issues
def safe_filename(name):
    name = re.sub(r'[^\w\s-]', '', name)
    return re.sub(r'[\s-]+', '_', name).strip('_')[:50] + ".txt"

# Cache functions
def get_search_cache_path(search_term):
    """Get the cache file path for a given search term"""
    safe_term = re.sub(r'[^\w\s-]', '', search_term)
    safe_term = re.sub(r'[\s-]+', '_', safe_term).strip('_')[:50]
    # Use search cache directory
    return os.path.join(SEARCH_CACHE, f"{safe_term}.json")

def load_cached_search(search_term):
    """Load search results from cache if they exist and are valid"""
    cache_path = get_search_cache_path(search_term)
    if not os.path.exists(cache_path):
        print(f"No search cache file exists at {cache_path}")
        return None

    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)

        current_time = time.time()
        cache_age = current_time - cache_data['timestamp']

        # If cache is less than 1 hour old, mark it as fresh
        if cache_age < 24 * 60 * 60:
            print(f"Using fresh search cache for '{search_term}' (less than 24 hours old)")
            return cache_data['results']

        # Check if cache has expired (24 hours)
        if cache_age > 24 * 60 * 60:
            print(f"Search cache expired for '{search_term}' (older than 24 hours)")
            return None

        print(f"Using valid search cache for '{search_term}' (less than 24 hours old)")
        return cache_data['results']
    except Exception as e:
        print(f"Error loading search cache for '{search_term}': {e}")
        return None

def save_search_to_cache(search_term, results):
    """Save search results to cache"""
    cache_path = get_search_cache_path(search_term)
    # Create cache directory if it doesn't exist
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    
    cache_data = {
        'results': results,
        'timestamp': time.time()
    }

    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False)
        print(f"Saved search results to cache for '{search_term}'")
    except Exception as e:
        print(f"Error saving search cache for '{search_term}': {e}")

def get_page_cache_path(url):
    """Get the cache file path for a page URL"""
    # Use MD5 hash of URL as filename to avoid issues with special characters
    url_hash = hashlib.md5(url.encode()).hexdigest()
    # Use pages cache directory
    return os.path.join(PAGES_CACHE, f"{url_hash}.json")

def load_cached_page_content(url):
    """Load page content from cache if it exists and is valid"""
    cache_path = get_page_cache_path(url)
    if not os.path.exists(cache_path):
        print(f"No page cache file exists for URL: {url}")
        return None

    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)

        current_time = time.time()
        cache_age = current_time - cache_data['timestamp']

        # If cache is less than 1 day old, use it
        if cache_age < 24 * 60 * 60:
            print(f"Using cached page content for URL: {url}")
            return cache_data['content']

        print(f"Page cache expired for URL: {url}")
        return None
    except Exception as e:
        print(f"Error loading page cache for URL {url}: {e}")
        return None

def save_page_content_to_cache(url, content):
    """Save page content to cache"""
    cache_path = get_page_cache_path(url)
    # Create cache directory if it doesn't exist
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    
    cache_data = {
        'content': content,
        'timestamp': time.time(),
        'url': url
    }

    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False)
        print(f"Saved page content to cache for URL: {url}")
    except Exception as e:
        print(f"Error saving page cache for URL {url}: {e}")

# Extract printable text from a web page using trafilatura
async def extract_text_from_url(session, page_url):
    try:
        # Try to load from cache first
        cached_content = load_cached_page_content(page_url)
        if cached_content:
            return cached_content

        print(f"Fetching content from URL: {page_url}")

        # Use configured headers for better success rate
        timeout = aiohttp.ClientTimeout(total=10)
        async with session.get(page_url, headers=config.http_headers, timeout=timeout, allow_redirects=True) as response:
            if response.status == 200:
                # Get HTML content
                html_content = await response.text()

                # Use trafilatura for cleaner extraction (less boilerplate = fewer tokens)
                try:
                    content = trafilatura.extract(
                        html_content,
                        include_comments=False,
                        include_tables=True,
                        output_format="text"
                    )
                except Exception as e:
                    print(f"Trafilatura extraction failed for {page_url}: {e}")
                    content = None

                # Fallback to BeautifulSoup if trafilatura fails
                if not content:
                    soup = BeautifulSoup(html_content, "html.parser")
                    for tag in soup(["script", "style", "noscript"]):
                        tag.decompose()
                    content = soup.get_text(separator="\n", strip=True)

                # Save to cache if content was successfully extracted
                if content:
                    save_page_content_to_cache(page_url, content)

                return content
            else:
                print(f"Failed to fetch {page_url}: Status {response.status}")
                return None
    except Exception as e:
        print(f"Failed to fetch {page_url}: {e}")
        return None

async def search_web(search_term):
    """Search the web using Brave Search API and return formatted results"""
    if not config.brave_api_key:
        raise ValueError("Brave API key not found. Please set the BRAVE_API_KEY environment variable.")

    # Try to load from search cache first
    cached_results = load_cached_search(search_term)
    if cached_results:
        # Filter cached results
        filtered_results = [
            result for result in cached_results
            if result.get('url') and not any(term in result['url'].lower() for term in EXCLUDED_TERMS) and (
                not "runescape.wiki" in result['url'] or any(domain in result['url'] for domain in ALLOWED_WIKI_DOMAINS)
            )
        ]

        if filtered_results:
            print(f"Using filtered cached results ({len(filtered_results)} of {len(cached_results)} results kept)")
            return filtered_results
        print("All cached results were filtered out, performing new search")

    # Brave Search query and parameters
    params = {
        "q": f"osrs {search_term}",  # Prefix with osrs to focus results
        "count": 5
    }

    # Brave Search API endpoint and headers
    search_url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": config.brave_api_key
    }

    # Make request with retry logic for rate limiting
    max_retries = 5
    retry_count = 0

    while retry_count < max_retries:
        try:
            # Rate limiting: ensure at least 1 second between requests
            async with _search_lock:
                global _last_search_time
                current_time = time.time()
                time_since_last = current_time - _last_search_time

                if time_since_last < 1.0:
                    wait_time = 1.0 - time_since_last
                    print(f"Rate limiter: Waiting {wait_time:.1f}s before search...")
                    await asyncio.sleep(wait_time)

                _last_search_time = time.time()

            print(f"[API CALL: BRAVE] Search for '{search_term}'")
            # Perform search query
            response = requests.get(search_url, headers=headers, params=params)

            # Handle rate limiting
            if response.status_code == 429:
                # Check rate limit reset header
                reset_header = response.headers.get('X-RateLimit-Reset', '1')
                resets = reset_header.split(',')

                # Get the shortest reset time (usually the per-second limit)
                try:
                    wait_time = int(resets[0].strip()) if resets else 1
                except ValueError:
                    wait_time = 1

                # Add small buffer to ensure we don't hit it again
                wait_time = max(wait_time + 0.5, 1.0)

                retry_count += 1
                if retry_count >= max_retries:
                    print(f"Rate limited: Max retries ({max_retries}) reached")
                    return []

                print(f"Rate limited (429). Waiting {wait_time:.1f}s before retry {retry_count}/{max_retries}...")
                await asyncio.sleep(wait_time)
                continue

            elif response.status_code == 200:
                results = response.json().get("web", {}).get("results", [])

                # Format to store all search results
                tasks = []
                original_results = [] # Keep track of original result order and metadata

                # Create a single session for fetching page content
                async with aiohttp.ClientSession() as session:
                    for result in results:
                        title = result.get("title", "Untitled")
                        link = result.get("url")
                        # Skip unwanted URLs
                        if not link or any(term in link.lower() for term in EXCLUDED_TERMS) or (
                            "runescape.wiki" in link and not any(domain in link for domain in ALLOWED_WIKI_DOMAINS)
                        ):
                            if link: print(f"Skipping excluded URL: {link}")
                            continue

                        # print(f"\nQueueing content fetch for: {title}\n{link}")
                        # Store original result metadata and create task
                        original_results.append({"title": title, "url": link})
                        tasks.append(extract_text_from_url(session, link))

                    # Fetch content concurrently
                    print(f"Fetching content for {len(tasks)} URLs concurrently...")
                    content_results = await asyncio.gather(*tasks, return_exceptions=True)
                    print("Finished fetching content.")

                # Combine original metadata with fetched content
                formatted_results = []
                for i, content in enumerate(content_results):
                    original = original_results[i]
                    if isinstance(content, Exception):
                        print(f"Error fetching content for {original['url']}: {content}")
                    elif content:
                        # Truncate text if it's too long (first 2000 chars)
                        if len(content) > 2000:
                            content = content[:2000] + "... (content truncated)"

                        formatted_results.append({
                            "title": original['title'],
                            "url": original['url'],
                            "content": content
                        })
                        print(f"Successfully processed content from: {original['url']}")
                    else:
                        print(f"Skipped (no content found): {original['url']}")

                # Save search results to cache
                if formatted_results:
                    save_search_to_cache(search_term, formatted_results)

                return formatted_results
            else:
                # Other error status codes
                print(f"Search API error: {response.status_code}")
                print(response.text)
                return []

        except Exception as e:
            print(f"Error during web search: {e}")
            return []

    # If we exit the loop without returning, we've exhausted retries
    print(f"Search failed after {max_retries} retries")
    return []

def format_search_results(results):
    """Format search results into a string for use as context"""
    if not results:
        return "No search results found."
    
    formatted_text = "\n\n=== WEB SEARCH RESULTS ===\n\n"
    
    for i, result in enumerate(results, 1):
        formatted_text += f"--- RESULT {i}: {result['title']} ---\n"
        formatted_text += f"Source: <{result['url']}>\n\n"
        formatted_text += result['content']
        formatted_text += "\n\n" + "="*50 + "\n\n"
    
    return formatted_text