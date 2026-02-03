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
        "version": "7.0.0",
        "name": "TPB V7 (Perfect Fix)",
        "description": "Correct Title + Correct Size",
        "types": ["movie", "series"],
        "catalogs": [],
        "resources": ["stream"],
        "idPrefixes": ["tt"]
    }

@app.get("/stream/{type}/{id}.json")
def get_stream(type: str, id: str):
    imdb_id = id.split(":")[0]
    query = get_meta(type, imdb_id)
    if not query: return {"streams": []}
    
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
                # 1. Logic Judul
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

                # 2. Logic Size (Full Scan)
                row_text = row.get_text(" ", strip=True)
                size_match = re.search(r'(\d+(?:\.\d+)?\s*[KMGTP]i?B)', row_text, re.IGNORECASE)
                size = size_match.group(1) if size_match else "??"
                
                quality = detect_quality(file_name)
                
                # 3. Logic Seeders
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
