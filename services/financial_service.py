import requests
import logging
import time
from functools import wraps
from datetime import datetime
from requests.adapters import HTTPAdapter
from utils.cache import set_cache

logger = logging.getLogger(__name__)

# ======================================
# AYARLAR
# ======================================
CACHE_TTL = 600
API_TIMEOUT = (5, 15)  # 5s bağlantı, 15s okuma (JSON büyük olduğu için okuma süresini artırdık)
API_URL_V4 = "https://finans.truncgil.com/v4/today.json"

# ======================================
# OPTİMİZE EDİLMİŞ SESSION & HEADERS
# ======================================
session = requests.Session()
adapter = HTTPAdapter(pool_connections=2, pool_maxsize=4)
session.mount("https://", adapter)

# Gerçek bir tarayıcı gibi davranıyoruz
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://finans.truncgil.com/",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8",
    "Connection": "keep-alive"
}

def get_safe_float(value):
    try:
        if isinstance(value, (int, float)): return float(value)
        v = str(value).strip().replace("%", "").replace("$", "").replace(" ", "")
        if '.' in v and ',' in v: v = v.replace(".", "").replace(",", ".")
        elif ',' in v: v = v.replace(",", ".")
        return float(v)
    except: return 0.0

# ======================================
# DATA PROCESSING (AYIKLAMA)
# ======================================

def process_currencies(data):
    codes = ["USD", "EUR", "GBP", "JPY", "CHF", "CNY", "CAD", "AUD", "SAR", "AED"]
    result = []
    for code in codes:
        if code in data and data[code].get("Type") == "Currency":
            item = data[code]
            selling = get_safe_float(item.get("Selling"))
            result.append({
                "code": code,
                "name": item.get("Name", code),
                "rate": round(selling, 4) if selling < 10 else round(selling, 2),
                "change_percent": round(get_safe_float(item.get("Change")), 2)
            })
    return result

def process_golds(data):
    mapping = {"GRA": "Gram Altın", "CEYREKALTIN": "Çeyrek Altın", "YARIMALTIN": "Yarım Altın", "TAMALTIN": "Tam Altın", "CUMHURIYETALTINI": "Cumhuriyet Altını"}
    result = []
    for code, name in mapping.items():
        if code in data:
            item = data[code]
            result.append({
                "name": name,
                "rate": round(get_safe_float(item.get("Selling")), 2),
                "change_percent": round(get_safe_float(item.get("Change")), 2)
            })
    return result

def process_silvers(data):
    if "GUMUS" in data:
        item = data["GUMUS"]
        return [{
            "name": "Gümüş",
            "rate": round(get_safe_float(item.get("Selling")), 4),
            "change_percent": round(get_safe_float(item.get("Change")), 2)
        }]
    return []

# ======================================
# ANA SENKRONİZASYON FONKSİYONU
# ======================================

def sync_financial_data():
    """
    API'yi 1 kere çağırır, tüm kategorileri ayıklar ve Redis'e ayrı ayrı yazar.
    """
    try:
        logger.info("🔄 Finansal veriler güncelleniyor (Tekil İstek)...")
        
        response = session.get(API_URL_V4, headers=HEADERS, timeout=API_TIMEOUT)
        response.raise_for_status()
        
        # JSON kontrolü
        try:
            full_data = response.json()
        except Exception as e:
            logger.error(f"❌ JSON Decode Hatası: {str(e)[:100]}")
            return False

        update_date = full_data.get("Update_Date", "Bilinmiyor")

        # 1. Dövizleri İşle & Kaydet
        currencies = process_currencies(full_data)
        if currencies:
            set_cache('kurabak:currencies:all', {
                "success": True, "count": len(currencies), "data": currencies, "update_date": update_date
            }, CACHE_TTL)

        # 2. Altınları İşle & Kaydet
        golds = process_golds(full_data)
        if golds:
            set_cache('kurabak:golds:all', {
                "success": True, "count": len(golds), "data": golds, "update_date": update_date
            }, CACHE_TTL)

        # 3. Gümüşü İşle & Kaydet
        silvers = process_silvers(full_data)
        if silvers:
            set_cache('kurabak:silvers:all', {
                "success": True, "count": len(silvers), "data": silvers, "update_date": update_date
            }, CACHE_TTL)

        logger.info(f"✅ Tüm veriler başarıyla güncellendi (Tarih: {update_date})")
        return True

    except Exception as e:
        logger.error(f"❌ sync_financial_data Kritik Hata: {e}")
        return False
