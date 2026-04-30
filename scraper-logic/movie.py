import requests
from bs4 import BeautifulSoup
import os
import re
import json
from urllib.parse import urljoin, unquote

# --- CONFIGURATION ---
# Using the URL from your original script provided above
OMDB_API_KEY = os.environ.get("OMDB_API_KEY")
BASE_URL = "http://23.147.64.113/movies/Other/"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VOD_DIR = os.path.join(SCRIPT_DIR, "vod")
CACHE_FILE = os.path.join(VOD_DIR, "movie_cache.json")
OUTPUT_M3U = os.path.join(VOD_DIR, "movies.m3u")
# ---------------------

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_cache(cache):
    if not os.path.exists(VOD_DIR):
        os.makedirs(VOD_DIR)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=4)

def get_movie_details(title, cache):
    if title in cache:
        return cache[title]
    
    if not OMDB_API_KEY:
        return None
    
    year_match = re.search(r'\((\d{4})\)', title)
    year = year_match.group(1) if year_match else ""
    clean_title = re.sub(r'\(.*?\)', '', title).strip()

    params = {
        "apikey": OMDB_API_KEY, 
        "t": clean_title, 
        "y": year if year else None, 
        "plot": "short"
    }

    try:
        response = requests.get("http://www.omdbapi.com/", params=params, timeout=5)
        data = response.json()
        if data.get("Response") == "True":
            cache[title] = data
            return data
        elif data.get("Error") == "Request limit reached!":
            return "LIMIT_REACHED"
    except Exception:
        pass
    return None

def generate_vod_m3u():
    if not os.path.exists(VOD_DIR):
        os.makedirs(VOD_DIR)
    
    cache = load_cache()
    m3u_content = ["#EXTM3U"]
    
    print(f"Connecting to: {BASE_URL}")
    try:
        response = requests.get(BASE_URL, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"Failed to reach source: {e}")
        return

    video_exts = ('.mp4', '.mkv', '.avi', '.mov', '.m4v')
    limit_hit = False
    
    for link in soup.find_all('a'):
        href = link.get('href')
        if href and href.lower().endswith(video_exts):
            display_name = os.path.splitext(unquote(href).strip('/'))[0]
            full_url = urljoin(BASE_URL, href)
            
            # If we haven't hit the limit, try to get/fetch details
            details = None
            if not limit_hit:
                details = get_movie_details(display_name, cache)
                if details == "LIMIT_REACHED":
                    print("OMDb limit reached. Continuing with basic file info...")
                    limit_hit = True
                    details = cache.get(display_name) # Check if it's already in cache
            else:
                # Limit was hit earlier, just use cache if it exists
                details = cache.get(display_name)
            
            # --- Build M3U Entry ---
            is_dict = isinstance(details, dict)
            poster = details.get("Poster", "") if is_dict else ""
            plot = details.get("Plot", "No description available.").replace('"', "'") if is_dict else ""
            year_val = details.get("Year", "") if is_dict else ""
            
            logo = f' tvg-logo="{poster}"' if poster.startswith("http") else ""
            title_line = f'{display_name} ({year_val})' if year_val else display_name
            
            # Changed group-title from "Other Movies" to "Movies"
            m3u_content.append(f'#EXTINF:-1 tvg-name="{display_name}"{logo} description="{plot}" group-title="Movies",{title_line}')
            m3u_content.append(full_url)

    # Save both files
    save_cache(cache)
    with open(OUTPUT_M3U, "w", encoding="utf-8") as f:
        f.write("\n".join(m3u_content))
    print(f"Update complete. Created playlist with {len(m3u_content)//2} movies.")

if __name__ == "__main__":
    generate_vod_m3u()
