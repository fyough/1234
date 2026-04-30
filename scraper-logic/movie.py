import requests
from bs4 import BeautifulSoup
import os
import json
from urllib.parse import urljoin, unquote

# --- CONFIGURATION ---
BASE_URL = "http://64.52.81.50:8080/VOD/MOVIES/"
OMDB_API_KEY = "76495146"
CACHE_FILE = "scraper-logic/vod/movie_cache.json"
OUTPUT_M3U = "scraper-logic/vod/movies.m3u"

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=4)

def get_movie_details(display_name, cache):
    # Check cache first
    if display_name in cache:
        return cache[display_name]

    # If not in cache, try OMDb
    try:
        response = requests.get(f"http://www.omdbapi.com/?t={display_name}&apikey={OMDB_API_KEY}", timeout=10)
        data = response.json()
        
        if data.get("Response") == "True":
            movie_info = {
                "title": data.get("Title"),
                "poster": data.get("Poster"),
                "plot": data.get("Plot"),
                "year": data.get("Year")
            }
            cache[display_name] = movie_info
            return movie_info
        elif data.get("Error") == "Request limit reached!":
            return "LIMIT_REACHED"
    except Exception as e:
        print(f"Error fetching OMDb for {display_name}: {e}")
    
    return None

def generate_playlist():
    cache = load_cache()
    video_exts = ('.mp4', '.mkv', '.avi', '.mov')
    m3u_lines = ["#EXTM3U"]
    
    print(f"Fetching file list from {BASE_URL}...")
    try:
        response = requests.get(BASE_URL, timeout=20)
        soup = BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"Failed to reach server: {e}")
        return

    limit_hit = False
    movies_processed = 0

    for link in soup.find_all('a'):
        href = link.get('href')
        if href and href.lower().endswith(video_exts):
            # 1. Basic Info (Always available)
            display_name = os.path.splitext(unquote(href).strip('/'))[0]
            full_url = urljoin(BASE_URL, href)
            
            # 2. Enrichment (Try to get high-quality info)
            details = None
            if not limit_hit:
                details = get_movie_details(display_name, cache)
                if details == "LIMIT_REACHED":
                    print("!!! OMDb API Limit Reached. Using cache/defaults for remaining files.")
                    limit_hit = True
                    details = cache.get(display_name) 
            else:
                # Limit already hit this run, check if we have it in cache
                details = cache.get(display_name)

            # 3. Build M3U Entry
            # Use enriched data if we have it, otherwise fallback to filename
            title = details['title'] if details and details.get('title') else display_name
            poster = details['poster'] if details and details.get('poster') and details['poster'] != "N/A" else ""
            plot = details['plot'] if details and details.get('plot') else "No description available."
            
            entry = f'#EXTINF:-1 tvg-name="{display_name}" tvg-logo="{poster}" group-title="VOD Movies", {title}\n'
            entry += f'#EXTDESCRIPTION: {plot}\n'
            entry += f'{full_url}'
            m3u_lines.append(entry)
            movies_processed += 1

    # Save everything
    with open(OUTPUT_M3U, 'w', encoding='utf-8') as f:
        f.write("\n".join(m3u_lines))
    
    save_cache(cache)
    print(f"Playlist generated with {movies_processed} entries.")

if __name__ == "__main__":
    generate_playlist()
