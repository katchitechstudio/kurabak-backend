"""
Financial Service - Tek İstek, Tüm Veriler
Özellikler:
- Sadece 1 HTTP isteği (bot korumasına karşı)
- V4 başarısız olursa V3'e otomatik geçiş
- Bozuk JSON hatalarına karşı koruma
- Retry mekanizması (3 deneme)
- Connection pooling optimizasyonu
"""
import requests
import logging
import time
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from utils.cache import set_cache

logger = logging.getLogger(__name__)

# ======================================
# AYARLAR
# ======================================
CACHE_TTL = 180  # 3 dakika
API_TIMEOUT = (10, 20)  # Daha uzun timeout (10s bağlantı, 20s okuma)

# Dual API support
API_URL_V4 = "https://finans.truncgil.com/v4/today.json"
API_URL_V3 = "https://finans.truncgil.com/v3/today.json"

# ======================================
# OPTİMİZE EDİLMİŞ SESSION
# ======================================
def create_session():
    """
    Connection pooling ve retry stratejisi ile optimize edilmiş session
    """
    session = requests.Session()
    
    # Retry stratejisi (sadece bağlantı hatalarında)
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,  # 1s, 2s, 4s
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=2,
        pool_maxsize=4,
        pool_block=False
    )
    
    session.mount("https://", adapter)
    return session

# Global session
_session = create_session()

# İnsan gibi görünmek için gerçekçi headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://finans.truncgil.com/",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache"
}

# ======================================
# YARDIMCI FONKSİYONLAR
# ======================================

def get_safe_float(value):
    """Güvenli float dönüşümü"""
    try:
        if isinstance(value, (int, float)):
            return float(value)
        
        v = str(value).strip().replace("%", "").replace("$", "").replace(" ", "")
        
        # Türkçe format: 1.234,56 -> 1234.56
        if '.' in v and ',' in v:
            v = v.replace(".", "").replace(",", ".")
        # Sadece virgül varsa: 1234,56 -> 1234.56
        elif ',' in v:
            v = v.replace(",", ".")
        
        return float(v)
    except:
        return 0.0

def process_currencies(data):
    """
    Döviz verilerini işle (15 popüler döviz)
    """
    codes = [
        "USD", "EUR", "GBP", "JPY", "CHF", 
        "CNY", "CAD", "AUD", "DKK", "SEK",
        "NOK", "SAR", "QAR", "KWD", "AED"
    ]
    
    result = []
    for code in codes:
        if code in data and data[code].get("Type") == "Currency":
            item = data[code]
            selling = get_safe_float(item.get("Selling"))
            
            if selling > 0:  # Geçerli fiyat kontrolü
                result.append({
                    "code": code,
                    "name": item.get("Name", code),
                    "rate": round(selling, 4) if selling < 10 else round(selling, 2),
                    "change_percent": round(get_safe_float(item.get("Change")), 2)
                })
    
    return result

def process_golds(data):
    """
    Altın verilerini işle (5 popüler altın)
    """
    mapping = {
        "GRA": "Gram Altın",
        "CEYREKALTIN": "Çeyrek Altın",
        "YARIMALTIN": "Yarım Altın",
        "TAMALTIN": "Tam Altın",
        "CUMHURIYETALTINI": "Cumhuriyet Altını"
    }
    
    result = []
    for code, name in mapping.items():
        if code in data:
            item = data[code]
            selling = get_safe_float(item.get("Selling"))
            
            if selling > 0:
                result.append({
                    "name": name,
                    "rate": round(selling, 2),
                    "change_percent": round(get_safe_float(item.get("Change")), 2)
                })
    
    return result

def process_silvers(data):
    """
    Gümüş verilerini işle
    """
    if "GUMUS" in data:
        item = data["GUMUS"]
        selling = get_safe_float(item.get("Selling"))
        
        if selling > 0:
            return [{
                "name": "Gümüş",
                "rate": round(selling, 4),
                "change_percent": round(get_safe_float(item.get("Change")), 2)
            }]
    
    return []

# ======================================
# API ÇAĞRISI (Retry Mekanizmalı)
# ======================================

def fetch_api_data(url, max_retries=3):
    """
    API'den veri çek, retry mekanizmalı
    
    Args:
        url: API endpoint
        max_retries: Maksimum deneme sayısı
    
    Returns:
        dict veya None
    """
    for attempt in range(1, max_retries + 1):
        try:
            # Her denemede kısa bekleme (rate limit için)
            if attempt > 1:
                wait_time = attempt - 1
                logger.warning(f"⚠️ fetch_api_data bağlantı hatası (deneme {attempt}/{max_retries}), {wait_time}s sonra tekrar denenecek...")
                time.sleep(wait_time)
            
            response = _session.get(url, headers=HEADERS, timeout=API_TIMEOUT)
            response.raise_for_status()
            
            # JSON parse (bozuk JSON kontrolü)
            try:
                data = response.json()
                return data
            except Exception as json_err:
                logger.error(f"❌ API bozuk JSON döndürdü: {str(json_err)[:100]}")
                if attempt == max_retries:
                    return None
                continue
        
        except requests.exceptions.Timeout:
            logger.error(f"❌ API timeout (deneme {attempt}/{max_retries})")
            if attempt == max_retries:
                return None
        
        except requests.exceptions.ConnectionError as ce:
            logger.error(f"❌ API bağlantı hatası (deneme {attempt}/{max_retries}): {str(ce)[:100]}")
            if attempt == max_retries:
                return None
        
        except Exception as e:
            logger.error(f"❌ API beklenmeyen hata (deneme {attempt}/{max_retries}): {str(e)[:100]}")
            if attempt == max_retries:
                return None
    
    logger.error(f"❌ fetch_api_data bağlantı hatası (tüm denemeler tükendi)")
    return None

# ======================================
# ANA SENKRONİZASYON FONKSİYONU
# ======================================

def sync_financial_data():
    """
    TEK API çağrısıyla tüm finansal verileri çeker ve Redis'e yazar.
    V4 başarısız olursa V3'e otomatik geçer (fallback).
    
    Returns:
        bool: Başarılı ise True
    """
    try:
        logger.info("🔄 Finansal veriler güncelleniyor (TEK İstek Modu)...")
        start_time = time.time()
        
        # 1️⃣ Önce V4 API'yi dene
        full_data = fetch_api_data(API_URL_V4)
        api_version = "V4"
        
        # 2️⃣ V4 başarısız olduysa V3'e geç
        if not full_data:
            logger.warning("⚠️ V4 API başarısız, V3'e fallback yapılıyor...")
            full_data = fetch_api_data(API_URL_V3)
            api_version = "V3"
        
        # 3️⃣ Her iki API de başarısız olduysa çık
        if not full_data:
            logger.error("❌ Hem V4 hem V3 API başarısız!")
            return False
        
        update_date = full_data.get("Update_Date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        logger.info(f"🎯 {api_version} API kullanılıyor - Tarih: {update_date}")
        
        # 4️⃣ Tüm verileri işle
        currencies = process_currencies(full_data)
        golds = process_golds(full_data)
        silvers = process_silvers(full_data)
        
        # 5️⃣ Redis'e kaydet
        success_count = 0
        
        if currencies:
            set_cache('kurabak:currencies:all', {
                "success": True,
                "count": len(currencies),
                "data": currencies,
                "update_date": update_date,
                "api_version": api_version
            }, CACHE_TTL)
            logger.info(f"✅ {len(currencies)} döviz Redis'e yazıldı")
            success_count += 1
        
        if golds:
            set_cache('kurabak:golds:all', {
                "success": True,
                "count": len(golds),
                "data": golds,
                "update_date": update_date,
                "api_version": api_version
            }, CACHE_TTL)
            logger.info(f"✅ {len(golds)} altın Redis'e yazıldı")
            success_count += 1
        
        if silvers:
            set_cache('kurabak:silvers:all', {
                "success": True,
                "count": len(silvers),
                "data": silvers,
                "update_date": update_date,
                "api_version": api_version
            }, CACHE_TTL)
            logger.info(f"✅ {len(silvers)} gümüş Redis'e yazıldı")
            success_count += 1
        
        elapsed = time.time() - start_time
        
        if success_count == 3:
            logger.info(f"✅ Tüm veriler başarıyla güncellendi ({api_version} API) - {elapsed:.2f}s")
            return True
        elif success_count > 0:
            logger.warning(f"⚠️ Kısmi güncelleme ({success_count}/3 başarılı) - {elapsed:.2f}s")
            return True
        else:
            logger.error(f"❌ Hiçbir veri güncellenemedi - {elapsed:.2f}s")
            return False
    
    except Exception as e:
        logger.error(f"❌ sync_financial_data kritik hata: {str(e)}")
        return False

# ======================================
# SESSION TEMİZLEME (Graceful Shutdown)
# ======================================

def cleanup_session():
    """
    Session'ı düzgünce kapat (app kapanırken çağrılmalı)
    """
    global _session
    if _session:
        _session.close()
        logger.info("🧹 API session kapatıldı")
