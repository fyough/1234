import requests
from bs4 import BeautifulSoup
import os
import re
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import urljoin, unquote

# --- CONFIGURATION ---
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
BASE_URL = os.environ.get("BASE_URL")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VOD_DIR = os.path.join(SCRIPT_DIR, "vod")
CACHE_FILE = os.path.join(VOD_DIR, "movie_cache.json")
OUTPUT_M3U = os.path.join(VOD_DIR, "movies.m3u")
OUTPUT_XML = os.path.join(VOD_DIR, "epg.xml")

VALID_GENRES = {
    "Action", "Adventure", "Animation", "Biography", "Comedy", 
    "Crime", "Drama", "Family", "Fantasy", "Horror", 
    "Music", "Musical", "Mystery", "Romance", "Sci-Fi", 
    "Short", "Thriller", "War", "Western", "Documentary"
}

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
DEFAULT_POSTER_URL = "https://github.com/fyough/1234/blob/main/scraper-logic/vod/no-image.png?raw=true"
# ---------------------

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}

def save_cache(cache):
    os.makedirs(VOD_DIR, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=4)

def clean_title_for_search(display_name):
    """Clean filename for better TMDB search"""
    clean = re.sub(r'\(\d{4}\)', '', display_name)           # Remove year
    clean = re.sub(r'\b(1080p|720p|2160p|4K|BluRay|WEBRip|HDRip|x264|x265|H265|AAC|DD5|DD+|HEVC|REMUX)\b', '', clean, flags=re.I)
    clean = re.sub(r'[\.\-_]', ' ', clean)                   # Replace dots, hyphens, underscores
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

def get_movie_details(display_name, cache):
    if display_name in cache:
        return cache[display_name]

    if not TMDB_API_KEY:
        return None

    original_clean = clean_title_for_search(display_name)
    year_match = re.search(r'\((\d{4})\)', display_name)
    year = year_match.group(1) if year_match else None

    search_attempts = [
        (original_clean, year),                    # Best attempt
        (original_clean, None),                    # Without year
        (display_name.replace('.', ' '), year),    # Minimal cleaning
    ]

    for query, y in search_attempts:
        try:
            params = {
                "api_key": TMDB_API_KEY,
                "query": query,
                "include_adult": False,
                "page": 1
            }
            if y:
                params["year"] = y

            resp = requests.get("https://api.themoviedb.org/3/search/movie", 
                              params=params, timeout=10)
            data = resp.json()

            if data.get("results"):
                movie = data["results"][0]
                movie_id = movie["id"]

                # Get full details
                detail_resp = requests.get(
                    f"https://api.themoviedb.org/3/movie/{movie_id}",
                    params={"api_key": TMDB_API_KEY},
                    timeout=10
                )
                details = detail_resp.json()

                cache[display_name] = details
                return details

        except Exception:
            continue

    # Cache failure to avoid retrying every run
    cache[display_name] = None
    return None

def generate_vod_assets():
    cache = load_cache()
    m3u_content = ["#EXTM3U"]
    xml_root = ET.Element("tv")

    if not BASE_URL:
        print("Error: BASE_URL environment variable is not set.")
        return

    try:
        response = requests.get(BASE_URL, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"Failed to reach source: {e}")
        return

    video_exts = ('.mp4', '.mkv', '.avi', '.mov', '.m4v')
    processed = 0

    for link in soup.find_all('a'):
        href = link.get('href')
        if not href or not href.lower().endswith(video_exts):
            continue

        display_name = os.path.splitext(unquote(href).strip('/'))[0]
        full_url = urljoin(BASE_URL, href)

        details = get_movie_details(display_name, cache)

        if isinstance(details, dict):
            title = details.get("title") or details.get("original_title", display_name)
            poster_path = details.get("poster_path")
            # If TMDB has a poster, use it; otherwise, use the default
            poster = f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else DEFAULT_POSTER_URL
            
            plot_text = details.get("overview", "").strip()
            if not plot_text:
                plot_text = "No description available."
            else:
                plot_text = plot_text.replace('"', "'")

            year_val = str(details.get("release_date", ""))[:4] if details.get("release_date") else ""

            # Genre
            genres = [g["name"] for g in details.get("genres", [])]
            genre_list = genres[0] if genres and genres[0] in VALID_GENRES else "Other"
        else:
            title = display_name
            poster = DEFAULT_POSTER_URL
            plot_text = "No description available."
            genre_list = "Other"
            year_val = ""

        if year_val and year_val not in title:
            final_title = f"{title} ({year_val})"
        else:
            final_title = title

        logo = f' tvg-logo="{poster}"' if poster else ""

        m3u_content.append(
            f'#EXTINF:-1 tvg-id="{display_name}" tvg-name="{display_name}"{logo} '
            f'plot="{plot_text}" group-title="{genre_list}",{final_title}'
        )
        m3u_content.append(full_url)

        # XMLTV
        chan = ET.SubElement(xml_root, "channel", id=display_name)
        ET.SubElement(chan, "display-name").text = final_title
        
        start = datetime.now().strftime("%Y%m%d000000 +0000")
        stop = (datetime.now() + timedelta(days=7)).strftime("%Y%m%d235959 +0000")
        
        prog = ET.SubElement(xml_root, "programme", start=start, stop=stop, channel=display_name)
        ET.SubElement(prog, "title").text = final_title
        ET.SubElement(prog, "desc").text = plot_text
        ET.SubElement(prog, "category").text = genre_list

        processed += 1

    # Save files
    with open(OUTPUT_M3U, "w", encoding="utf-8") as f:
        f.write("\n".join(m3u_content))

    tree = ET.ElementTree(xml_root)
    ET.indent(tree, space="  ", level=0)
    tree.write(OUTPUT_XML, encoding="utf-8", xml_declaration=True)

    save_cache(cache)
    print(f"Update complete. Processed {processed} movies.")

if __name__ == "__main__":
    generate_vod_assets()
