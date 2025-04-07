import re

def collect_source_urls(player_sources, wiki_sources, web_sources):
    """Collect all source URLs into a single list"""
    all_sources = []
    
    # Add player sources
    for source in player_sources:
        all_sources.append(source['url'])
    
    # Add wiki sources
    for source in wiki_sources:
        all_sources.append(source['url'])
    
    # Add web sources
    for source in web_sources:
        all_sources.append(source['url'])
    
    return all_sources

def build_sources_section(player_sources, wiki_sources, web_sources):
    """Build a sources section for the response"""
    sources = collect_source_urls(player_sources, wiki_sources, web_sources)
    
    if not sources:
        return ""
        
    sources_section = "\n\nSources:"
    for url in sources:
        # Ensure consistent formatting without prefixes like "Player data:"
        clean_url = url.split("://")[-1] if "://" in url else url
        sources_section += f"\n- <https://{clean_url}>"
        
    return sources_section

def ensure_all_sources_included(response, player_sources, wiki_sources, web_sources):
    """Ensure all sources are included in the response using a robust method."""
    # 1. Collect all expected source URLs
    all_sources = collect_source_urls(player_sources, wiki_sources, web_sources)
    unique_sources = sorted(list(set(all_sources))) # Ensure uniqueness and consistent order

    # 2. If no sources expected, return the response as is
    if not unique_sources:
        return response

    # 3. Define patterns
    url_pattern = re.compile(r'<(https?://[^\s<>"]+)>')
    # Pattern to find "Sources:" or "Source:" header, case-insensitive, possibly preceded by newlines/whitespace
    sources_header_pattern = re.compile(r'^([ \t]*\n)?(Sources?):', re.MULTILINE | re.IGNORECASE)

    # 4. Try to find an existing "Sources:" section
    header_match = sources_header_pattern.search(response)
    existing_section_valid_and_complete = False

    if header_match:
        sources_start_index = header_match.start()
        # Extract text from the header onwards
        sources_section_text = response[sources_start_index:]
        # Find all URLs within this potential section
        existing_urls = sorted(list(set(url_pattern.findall(sources_section_text))))

        # Check if the existing section contains exactly the set of expected unique URLs
        if set(existing_urls) == set(unique_sources):
            existing_section_valid_and_complete = True
            print("Existing Sources section is valid and complete.")
        else:
            print(f"Existing Sources section found but is incomplete or incorrect. Expected: {unique_sources}, Found: {existing_urls}")
    else:
        print("No existing Sources section found.")
        # Check if URLs exist *without* a header, indicating a malformed response from LLM
        urls_without_header = url_pattern.findall(response)
        if urls_without_header:
            print("Found URLs without a Sources header, indicating LLM ignored instructions.")


    # 5. If section is valid and complete, return (potentially after minor cleanup)
    if existing_section_valid_and_complete:
        # Minor cleanup: remove extra newlines within the section
        sources_start_index = header_match.start()
        pre_sources = response[:sources_start_index]
        sources_part = response[sources_start_index:]
        # Replace multiple consecutive newlines before a source item with a single newline
        sources_part = re.sub(r'\n\s*\n(- <https?://)', r'\n\1', sources_part)
        # Ensure the header itself is preceded by exactly two newlines
        pre_sources = pre_sources.rstrip() + "\n\n"
        # Ensure the header line itself is just "Sources:"
        sources_part = re.sub(r'^(Sources?):', 'Sources:', sources_part.strip(), count=1, flags=re.IGNORECASE)

        return pre_sources + sources_part

    # 6. Otherwise (section missing, incomplete, or malformed), rebuild the sources section
    print("Rebuilding Sources section.")
    response_base = response # Start with the original response

    # If a header existed, strip everything from the header onwards
    if header_match:
        response_base = response[:header_match.start()].rstrip()
    else:
        # If no header, try to remove trailing lines that look like source URLs
        lines = response.rstrip().split('\n')
        last_non_url_line_index = -1
        # Find the index of the last line that does *not* look like a source URL line
        for i in range(len(lines) - 1, -1, -1):
             # A line is likely a source URL if it starts with '- <http' or just '<http' after stripping whitespace
            line_content = lines[i].strip()
            if not (line_content.startswith('- <http') or line_content.startswith('<http')):
                last_non_url_line_index = i
                break

        # If we found loose URLs at the end (i.e., the last line was a URL line)
        if last_non_url_line_index < len(lines) - 1:
            print(f"Stripping trailing URL-like lines from index {last_non_url_line_index + 1}")
            # Take lines up to and including the last non-URL line
            response_base = '\n'.join(lines[:last_non_url_line_index + 1]).rstrip()
        else:
            # No trailing URL lines found, keep the response as is
             response_base = response.rstrip()


    # Build the new section string
    new_sources_section = "\n\nSources:"
    for url in unique_sources:
        new_sources_section += f"\n- <{url}>"

    # Combine base response with the new section
    final_response = response_base + new_sources_section

    return final_response

def clean_url_patterns(text, url, escaped_url=None):
    """Clean and format URLs consistently"""
    if escaped_url is None:
        escaped_url = url
    
    # Handle the specific broken format with both escaped and unescaped versions
    # ([URL](<URL>))
    text = re.sub(r'\(\[\s*' + re.escape(escaped_url) + r'\s*\]\s*\(\s*<\s*' + re.escape(url) + r'\s*>\s*\)\s*\)', f"(<{url}>)", text)
    
    # Handle other common patterns
    patterns = [
        (f"[{escaped_url}]({url})", f"<{url}>"),  # Markdown with escaped URL
        (f"[{url}]({url})", f"<{url}>"),  # Markdown style
        (f"[<{url}>]", f"<{url}>"),  # Bracketed angle brackets
        (f"(<{url}>)", f"<{url}>"),  # Parenthesized angle brackets - preserve this format
        (f"[{url}]", f"<{url}>"),  # Simple brackets
        (f"({url})", f"<{url}>"),  # Simple parentheses
    ]
    
    # Apply each pattern replacement
    for pattern, replacement in patterns:
        text = text.replace(pattern, replacement)
    
    # Ensure the URL is wrapped in angle brackets if it's not already
    # But avoid double-wrapping URLs that are already properly formatted
    if f"<{url}>" not in text and url in text:
        # Use regex with word boundaries to avoid partial replacements
        text = re.sub(r'(?<!\<)' + re.escape(url) + r'(?!\>)', f"<{url}>", text)
    
    return text