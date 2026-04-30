import requests
from bs4 import BeautifulSoup
import os
import re
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import urljoin, unquote

# --- CONFIGURATION ---
OMDB_API_KEY = os.environ.get("OMDB_API_KEY")
BASE_URL = "http://23.147.64.113/movies/Other/"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VOD_DIR = os.path.join(SCRIPT_DIR, "vod")
CACHE_FILE = os.path.join(VOD_DIR, "movie_cache.json")
OUTPUT_M3U = os.path.join(VOD_DIR, "movies.m3u")
OUTPUT_XML = os.path.join(VOD_DIR, "epg.xml")
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

def get_movie_details(display_name, cache):
    if display_name in cache:
        return cache[display_name]
    
    if not OMDB_API_KEY:
        return None
    
    # Extract year and clean the title for a better API search
    year_match = re.search(r'\((\d{4})\)', display_name)
    year = year_match.group(1) if year_match else ""
    clean_title = re.sub(r'\(.*?\)', '', display_name).strip()

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
            cache[display_name] = data
            return data
        elif data.get("Error") == "Request limit reached!":
            return "LIMIT_REACHED"
    except Exception:
        pass
    return None

def generate_vod_assets():
    if not os.path.exists(VOD_DIR):
        os.makedirs(VOD_DIR)
    
    cache = load_cache()
    m3u_content = ["#EXTM3U"]
    
    # XMLTV Root Setup
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
    limit_hit = False
    
    for link in soup.find_all('a'):
        href = link.get('href')
        if href and href.lower().endswith(video_exts):
            display_name = os.path.splitext(unquote(href).strip('/'))[0]
            full_url = urljoin(BASE_URL, href)
            
            details = None
            if not limit_hit:
                details = get_movie_details(display_name, cache)
                if details == "LIMIT_REACHED":
                    print("OMDb limit reached. Continuing with basic file info...")
                    limit_hit = True
                    details = cache.get(display_name)
            else:
                details = cache.get(display_name)
            
            # --- Extract Data ---
            if isinstance(details, dict):
                title = details.get("Title", display_name)
                poster = details.get("Poster", "")
                plot_text = details.get("Plot", "No description available.").replace('"', "'")
                year_val = details.get("Year", "")
                
                if year_val and year_val not in title:
                    final_title = f"{title} ({year_val})"
                else:
                    final_title = title
            else:
                final_title = display_name
                poster = ""
                plot_text = "No description available."

            logo = f' tvg-logo="{poster}"' if poster.startswith("http") else ""
            
            # --- 1. Update M3U (using plot instead of description) ---
            m3u_content.append(f'#EXTINF:-1 tvg-id="{display_name}" tvg-name="{display_name}"{logo} plot="{plot_text}" group-title="Movies",{final_title}')
            m3u_content.append(full_url)

            # --- 2. Update XMLTV (for TiviMate EPG support) ---
            chan = ET.SubElement(xml_root, "channel", id=display_name)
            ET.SubElement(chan, "display-name").text = final_title
            
            start = datetime.now().strftime("%Y%m%d000000 +0000")
            stop = (datetime.now() + timedelta(days=7)).strftime("%Y%m%d235959 +0000")
            
            prog = ET.SubElement(xml_root, "programme", start=start, stop=stop, channel=display_name)
            ET.SubElement(prog, "title").text = final_title
            ET.SubElement(prog, "desc").text = plot_text

    # Save M3U
    with open(OUTPUT_M3U, "w", encoding="utf-8") as f:
        f.write("\n".join(m3u_content))
    
    # Save XMLTV
    tree = ET.ElementTree(xml_root)
    ET.indent(tree, space="  ", level=0)
    tree.write(OUTPUT_XML, encoding="utf-8", xml_declaration=True)
    
    save_cache(cache)
    print(f"Update complete. Created M3U and EPG for {len(m3u_content)//2} movies.")

if __name__ == "__main__":
    generate_vod_assets()
