"""
Financial Service - Tek İstek, Tüm Veriler
==========================================

Özellikler:
✅ Sadece 1 HTTP isteği (bot korumasına karşı)
✅ V4 başarısız olursa V3'e otomatik geçiş
✅ Thread-safe session yönetimi
✅ Akıllı retry mekanizması
✅ Metrik ve monitoring
✅ Graceful shutdown
✅ Detaylı loglama
"""

import requests
import logging
import time
import atexit
import threading
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, Dict, List

from utils.cache import set_cache
from config import Config

logger = logging.getLogger(__name__)

# ======================================
# AYARLAR
# ======================================

API_TIMEOUT = (12, 25)  # (connect, read) - Daha uzun timeout

# Dual API support
API_URL_V4 = "https://finans.truncgil.com/v4/today.json"
API_URL_V3 = "https://finans.truncgil.com/v3/today.json"

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

# Popüler veri listeleri
POPULAR_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CHF", "CNY", "CAD", "AUD", "DKK", "SEK", "NOK", "SAR", "QAR", "KWD", "AED"]
POPULAR_GOLDS = {
    "GRA": "Gram Altın",
    "CEYREKALTIN": "Çeyrek Altın",
    "YARIMALTIN": "Yarım Altın",
    "TAMALTIN": "Tam Altın",
    "CUMHURIYETALTINI": "Cumhuriyet Altını"
}

# ======================================
# METRİKLER
# ======================================

class ServiceMetrics:
    """API çağrıları için metrik takibi"""
    
    def __init__(self):
        self.lock = threading.Lock()
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.v4_calls = 0
        self.v3_fallbacks = 0
        self.total_response_time = 0.0
        self.last_success_time = None
        self.last_failure_time = None
    
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
            self.last_failure_time = datetime.now()
    
    def get_stats(self) -> dict:
        with self.lock:
            avg_time = (
                self.total_response_time / self.successful_calls 
                if self.successful_calls > 0 else 0
            )
            success_rate = (
                (self.successful_calls / self.total_calls * 100) 
                if self.total_calls > 0 else 0
            )
            
            return {
                'total_calls': self.total_calls,
                'successful_calls': self.successful_calls,
                'failed_calls': self.failed_calls,
                'success_rate': f"{success_rate:.2f}%",
                'v4_calls': self.v4_calls,
                'v3_fallbacks': self.v3_fallbacks,
                'avg_response_time': f"{avg_time:.2f}s",
                'last_success': self.last_success_time.isoformat() if self.last_success_time else None,
                'last_failure': self.last_failure_time.isoformat() if self.last_failure_time else None
            }

metrics = ServiceMetrics()

# ======================================
# THREAD-SAFE SESSION YÖNETİMİ
# ======================================

class SessionManager:
    """Thread-safe HTTP session yönetimi"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._session = None
    
    def get_session(self) -> requests.Session:
        """Session'ı al (lazy initialization)"""
        if self._session is None:
            with self._lock:
                if self._session is None:
                    self._session = self._create_session()
        return self._session
    
    def _create_session(self) -> requests.Session:
        """Optimize edilmiş session oluştur"""
        session = requests.Session()
        
        # Retry stratejisi
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,  # 1s, 2s, 4s
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False
        )
        
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=2,
            pool_maxsize=5,
            pool_block=False
        )
        
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        logger.info("✅ HTTP Session oluşturuldu (connection pooling aktif)")
        return session
    
    def close(self):
        """Session'ı kapat"""
        if self._session:
            with self._lock:
                if self._session:
                    self._session.close()
                    self._session = None
                    logger.info("🧹 HTTP Session kapatıldı")

# Global session manager
session_manager = SessionManager()

# ======================================
# YARDIMCI FONKSİYONLAR
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
        # Sadece virgül varsa: 1234,56 -> 1234.56
        elif ',' in v:
            v = v.replace(",", ".")
        
        result = float(v)
        
        # Negatif veya aşırı büyük değerleri filtrele
        if result < 0 or result > 1_000_000:
            logger.warning(f"⚠️ Anormal değer tespit edildi: {result}")
            return 0.0
        
        return result
        
    except (ValueError, TypeError) as e:
        logger.debug(f"Float dönüşüm hatası: {value} -> {e}")
        return 0.0


def process_currencies(data: dict) -> List[dict]:
    """Döviz verilerini işle (15 popüler döviz)"""
    result = []
    
    for code in POPULAR_CURRENCIES:
        if code not in data:
            continue
        
        item = data[code]
        
        # Tip kontrolü
        if item.get("Type") != "Currency":
            continue
        
        selling = get_safe_float(item.get("Selling"))
        
        # Geçersiz fiyat kontrolü
        if selling <= 0:
            logger.warning(f"⚠️ Geçersiz döviz fiyatı: {code} = {selling}")
            continue
        
        result.append({
            "code": code,
            "name": item.get("Name", code),
            "rate": round(selling, 4) if selling < 10 else round(selling, 2),
            "change_percent": round(get_safe_float(item.get("Change")), 2)
        })
    
    return result


def process_golds(data: dict) -> List[dict]:
    """Altın verilerini işle (5 popüler altın)"""
    result = []
    
    for code, name in POPULAR_GOLDS.items():
        if code not in data:
            continue
        
        item = data[code]
        selling = get_safe_float(item.get("Selling"))
        
        if selling <= 0:
            logger.warning(f"⚠️ Geçersiz altın fiyatı: {name} = {selling}")
            continue
        
        result.append({
            "name": name,
            "rate": round(selling, 2),
            "change_percent": round(get_safe_float(item.get("Change")), 2)
        })
    
    return result


def process_silvers(data: dict) -> List[dict]:
    """Gümüş verilerini işle"""
    if "GUMUS" not in data:
        return []
    
    item = data["GUMUS"]
    selling = get_safe_float(item.get("Selling"))
    
    if selling <= 0:
        logger.warning(f"⚠️ Geçersiz gümüş fiyatı: {selling}")
        return []
    
    return [{
        "name": "Gümüş",
        "rate": round(selling, 4),
        "change_percent": round(get_safe_float(item.get("Change")), 2)
    }]

# ======================================
# API ÇAĞRISI
# ======================================

def fetch_api_data(url: str) -> Optional[dict]:
    """
    API'den veri çek (urllib3.Retry otomatik retry yapıyor)
    
    Args:
        url: API endpoint
    
    Returns:
        dict veya None
    """
    try:
        session = session_manager.get_session()
        
        logger.debug(f"🌐 API çağrısı yapılıyor: {url}")
        response = session.get(url, headers=HEADERS, timeout=API_TIMEOUT)
        
        # HTTP hata kontrolü
        if response.status_code != 200:
            logger.error(f"❌ API HTTP hatası: {response.status_code}")
            return None
        
        # JSON parse
        try:
            data = response.json()
            logger.debug(f"✅ JSON parse başarılı ({len(data)} anahtar)")
            return data
            
        except requests.exceptions.JSONDecodeError as je:
            logger.error(f"❌ Bozuk JSON: {str(je)[:200]}")
            return None
    
    except requests.exceptions.Timeout:
        logger.error(f"❌ API timeout ({API_TIMEOUT[0]}s connect, {API_TIMEOUT[1]}s read)")
        return None
    
    except requests.exceptions.ConnectionError as ce:
        # Retry zaten yapıldı, bu final hata
        logger.error(f"❌ Bağlantı hatası (tüm retry'lar başarısız): {str(ce)[:150]}")
        return None
    
    except Exception as e:
        logger.error(f"❌ Beklenmeyen API hatası: {type(e).__name__}: {str(e)[:150]}")
        return None

# ======================================
# ANA SENKRONİZASYON FONKSİYONU
# ======================================

def sync_financial_data() -> bool:
    """
    TEK API çağrısıyla tüm finansal verileri çeker ve Redis'e yazar.
    V4 başarısız olursa V3'e otomatik geçer (fallback).
    
    Returns:
        bool: Başarılı ise True
    """
    start_time = time.time()
    
    try:
        logger.info("🔄 Finansal veriler güncelleniyor...")
        
        # 1️⃣ V4 API'yi dene
        full_data = fetch_api_data(API_URL_V4)
        api_version = "V4"
        
        # 2️⃣ V4 başarısız olduysa V3'e geç
        if not full_data:
            logger.warning("⚠️ V4 başarısız, V3'e fallback yapılıyor...")
            full_data = fetch_api_data(API_URL_V3)
            api_version = "V3"
        
        # 3️⃣ Her iki API de başarısız
        if not full_data:
            logger.error("❌ Hem V4 hem V3 başarısız!")
            metrics.record_failure()
            return False
        
        # API çağrısı başarılı
        elapsed = time.time() - start_time
        metrics.record_success(api_version, elapsed)
        
        update_date = full_data.get("Update_Date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        logger.info(f"✅ {api_version} API başarılı - Tarih: {update_date}")
        
        # 4️⃣ Verileri işle
        currencies = process_currencies(full_data)
        golds = process_golds(full_data)
        silvers = process_silvers(full_data)
        
        # Veri doğrulama
        if not currencies or not golds or not silvers:
            logger.error(
                f"❌ Eksik veri! Döviz: {len(currencies)}, "
                f"Altın: {len(golds)}, Gümüş: {len(silvers)}"
            )
            metrics.record_failure()
            return False
        
        # 5️⃣ Redis'e toplu kaydet
        cache_data = {
            "success": True,
            "update_date": update_date,
            "api_version": api_version
        }
        
        # Dövizler
        set_cache(
            'kurabak:currencies:all',
            {**cache_data, "count": len(currencies), "data": currencies},
            Config.CACHE_TTL
        )
        
        # Altınlar
        set_cache(
            'kurabak:golds:all',
            {**cache_data, "count": len(golds), "data": golds},
            Config.CACHE_TTL
        )
        
        # Gümüş
        set_cache(
            'kurabak:silvers:all',
            {**cache_data, "count": len(silvers), "data": silvers},
            Config.CACHE_TTL
        )
        
        total_time = time.time() - start_time
        logger.info(
            f"✅ Tüm veriler başarıyla güncellendi ({api_version}) - "
            f"Döviz: {len(currencies)}, Altın: {len(golds)}, Gümüş: {len(silvers)} - "
            f"Süre: {total_time:.2f}s"
        )
        
        return True
    
    except Exception as e:
        logger.error(f"❌ sync_financial_data kritik hata: {type(e).__name__}: {str(e)}", exc_info=True)
        metrics.record_failure()
        return False


def get_service_metrics() -> dict:
    """
    Servis metriklerini döndür
    """
    return metrics.get_stats()

# ======================================
# GRACEFUL SHUTDOWN
# ======================================

def cleanup():
    """
    Uygulama kapanırken session'ları temizle
    """
    logger.info("🛑 Financial service kapatılıyor...")
    session_manager.close()
    
    # Metrikleri logla
    stats = metrics.get_stats()
    logger.info(f"📊 Final metrikler: {stats}")

# Uygulama kapanırken otomatik temizlik
atexit.register(cleanup)
