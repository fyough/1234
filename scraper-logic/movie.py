import requests
from bs4 import BeautifulSoup
import os
import re
import json
from urllib.parse import urljoin, unquote

# --- CONFIGURATION ---
OMDB_API_KEY = os.environ.get("OMDB_API_KEY")
BASE_URL = "http://23.147.64.113/movies/Other/"

# Ensures the script finds the 'vod' folder relative to movie.py
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
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=4)

def get_movie_details(title, cache):
    if title in cache:
        return cache[title]
    
    if not OMDB_API_KEY:
        return None
    
    # Extract year if present, e.g., "Movie Name (2024)"
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
    
    try:
        response = requests.get(BASE_URL, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"Failed to reach source: {e}")
        return

    video_exts = ('.mp4', '.mkv', '.avi', '.mov', '.m4v')
    
    for link in soup.find_all('a'):
        href = link.get('href')
        if href and href.lower().endswith(video_exts):
            display_name = os.path.splitext(unquote(href).strip('/'))[0]
            
            details = get_movie_details(display_name, cache)
            
            # Stop calling the API if the 1,000 daily limit is hit
            if details == "LIMIT_REACHED":
                print("OMDb limit reached. Saving current progress to cache...")
                break
                
            full_url = urljoin(BASE_URL, href)
            
            # Ensure details is a dictionary before calling .get()
            is_dict = isinstance(details, dict)
            poster = details.get("Poster", "") if is_dict else ""
            plot = details.get("Plot", "No description available.").replace('"', "'") if is_dict else ""
            year = details.get("Year", "") if is_dict else ""
            
            logo = f' tvg-logo="{poster}"' if poster.startswith("http") else ""
            m3u_content.append(f'#EXTINF:-1 tvg-name="{display_name}"{logo} description="{plot}" group-title="Other Movies",{display_name} ({year})')
            m3u_content.append(full_url)

    save_cache(cache)
    with open(OUTPUT_M3U, "w", encoding="utf-8") as f:
        f.write("\n".join(m3u_content))
    print(f"Update complete. Playlist saved to {OUTPUT_M3U}")

if __name__ == "__main__":
    generate_vod_m3u()
