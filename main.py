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

def parse_size_quality(text):
    # Cari size pake regex barbar (angka + GB/MB)
    # Contoh match: "Size 2.29 GiB" atau "2.29 GiB" atau "2.29 GB"
    size_match = re.search(r'(\d+(\.\d+)?\s*[KMGTP]i?B)', text, re.IGNORECASE)
    size = size_match.group(1) if size_match else "??"
    
    # Deteksi kualitas dari teks baris
    text_lower = text.lower()
    q = []
    if "2160p" in text_lower or "4k" in text_lower: q.append("4K")
    elif "1080p" in text_lower: q.append("1080p")
    elif "720p" in text_lower: q.append("720p")
    elif "480p" in text_lower: q.append("480p")
    
    if "bluray" in text_lower: q.append("BluRay")
    elif "web-dl" in text_lower or "webdl" in text_lower: q.append("WEB-DL")
    elif "hdr" in text_lower: q.append("HDR")
    
    quality = " ".join(q) if q else "SD"
    return size, quality

@app.get("/manifest.json")
def get_manifest():
    return {
        "id": "org.tpb.v5.debug",
        "version": "5.0.0",
        "name": "TPB V5 (Debug)",
        "description": "Brute force parsing",
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
        # Search URL default
        url = f"{TPB_URL}/search/{safe_query}/0/7/0"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        streams = []
        
        # --- DEBUG: Print 1 baris HTML pertama biar ketahuan strukturnya ---
        first_row = soup.find('tr')
        if first_row:
             # Kita print 500 karakter pertama dari baris tabel buat intip
            print(f"\n🐛 DEBUG HTML ROW: {str(first_row)[:500]}...\n")
        
        for row in soup.select('tr'):
            # Kita cari semua kolom (TD)
            tds = row.find_all('td')
            
            # Struktur TPB normal biasanya minimal 2 kolom
            if len(tds) < 2:
                continue
                
            # Kolom index 1 biasanya Judul + Deskripsi
            main_col = tds[1]
            main_text = main_col.get_text(" ", strip=True) # Ambil semua text di kolom itu
            
            magnet_tag = row.find('a', href=re.compile(r'^magnet:\?'))
            
            if magnet_tag:
                # 1. Cari Judul (Link pertama di kolom utama yg BUKAN magnet)
                title_tag = None
                for link in main_col.find_all('a'):
                    href = link.get('href', '')
                    # Judul biasanya link yg ngarah ke /torrent/ atau /description
                    if 'magnet:' not in href and ('/torrent/' in href or '/description' in href or 'view' in href):
                        title_tag = link
                        break
                
                # Fallback: Kalo gak nemu link spesifik, ambil link apapun yg teksnya panjang
                if not title_tag:
                     for link in main_col.find_all('a'):
                        if len(link.get_text()) > 5:
                            title_tag = link
                            break

                file_name = title_tag.get_text(strip=True) if title_tag else "TPB File (Check Debug)"
                
                # 2. Parse Size & Quality dari SELURUH teks di kolom itu
                size, quality = parse_size_quality(main_text)

                # 3. Cari Seeders (Cari angka di kolom sebelah kanan)
                seeders = "?"
                # Cek kolom index 2 (biasanya seeders)
                if len(tds) > 2:
                    txt = tds[2].get_text(strip=True)
                    if txt.isdigit(): seeders = txt
                
                # Fallback Seeders: Cek kolom terakhir
                if not seeders.isdigit() and len(tds) > 3:
                     # Kadang seeders ada di paling belakang (tds[-2])
                     if tds[-2].get_text(strip=True).isdigit():
                         seeders = tds[-2].get_text(strip=True)

                magnet = magnet_tag['href']
                hash_match = re.search(r'btih:([a-zA-Z0-9]+)', magnet)

                if hash_match:
                    streams.append({
                        "name": f"TPB+ {quality}",
                        "title": f"{file_name}\n👤 {seeders}  💾 {size}",
                        "infoHash": hash_match.group(1)
                    })
        
        print(f"✅ Dapet {len(streams)} streams!")
        return {"streams": streams}

    except Exception as e:
        print(f"🔥 Error: {e}")
        return {"streams": []}
