import requests
from bs4 import BeautifulSoup
import os
import re
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import urljoin, unquote

# --- CONFIGURATION ---
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")   # <-- Change this
BASE_URL = "http://23.147.64.113/movies/Other/"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VOD_DIR = os.path.join(SCRIPT_DIR, "vod")
CACHE_FILE = os.path.join(VOD_DIR, "movie_cache.json")
OUTPUT_M3U = os.path.join(VOD_DIR, "movies.m3u")
OUTPUT_XML = os.path.join(VOD_DIR, "epg.xml")

# Valid genres (updated to match TMDB common names)
VALID_GENRES = {
    "Action", "Adventure", "Animation", "Biography", "Comedy", 
    "Crime", "Drama", "Family", "Fantasy", "Horror", 
    "Music", "Musical", "Mystery", "Romance", "Sci-Fi", 
    "Short", "Thriller", "War", "Western", "Documentary"
}
# ---------------------

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"  # You can change to w780 or original

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

def get_movie_details(display_name, cache):
    if display_name in cache:
        return cache[display_name]
    
    if not TMDB_API_KEY:
        return None

    year_match = re.search(r'\((\d{4})\)', display_name)
    year = year_match.group(1) if year_match else None
    clean_title = re.sub(r'\(.*?\)', '', display_name).strip()

    try:
        # Step 1: Search for the movie
        search_url = "https://api.themoviedb.org/3/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": clean_title,
            "include_adult": False,
            "page": 1
        }
        if year:
            params["year"] = year

        response = requests.get(search_url, params=params, timeout=8)
        data = response.json()

        if data.get("results"):
            movie = data["results"][0]  # Best match
            movie_id = movie["id"]

            # Step 2: Get full details
            details_url = f"https://api.themoviedb.org/3/movie/{movie_id}"
            details_resp = requests.get(details_url, params={"api_key": TMDB_API_KEY}, timeout=8)
            details = details_resp.json()

            cache[display_name] = details
            return details

    except Exception as e:
        print(f"TMDB error for {display_name}: {e}")
    
    return None

def generate_vod_assets():
    if not os.path.exists(VOD_DIR):
        os.makedirs(VOD_DIR)
    
    cache = load_cache()
    m3u_content = ["#EXTM3U"]
    xml_root = ET.Element("tv")
    
    print(f"Connecting to: {BASE_URL}")
    try:
        response = requests.get(BASE_URL, timeout=15)
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
            full_url = urljoin(BASE_URL, href)
            
            details = get_movie_details(display_name, cache)
            
            # --- Extract Data ---
            if isinstance(details, dict):
                title = details.get("title") or details.get("original_title", display_name)
                poster_path = details.get("poster_path")
                poster = f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else ""
                plot_text = details.get("overview", "No description available.").replace('"', "'")
                year_val = str(details.get("release_date", ""))[:4] if details.get("release_date") else ""
                
                # Genre handling
                genres = details.get("genres", [])
                genre_list = "Other"
                if genres:
                    first_genre = genres[0]["name"]
                    if first_genre in VALID_GENRES:
                        genre_list = first_genre
                    else:
                        genre_list = "Other"
            else:
                title = display_name
                poster = ""
                plot_text = "No description available."
                genre_list = "Other"
                year_val = ""

            if year_val and year_val not in title:
                final_title = f"{title} ({year_val})"
            else:
                final_title = title

            logo = f' tvg-logo="{poster}"' if poster else ""
            
            # M3U Entry
            m3u_content.append(
                f'#EXTINF:-1 tvg-id="{display_name}" tvg-name="{display_name}"{logo} '
                f'plot="{plot_text}" group-title="{genre_list}",{final_title}'
            )
            m3u_content.append(full_url)

            # XMLTV Entry
            chan = ET.SubElement(xml_root, "channel", id=display_name)
            ET.SubElement(chan, "display-name").text = final_title
            
            start = datetime.now().strftime("%Y%m%d000000 +0000")
            stop = (datetime.now() + timedelta(days=7)).strftime("%Y%m%d235959 +0000")
            
            prog = ET.SubElement(xml_root, "programme", start=start, stop=stop, channel=display_name)
            ET.SubElement(prog, "title").text = final_title
            ET.SubElement(prog, "desc").text = plot_text
            ET.SubElement(prog, "category").text = genre_list

    # Save Files
    with open(OUTPUT_M3U, "w", encoding="utf-8") as f:
        f.write("\n".join(m3u_content))
    
    tree = ET.ElementTree(xml_root)
    ET.indent(tree, space="  ", level=0)
    tree.write(OUTPUT_XML, encoding="utf-8", xml_declaration=True)
    
    save_cache(cache)
    print(f"Update complete. Processed {len(m3u_content)//2} movies.")

if __name__ == "__main__":
    generate_vod_assets()
