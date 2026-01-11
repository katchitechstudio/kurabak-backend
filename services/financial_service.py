"""
Financial Service - Multi-Version API Support (Final)
=====================================================
✅ V4/V3 API desteği (fallback)
✅ Cache TTL 1 Saat (Asla 503 vermez)
✅ Günün Özeti (Winner/Loser) Hesaplama
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
# Config'den CACHE_TTL'i siliyoruz, manuel 1 saat vereceğiz.
from config import Config

logger = logging.getLogger(__name__)

# ======================================
# CONFIG
# ======================================

API_TIMEOUT = (10, 20)
API_URL_V4 = "https://finans.truncgil.com/v4/today.json"
API_URL_V3 = "https://finans.truncgil.com/v3/today.json"

# 🔥 CACHE SÜRESİ: 1 SAAT (3600 Saniye)
# Veri her 2 dakikada bir yenilense de, cache silinmeyecek.
SAFE_CACHE_TTL = 3600 

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

# ALTIN KEY MAPPİNGLERİ
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

# GÜMÜŞ KEY MAPPİNGLERİ
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
# DATA PROCESSING
# ======================================

def get_safe_float(value) -> float:
    try:
        if isinstance(value, (int, float)):
            return float(value)
        if value is None:
            return 0.0
        
        v = str(value).strip().replace("%", "").replace("$", "").replace(" ", "")
        if '.' in v and ',' in v:
            v = v.replace(".", "").replace(",", ".")
        elif ',' in v:
            v = v.replace(",", ".")
        
        result = float(v)
        if result < 0 or result > 1_000_000:
            return 0.0
        
        return result
    except:
        return 0.0

def find_item(data: dict, keys: List[str]) -> Optional[dict]:
    for key in keys:
        if key in data:
            return data[key]
    return None

def process_currencies(data: dict) -> List[dict]:
    result = []
    for code in POPULAR_CURRENCIES:
        item = find_item(data, [code, code.lower()])
        if not item:
            continue
        
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
    item = find_item(data, SILVER_KEYS)
    if not item:
        return []

    selling = get_safe_float(item.get("Selling"))
    if selling <= 0:
        return []
    
    return [{
        "name": "Gümüş",
        "rate": round(selling, 4),
        "change_percent": round(get_safe_float(item.get("Change")), 2)
    }]

# 🔥 YENİ: GÜNÜN ÖZETİNİ HESAPLA (WINNER/LOSER)
def calculate_daily_summary(currencies: List[dict]) -> dict:
    """En çok artan ve düşen dövizi bulur"""
    if not currencies or len(currencies) < 2:
        return {}

    try:
        # Değişim oranına göre sırala (Küçükten büyüğe)
        sorted_currencies = sorted(currencies, key=lambda x: x['change_percent'])

        # En çok düşen (Listenin başı)
        loser = sorted_currencies[0]
        
        # En çok yükselen (Listenin sonu)
        winner = sorted_currencies[-1]

        return {
            "winner": {
                "name": winner["name"],
                "code": winner["code"],
                "change": winner["change_percent"],
                "rate": winner["rate"]
            },
            "loser": {
                "name": loser["name"],
                "code": loser["code"],
                "change": loser["change_percent"],
                "rate": loser["rate"]
            }
        }
    except Exception as e:
        logger.error(f"❌ Günün özeti hesaplanırken hata: {e}")
        return {}

# ======================================
# API FETCH
# ======================================

def fetch_api_data(url: str) -> Optional[dict]:
    try:
        session = session_manager.get_session()
        resp = session.get(url, headers=HEADERS, timeout=API_TIMEOUT)
        
        if resp.status_code != 200:
            logger.error(f"❌ HTTP {resp.status_code}: {url}")
            return None
        
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
        
        # 3. Verileri işle
        currencies = process_currencies(data)
        golds = process_golds(data)
        silvers = process_silvers(data)
        
        # 4. GÜNÜN ÖZETİNİ HESAPLA 🔥
        daily_summary = calculate_daily_summary(currencies)

        # 5. Veri kontrolü
        if not currencies:
            logger.error("❌ Hiç döviz verisi yok!")
            metrics.record_failure()
            return False
        
        # 6. Redis'e kaydet (TTL ARTTIRILDI -> 3600 Saniye)
        base_data = {
            "success": True,
            "update_date": update_date,
            "api_version": version
        }
        
        # Tüm verileri 1 saatlik cache süresiyle kaydet
        set_cache('kurabak:currencies:all', {**base_data, "count": len(currencies), "data": currencies}, SAFE_CACHE_TTL)
        set_cache('kurabak:golds:all', {**base_data, "count": len(golds), "data": golds}, SAFE_CACHE_TTL)
        set_cache('kurabak:silvers:all', {**base_data, "count": len(silvers), "data": silvers}, SAFE_CACHE_TTL)
        
        # Özet verisini de kaydet
        if daily_summary:
            set_cache('kurabak:summary', {**base_data, "data": daily_summary}, SAFE_CACHE_TTL)
            logger.info("✅ Günün özeti hesaplandı ve kaydedildi.")

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
