"""
Check Brave Search API rate limits and remaining quota
Displays real-time rate limit information from API response headers
"""

import sys
import io
from pathlib import Path
import requests
from datetime import timedelta
import json

# Fix Windows encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add src to path so we can import config
sys.path.insert(0, str(Path(__file__).parent / 'src'))
from config.config import config


def parse_rate_limit_header(value):
    """Parse comma-separated rate limit values"""
    if not value:
        return []
    return [int(v.strip()) for v in value.split(',')]


def parse_rate_limit_policy(value):
    """Parse rate limit policy format: 'limit;w=window, limit;w=window'"""
    if not value:
        return []

    policies = []
    for policy in value.split(','):
        policy = policy.strip()
        if ';w=' in policy:
            limit_str, window_str = policy.split(';w=')
            policies.append({
                'limit': int(limit_str.strip()),
                'window_seconds': int(window_str.strip())
            })
    return policies


def format_seconds(seconds):
    """Convert seconds to human-readable format"""
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f} minute{'s' if minutes != 1 else ''}"
    elif seconds < 86400:
        hours = seconds / 3600
        return f"{hours:.1f} hour{'s' if hours != 1 else ''}"
    else:
        days = seconds / 86400
        return f"{days:.1f} day{'s' if days != 1 else ''}"


def check_rate_limits():
    """Make a test request and display rate limit information"""

    if not config.brave_api_key:
        print("ERROR: BRAVE_API_KEY not found in config")
        return

    print("Checking Brave Search API Rate Limits")
    print("=" * 60)

    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": config.brave_api_key
    }

    # Make a real search query
    query = "OSRS Vorkath guide"
    params = {"q": query, "count": 3}

    print(f"\nRunning test search: '{query}'\n")

    try:
        response = requests.get(url, headers=headers, params=params)

        # Check for rate limit headers
        rate_limit_limit = response.headers.get('X-RateLimit-Limit')
        rate_limit_policy = response.headers.get('X-RateLimit-Policy')
        rate_limit_remaining = response.headers.get('X-RateLimit-Remaining')
        rate_limit_reset = response.headers.get('X-RateLimit-Reset')

        if not any([rate_limit_limit, rate_limit_policy, rate_limit_remaining]):
            print("\n⚠️  No rate limit headers found in response")
            print(f"Status Code: {response.status_code}")
            return

        # Parse headers
        limits = parse_rate_limit_header(rate_limit_limit)
        remaining = parse_rate_limit_header(rate_limit_remaining)
        resets = parse_rate_limit_header(rate_limit_reset)
        policies = parse_rate_limit_policy(rate_limit_policy)

        print(f"\n📊 RATE LIMIT SUMMARY")
        print("-" * 60)

        # Display each limit window
        for i, policy in enumerate(policies):
            print(f"\n{'='*60}")
            print(f"Window {i + 1}: {format_seconds(policy['window_seconds'])}")
            print(f"{'='*60}")

            # Limit
            limit_val = limits[i] if i < len(limits) else "N/A"
            print(f"📈 Limit:           {limit_val} requests")

            # Remaining
            remaining_val = remaining[i] if i < len(remaining) else "N/A"
            print(f"📉 Remaining:       {remaining_val} requests")

            # Reset time
            reset_val = resets[i] if i < len(resets) else None
            if reset_val is not None:
                reset_time = format_seconds(reset_val)
                print(f"🔄 Resets in:       {reset_time}")

            # Usage percentage
            if i < len(limits) and i < len(remaining):
                limit = limits[i]
                remain = remaining[i]
                if limit > 0:
                    used = limit - remain
                    percent_used = (used / limit) * 100
                    bar_length = 30
                    filled = int((percent_used / 100) * bar_length)
                    bar = '█' * filled + '░' * (bar_length - filled)
                    print(f"📊 Usage:           [{bar}] {percent_used:.1f}%")

        print(f"\n{'='*60}")
        print("RAW HEADERS")
        print(f"{'='*60}")

        if rate_limit_limit:
            print(f"X-RateLimit-Limit:     {rate_limit_limit}")
        if rate_limit_policy:
            print(f"X-RateLimit-Policy:    {rate_limit_policy}")
        if rate_limit_remaining:
            print(f"X-RateLimit-Remaining: {rate_limit_remaining}")
        if rate_limit_reset:
            print(f"X-RateLimit-Reset:     {rate_limit_reset}")

        # Show actual search results
        print(f"\n{'='*60}")
        print("SEARCH RESULTS")
        print(f"{'='*60}")

        if response.status_code == 200:
            data = response.json()
            results = data.get("web", {}).get("results", [])

            if results:
                print(f"\n✅ Found {len(results)} results:\n")
                for i, result in enumerate(results, 1):
                    title = result.get("title", "Untitled")
                    url = result.get("url", "")
                    snippet = result.get("description", "")[:150]

                    print(f"{i}. {title}")
                    print(f"   {url}")
                    print(f"   {snippet}...\n")
            else:
                print("\n⚠️  No results found")
        else:
            print(f"\n❌ Search failed with status {response.status_code}")

        # Warnings
        print(f"\n{'='*60}")
        print("STATUS")
        print(f"{'='*60}")

        if response.status_code == 429:
            print("⛔ RATE LIMITED - You've exceeded your quota")
        elif response.status_code == 401:
            print("⛔ AUTHENTICATION ERROR - Check your API key")
        elif response.status_code == 200:
            print("✅ API key is valid and requests are working")

        # Check if low on quota
        if len(remaining) >= 2:
            monthly_remaining = remaining[1]
            monthly_limit = limits[1] if len(limits) >= 2 else None
            if monthly_limit and monthly_remaining < monthly_limit * 0.1:
                print(f"⚠️  WARNING: Less than 10% monthly quota remaining!")
            elif monthly_limit and monthly_remaining < monthly_limit * 0.25:
                print(f"⚠️  NOTICE: Less than 25% monthly quota remaining")

        print(f"\n{'='*60}\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    check_rate_limits()
