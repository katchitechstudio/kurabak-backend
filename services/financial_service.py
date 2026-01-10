"""
Financial Service - Multi-Version API Support
==============================================

✅ V4/V3 API desteği (fallback)
✅ Akıllı key mapping (hem V4 hem V3 formatları)
✅ JSON parse hata yönetimi
✅ Gümüş cache fix
✅ Thread-safe session yönetimi
"""

import requests
import logging
import time
import atexit
import threading
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, List

from utils.cache import set_cache
from config import Config

logger = logging.getLogger(__name__)

# ======================================
# CONFIG
# ======================================

API_TIMEOUT = (10, 20)
API_URL_V4 = "https://finans.truncgil.com/v4/today.json"
API_URL_V3 = "https://finans.truncgil.com/v3/today.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Connection": "keep-alive"
}

# Döviz kodları
POPULAR_CURRENCIES = [
    "USD", "EUR", "GBP", "JPY", "CHF", "CNY", 
    "CAD", "AUD", "DKK", "SEK", "NOK", "SAR", 
    "QAR", "KWD", "AED"
]

# ALTIN KEY MAPPİNGLERİ (V4 + V3 uyumlu)
GOLD_MAPPINGS = {
    "GRA": ["GRA", "gram-altin", "gram_altin", "GRAM"],
    "CEYREKALTIN": ["CEYREKALTIN", "ceyrek-altin", "ceyrek_altin", "CEYREK"],
    "YARIMALTIN": ["YARIMALTIN", "yarim-altin", "yarim_altin", "YARIM"],
    "TAMALTIN": ["TAMALTIN", "tam-altin", "tam_altin", "TAM"],
    "CUMHURIYETALTINI": ["CUMHURIYETALTINI", "cumhuriyet-altini", "cumhuriyet_altini", "CUMHURIYET"]
}

GOLD_NAMES = {
    "GRA": "Gram Altın",
    "CEYREKALTIN": "Çeyrek Altın",
    "YARIMALTIN": "Yarım Altın",
    "TAMALTIN": "Tam Altın",
    "CUMHURIYETALTINI": "Cumhuriyet Altını"
}

# GÜMÜŞ KEY MAPPİNGLERİ (V4 + V3 uyumlu)
SILVER_KEYS = ["GUMUS", "gumus", "silver", "SILVER", "gümüş"]

# ======================================
# METRICS
# ======================================

class ServiceMetrics:
    def __init__(self):
        self.lock = threading.Lock()
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.v4_calls = 0
        self.v3_fallbacks = 0
        self.total_response_time = 0.0
        self.last_success_time = None
        
    def record_success(self, api_version: str, response_time: float):
        with self.lock:
            self.total_calls += 1
            self.successful_calls += 1
            self.total_response_time += response_time
            self.last_success_time = datetime.now()
            if api_version == "V4":
                self.v4_calls += 1
            else:
                self.v3_fallbacks += 1
    
    def record_failure(self):
        with self.lock:
            self.total_calls += 1
            self.failed_calls += 1

    def get_stats(self) -> dict:
        with self.lock:
            avg = (self.total_response_time / self.successful_calls) if self.successful_calls > 0 else 0
            rate = (self.successful_calls / self.total_calls * 100) if self.total_calls > 0 else 0
            return {
                'success_rate': f"{rate:.1f}%",
                'v4_calls': self.v4_calls,
                'v3_fallbacks': self.v3_fallbacks,
                'avg_time': f"{avg:.2f}s"
            }

metrics = ServiceMetrics()

# ======================================
# SESSION MANAGER
# ======================================

class SessionManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._session = None
    
    def get_session(self):
        if self._session is None:
            with self._lock:
                if self._session is None:
                    self._session = self._create()
        return self._session
    
    def _create(self):
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry, pool_maxsize=5)
        session.mount("https://", adapter)
        logger.info("✅ HTTP Session created")
        return session

    def close(self):
        if self._session:
            with self._lock:
                if self._session:
                    self._session.close()
                    self._session = None

session_manager = SessionManager()

# ======================================
# DATA PROCESSING (ROBUST)
# ======================================

def get_safe_float(value) -> float:
    """Güvenli float dönüşümü"""
    try:
        if isinstance(value, (int, float)):
            return float(value)
        if value is None:
            return 0.0
        
        v = str(value).strip().replace("%", "").replace("$", "").replace(" ", "")
        
        # Türkçe format: 1.234,56 -> 1234.56
        if '.' in v and ',' in v:
            v = v.replace(".", "").replace(",", ".")
        elif ',' in v:
            v = v.replace(",", ".")
        
        result = float(v)
        
        # Sınır kontrolü
        if result < 0 or result > 1_000_000:
            logger.warning(f"⚠️ Anormal değer: {result}")
            return 0.0
        
        return result
    except:
        return 0.0


def find_item(data: dict, keys: List[str]) -> Optional[dict]:
    """Verilen key alias'larından biriyle veriyi bul"""
    for key in keys:
        if key in data:
            return data[key]
    return None


def process_currencies(data: dict) -> List[dict]:
    """Döviz işleme"""
    result = []
    
    for code in POPULAR_CURRENCIES:
        # Hem büyük hem küçük harf dene
        item = find_item(data, [code, code.lower()])
        if not item:
            continue
        
        # V3'te Type olmayabilir, o yüzden esnek kontrol
        if "Type" in item and item["Type"] != "Currency":
            continue

        selling = get_safe_float(item.get("Selling"))
        if selling <= 0:
            continue
        
        result.append({
            "code": code,
            "name": item.get("Name", code),
            "rate": round(selling, 4) if selling < 10 else round(selling, 2),
            "change_percent": round(get_safe_float(item.get("Change")), 2)
        })
    
    return result


def process_golds(data: dict) -> List[dict]:
    """Altın işleme (V3/V4 alias desteği)"""
    result = []
    
    for main_code, aliases in GOLD_MAPPINGS.items():
        item = find_item(data, aliases)
        if not item:
            continue

        selling = get_safe_float(item.get("Selling"))
        if selling <= 0:
            continue
        
        result.append({
            "name": GOLD_NAMES[main_code],
            "rate": round(selling, 2),
            "change_percent": round(get_safe_float(item.get("Change")), 2)
        })
    
    return result


def process_silvers(data: dict) -> List[dict]:
    """Gümüş işleme (V3/V4 alias desteği) - FIXED"""
    item = find_item(data, SILVER_KEYS)
    
    if not item:
        logger.warning("⚠️ Gümüş verisi bulunamadı (tüm alias'lar denendi)")
        return []

    selling = get_safe_float(item.get("Selling"))
    if selling <= 0:
        return []
    
    return [{
        "name": "Gümüş",
        "rate": round(selling, 4),
        "change_percent": round(get_safe_float(item.get("Change")), 2)
    }]

# ======================================
# API FETCH
# ======================================

def fetch_api_data(url: str) -> Optional[dict]:
    """API'den veri çek - ROBUST JSON handling"""
    try:
        session = session_manager.get_session()
        resp = session.get(url, headers=HEADERS, timeout=API_TIMEOUT)
        
        if resp.status_code != 200:
            logger.error(f"❌ HTTP {resp.status_code}: {url}")
            return None
        
        # JSON parse (bozuk JSON hatası için hazır)
        try:
            return resp.json()
        except requests.exceptions.JSONDecodeError as je:
            logger.error(f"❌ Bozuk JSON ({url}): {str(je)[:100]}")
            return None
            
    except requests.exceptions.Timeout:
        logger.error(f"❌ Timeout: {url}")
        return None
    except Exception as e:
        logger.error(f"❌ API Hatası: {str(e)[:100]}")
        return None

# ======================================
# MAIN SYNC FUNCTION
# ======================================

def sync_financial_data() -> bool:
    """
    Ana senkronizasyon fonksiyonu
    V4 -> V3 fallback desteği
    """
    start_time = time.time()
    
    try:
        logger.info("🔄 Finansal veriler güncelleniyor...")
        
        # 1. V4 dene
        data = fetch_api_data(API_URL_V4)
        version = "V4"
        
        # 2. V3 fallback
        if not data:
            logger.warning("⚠️ V4 başarısız, V3 deneniyor...")
            data = fetch_api_data(API_URL_V3)
            version = "V3"
        
        if not data:
            logger.error("❌ Hem V4 hem V3 başarısız!")
            metrics.record_failure()
            return False
        
        elapsed = time.time() - start_time
        metrics.record_success(version, elapsed)
        
        update_date = data.get("Update_Date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        logger.info(f"✅ {version} API başarılı - {update_date}")
        
        # 3. Verileri işle
        currencies = process_currencies(data)
        golds = process_golds(data)
        silvers = process_silvers(data)
        
        # 4. Veri kontrolü (esnek)
        if not currencies:
            logger.error("❌ Hiç döviz verisi yok!")
            metrics.record_failure()
            return False
        
        # Gümüş olmasa bile devam et (bazen V3'te olmayabiliyor)
        if not golds:
            logger.warning("⚠️ Altın verisi yok")
        if not silvers:
            logger.warning("⚠️ Gümüş verisi yok")
        
        # 5. Redis'e kaydet
        base_data = {
            "success": True,
            "update_date": update_date,
            "api_version": version
        }
        
        set_cache('kurabak:currencies:all', {**base_data, "count": len(currencies), "data": currencies}, Config.CACHE_TTL)
        set_cache('kurabak:golds:all', {**base_data, "count": len(golds), "data": golds}, Config.CACHE_TTL)
        set_cache('kurabak:silvers:all', {**base_data, "count": len(silvers), "data": silvers}, Config.CACHE_TTL)
        
        total_time = time.time() - start_time
        logger.info(
            f"✅ Güncelleme tamamlandı ({version}) - "
            f"D:{len(currencies)} A:{len(golds)} G:{len(silvers)} - {total_time:.2f}s"
        )
        
        return True
    
    except Exception as e:
        logger.error(f"❌ Kritik hata: {type(e).__name__}: {str(e)}", exc_info=True)
        metrics.record_failure()
        return False


def get_service_metrics() -> dict:
    return metrics.get_stats()


@atexit.register
def cleanup():
    logger.info("🧹 Financial service cleanup...")
    session_manager.close()
