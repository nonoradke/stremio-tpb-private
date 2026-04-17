from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
from bs4 import BeautifulSoup
import re
import urllib.parse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CONFIG ---
TPB_URL = "https://thepiratebay.party" 

# --- HELPER ---
def get_meta(type: str, id: str):
    try:
        url = f"https://v3-cinemeta.strem.io/meta/{type}/{id}.json"
        resp = requests.get(url, timeout=5)
        data = resp.json()
        meta = data.get('meta', {})
        name = meta.get('name')
        year = meta.get('year')
        if name and year:
            return f"{name} {year}"
        return name
    except:
        return None

def detect_quality(text):
    text_lower = text.lower()
    q = []
    if "2160p" in text_lower or "4k" in text_lower: q.append("4K")
    elif "1080p" in text_lower: q.append("1080p")
    elif "720p" in text_lower: q.append("720p")
    elif "480p" in text_lower: q.append("480p")
    
    if "bluray" in text_lower: q.append("BluRay")
    elif "web-dl" in text_lower or "webdl" in text_lower: q.append("WEB-DL")
    elif "webrip" in text_lower: q.append("WEBRip")
    elif "hdr" in text_lower: q.append("HDR")
    elif "cam" in text_lower: q.append("CAM")
    elif "ts" in text_lower: q.append("TS")
    
    return " ".join(q) if q else "SD"

@app.get("/manifest.json")
def get_manifest():
    return {
        "id": "org.tpb.v7.final",
        "version": "7.1.0",
        "name": "TPB V7.1 (Regex Shield)",
        "description": "Correct Title + Perfect Series Filter",
        "types": ["movie", "series"],
        "catalogs": [],
        "resources": ["stream"],
        "idPrefixes": ["tt"]
    }

@app.get("/stream/{type}/{id}.json")
def get_stream(type: str, id: str):
    # 1. Parsing parameter ID dari Stremio
    parts = id.split(":")
    imdb_id = parts[0]
    
    is_series = type == "series" and len(parts) >= 3
    season = int(parts[1]) if is_series else 0
    episode = int(parts[2]) if is_series else 0

    base_query = get_meta(type, imdb_id)
    if not base_query: return {"streams": []}
    
    # 2. Inject episode ke string pencarian biar query lebih ringan
    query = f"{base_query} S{season:02d}E{episode:02d}" if is_series else base_query
    
    print(f"🔍 Searching: {query}")

    try:
        safe_query = urllib.parse.quote(query)
        url = f"{TPB_URL}/search/{safe_query}/0/7/0"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        streams = []
        
        for row in soup.select('tr'):
            magnet_tag = row.find('a', href=re.compile(r'^magnet:\?'))
            
            if magnet_tag:
                title_tag = None
                for link in row.find_all('a'):
                    href = link.get('href', '')
                    txt = link.get_text(strip=True)
                    if 'magnet:' in href: continue
                    if '/user/' in href: continue
                    if '/browse/' in href: continue 
                    if len(txt) < 2: continue 
                    title_tag = link
                    break
                
                if not title_tag:
                    title_tag = row.select_one('.detName a')

                file_name = title_tag.get_text(strip=True) if title_tag else "Unknown Title"
                name_upper = file_name.upper()

                # --- 3. HARD FILTER REGEX SHIELD ---
                # Blokir file kompilasi/sampah
                if any(ext in name_upper for ext in [".ZIP", ".RAR", "BATCH", "COMPLETE SEASON", "COMPLETE", "SEASON PACK"]):
                    continue 

                # Wajib nge-match ID SxxExx
                if is_series:
                    pattern = rf"S{season:02d}[^A-Z0-9]*E{episode:02d}"
                    if not re.search(pattern, name_upper):
                        continue
                # --- END FILTER ---

                row_text = row.get_text(" ", strip=True)
                size_match = re.search(r'(\d+(?:\.\d+)?\s*[KMGTP]i?B)', row_text, re.IGNORECASE)
                size = size_match.group(1) if size_match else "??"
                
                quality = detect_quality(file_name)
                
                tds = row.find_all('td')
                seeders = "0"
                for td in reversed(tds):
                    txt = td.get_text(strip=True)
                    if txt.isdigit():
                        seeders = txt
                        break

                magnet = magnet_tag['href']
                hash_match = re.search(r'btih:([a-zA-Z0-9]+)', magnet)

                if hash_match:
                    streams.append({
                        "name": f"TPB+ {quality}",
                        "title": f"{file_name}\n👤 {seeders}  💾 {size}",
                        "infoHash": hash_match.group(1),
                        "behaviorHints": {
                            "bingeGroup": f"tpb-{quality}"
                        }
                    })
        
        return {"streams": streams}

    except Exception as e:
        print(f"🔥 Error: {e}")
        return {"streams": []}
