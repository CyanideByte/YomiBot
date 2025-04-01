import os
import requests
from bs4 import BeautifulSoup
import re
from pathlib import Path
import asyncio
import json
import time
import hashlib
from config.config import config

# User-Agent string
USER_AGENT = 'OSRS Wiki Assistant/1.0'

# Sanitize filename to avoid filesystem issues
def safe_filename(name):
    name = re.sub(r'[^\w\s-]', '', name)
    return re.sub(r'[\s-]+', '_', name).strip('_')[:50] + ".txt"

# Cache functions
def get_search_cache_path(search_term):
    """Get the cache file path for a given search term"""
    safe_term = re.sub(r'[^\w\s-]', '', search_term)
    safe_term = re.sub(r'[\s-]+', '_', safe_term).strip('_')[:50]
    # Use project root directory for cache folder
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(root_dir, 'cache', 'search', f"{safe_term}.json")

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
        if cache_age < 60 * 60:
            print(f"Using fresh search cache for '{search_term}' (less than 1 hour old)")
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
    # Use project root directory for cache folder
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(root_dir, 'cache', 'pages', f"{url_hash}.json")

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

# Extract printable text from a web page
def extract_text_from_url(page_url):
    try:
        # Try to load from cache first
        cached_content = load_cached_page_content(page_url)
        if cached_content:
            return cached_content
            
        print(f"Fetching content from URL: {page_url}")
        res = requests.get(
            page_url,
            timeout=10,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True
        )
        soup = BeautifulSoup(res.content, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        
        content = soup.get_text(separator="\n", strip=True)
        
        # Save to cache if content was successfully extracted
        if content:
            save_page_content_to_cache(page_url, content)
            
        return content
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
        return cached_results
    
    # Brave Search query and parameters
    params = {
        "q": f"osrs {search_term}",  # Prefix with osrs to focus results
        "count": 5
    }
    
    # Brave Search API endpoint and headers
    search_url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": config.brave_api_key,
        "User-Agent": USER_AGENT
    }
    
    try:
        print(f"Performing Brave Search for term: '{search_term}'")
        # Perform search query
        response = requests.get(search_url, headers=headers, params=params)
        
        if response.status_code == 200:
            results = response.json().get("web", {}).get("results", [])
            
            # Format to store all search results
            formatted_results = []
            
            for result in results:
                title = result.get("title", "Untitled")
                link = result.get("url")
                
                # Skip results from runescape.fandom.com and runescape.wiki
                # but allow oldschool.runescape.wiki
                if "runescape.fandom.com" in link or (
                    "runescape.wiki" in link and "oldschool.runescape.wiki" not in link
                ):
                    print(f"Skipping excluded domain: {link}")
                    continue
                    
                print(f"\nProcessing result: {title}\n{link}")
                
                text = extract_text_from_url(link)
                if text:
                    # Truncate text if it's too long (first 2000 chars)
                    if len(text) > 2000:
                        text = text[:2000] + "... (content truncated)"
                    
                    formatted_results.append({
                        "title": title,
                        "url": link,
                        "content": text
                    })
                    print(f"Successfully processed content from: {link}")
                else:
                    print(f"Skipped (no content found): {link}")
            
            # Save search results to cache
            if formatted_results:
                save_search_to_cache(search_term, formatted_results)
                
            return formatted_results
        else:
            print(f"Search API error: {response.status_code}")
            print(response.text)
            return []
            
    except Exception as e:
        print(f"Error during web search: {e}")
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
async def get_web_search_context(query):
    """Main function to get web search context for a query
    
    Returns:
        list: A list of search result dictionaries with 'title', 'url', and 'content' keys
    """
    try:
        # Import here to avoid circular imports
        from osrs.llm import generate_search_term
        
        # Generate a search term based on the query
        search_term = await generate_search_term(query)
        
        # Search the web using the generated term
        search_results = await search_web(search_term)
        
        return search_results
    except Exception as e:
        print(f"Error getting web search context: {e}")
        return []