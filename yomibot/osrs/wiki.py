import asyncio
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import os

from config.config import config

# Configure the Gemini API
if config.gemini_api_key:
    genai.configure(api_key=config.gemini_api_key)

# System prompt for Gemini
SYSTEM_PROMPT = """
You are an Old School RuneScape (OSRS) expert assistant. Your task is to answer questions about OSRS using information provided from the OSRS Wiki.

Guidelines:
1. Use only the provided wiki information to answer questions
2. If the information doesn't contain the answer, admit you don't know
3. Format your responses using Discord-safe formatting (no LaTeX formulas)
4. Use ** for bold, * for italic, ` for inline code, and ``` for code blocks
5. Keep your answers concise and relevant to OSRS (Your answer must be less than 2000 characters long)

Remember that you're helping players understand game mechanics, items, quests, and other aspects of Old School RuneScape.
"""

# Helper functions for OSRS Wiki integration
def clean_text(text):
    """Clean text by removing extra whitespace and newlines"""
    return ' '.join(text.split())

def render_table_to_text(table):
    """Render an HTML table element into a text-formatted table"""
    rows = table.find_all('tr')
    lines = []
    for row in rows:
        cells = row.find_all(['th', 'td'])
        cell_texts = [clean_text(cell.get_text()) for cell in cells]
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

def fetch_osrs_wiki(page_name):
    """Fetch content from OSRS wiki page, following redirects if necessary"""
    original_page_name = page_name
    url = f"https://oldschool.runescape.wiki/w/{page_name}"
    
    # First check if the page redirects
    redirect_url = find_redirect_target(url)
    if redirect_url:
        # Extract the redirected page name from the URL
        redirected_page_name = redirect_url.split("/w/")[-1]
        print(f"Page {page_name} redirects to {redirected_page_name}")
        # Update the page name and URL
        page_name = redirected_page_name
        url = redirect_url
    
    response = requests.get(url, headers={"User-Agent": "OSRS Wiki Assistant/1.0"})
    if response.status_code != 200:
        return f"Failed to download page: {url} (Status code: {response.status_code})", original_page_name, page_name
    
    html_content = response.text
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
        rendered_tables = []
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
                elif header_text in ["Combat stats", "Used in recommended equipment", "Gallery", "Gallery (historical)", "History", "Trivia", "References", "Sound effects"]:
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
                table_text = render_table_to_text(el)
                #rendered_tables.append(table_text)
            elif in_changes and el.name == 'td':
                if el.has_attr('data-sort-value'):
                    output += "\n" + el['data-sort-value'] + "\n"
        if rendered_tables:
            output += "\n=== Rendered Tables ===\n"
            for idx, table in enumerate(rendered_tables, start=1):
                output += f"\nTable {idx}:\n{table}\n"
    
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

async def identify_wiki_pages(user_query):
    """Use Gemini to identify relevant wiki pages for the query"""
    if not config.gemini_api_key:
        print("Gemini API key not set")
        return []
        
    model = genai.GenerativeModel(config.gemini_model)
    prompt = f"""
    You are an assistant that helps determine which Old School RuneScape (OSRS) wiki pages to fetch based on user queries.
    Identify UP TO 5 most relevant OSRS wiki page to comprehensively answer this question. (but only as many as necessary and strictly relevant to the query)
    Respond ONLY with the exact page names separated by commas. No additional text or explanation.
    For example: "Abyssal_whip, Wilderness, Slayer"
    
    User Query: {user_query}
    """
    
    try:
        response = await asyncio.to_thread(
            lambda: model.generate_content(prompt).text
        )
        # Clean up the response to get just the page names
        page_names = [name.strip() for name in response.split(',')]
        print(f"Identified wiki pages: {page_names}")  # Debug print
        return page_names
    except Exception as e:
        print(f"Error identifying wiki pages: {e}")
        return []

async def process_user_query(user_query: str) -> str:
    """Process a user query about OSRS using Gemini and the OSRS Wiki"""
    if not config.gemini_api_key:
        return "Sorry, the OSRS Wiki assistant is not available because the Gemini API key is not set."
        
    try:
        # Identify relevant wiki pages
        page_names = await identify_wiki_pages(user_query)
        
        if not page_names:
            return "I couldn't determine which wiki pages to search. Please try a more specific query about OSRS."
        
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
        
        # Process the content with Gemini
        model = genai.GenerativeModel(config.gemini_model)
        
        prompt = f"""
        {SYSTEM_PROMPT}
        
        User Query: {user_query}
        
        OSRS Wiki Information:
        {wiki_content}
        
        Based on the above information from the OSRS Wiki, please provide a helpful answer to the user's query.
        Remember to cite your sources using the URL format: https://oldschool.runescape.wiki/w/[page_name]
        """
        
        response = await asyncio.to_thread(
            lambda: model.generate_content(prompt).text
        )
        
        # Add source citations if not already included
        if not any(f"https://oldschool.runescape.wiki/w/{page.replace(' ', '_')}" in response for page in updated_page_names):
            sources = "\n\nSources:"
            for page in updated_page_names:
                # Wrap URL in angle brackets
                sources += f"\n- <https://oldschool.runescape.wiki/w/{page.replace(' ', '_')}>"
            
            # Make sure the response with sources doesn't exceed Discord's limit
            if len(response) + len(sources) <= 1990:
                response += sources
        else:
            # If URLs are already in the response, wrap them in angle brackets
            for page in updated_page_names:
                url = f"https://oldschool.runescape.wiki/w/{page.replace(' ', '_')}"
                modified_url = f"<https://oldschool.runescape.wiki/w/{page.replace(' ', '_')}>"
                response = response.replace(url, modified_url)
    
        return response
        
    except Exception as e:
        return f"Error processing your query: {str(e)}"

# Register OSRS commands
def setup_osrs_commands(bot):
    @bot.command(name='askyomi')
    async def askyomi(ctx, *, user_query: str):
        # Let the user know we're processing their request
        await ctx.send("Processing your request, this may take a moment...")
        
        response = await process_user_query(user_query)
        
        # Discord has a 2000 character limit per message
        if len(response) > 1990:
            # Split into chunks of ~1990 characters
            chunks = [response[i:i + 1990] for i in range(0, len(response), 1990)]
            for i, chunk in enumerate(chunks):
                await ctx.send(f"{chunk}" + ("" if i == len(chunks) - 1 else " (continued...)"))
        else:
            await ctx.send(response)