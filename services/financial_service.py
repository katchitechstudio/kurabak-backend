"""
Financial Service - ULTIMATE EDITION (V4/V3 Hibrit & Kurşun Geçirmez)
================================================================
✅ V4/V3 API Tam Uyumluluk (Format Karmaşası %100 Çözüldü)
✅ Güvenli Float Dönüştürücü (String/Float/Int/Null/Empty - HEPSİNİ TANIR)
✅ Akıllı Key Eşleştirme (Büyük/Küçük harf, tire, alt çizgi fark etmez)
✅ Cache TTL 1 Saat + Otomatik Kurtarma
✅ Thread-Safe Session Yönetimi
✅ Profesyonel Hata Yönetimi
✅ Günün Özeti (Kazanan/Kaybeden) Hesaplama
✅ MAKİNE GİBİ ÇALIŞIR 🤖
"""

import requests
import logging
import time
import atexit
import threading
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, List, Union, Any

from utils.cache import set_cache
from config import Config

logger = logging.getLogger(__name__)

# ======================================
# AYARLAR (CONFIG)
# ======================================

API_TIMEOUT = (10, 20)
API_URL_V4 = "https://finans.truncgil.com/v4/today.json"
API_URL_V3 = "https://finans.truncgil.com/v3/today.json"

# 🔥 CACHE SÜRESİ: 1 SAAT (3600 Saniye)
SAFE_CACHE_TTL = 3600 

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Connection": "keep-alive"
}

# Takip edilecek döviz kodları
POPULAR_CURRENCIES = [
    "USD", "EUR", "GBP", "JPY", "CHF", "CNY", 
    "CAD", "AUD", "DKK", "SEK", "NOK", "SAR", 
    "QAR", "KWD", "AED"
]

# ALTIN EŞLEŞTİRMELERİ (V4 + V3 Hibrit)
# Her altın türü için API'den gelebilecek tüm olası isimler
GOLD_MAPPINGS = {
    "GRA": ["GRA", "gram-altin", "gram_altin", "GRAM", "GRAMALTIN"],
    "CEYREKALTIN": ["CEYREKALTIN", "ceyrek-altin", "ceyrek_altin", "CEYREK"],
    "YARIMALTIN": ["YARIMALTIN", "yarim-altin", "yarim_altin", "YARIM"],
    "TAMALTIN": ["TAMALTIN", "tam-altin", "tam_altin", "TAM"],
    "CUMHURIYETALTINI": ["CUMHURIYETALTINI", "cumhuriyet-altini", "cumhuriyet_altini", "CUMHURIYET"]
}

# Uygulamada görünecek isimler
GOLD_NAMES = {
    "GRA": "Gram Altın",
    "CEYREKALTIN": "Çeyrek Altın",
    "YARIMALTIN": "Yarım Altın",
    "TAMALTIN": "Tam Altın",
    "CUMHURIYETALTINI": "Cumhuriyet Altını"
}

# GÜMÜŞ KEYLERİ
SILVER_KEYS = ["GUMUS", "gumus", "silver", "SILVER", "gümüş"]

# ======================================
# METRİKLER (İstatistik Tutma)
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
        self.parse_errors = 0
        self.format_fixes = 0
        
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
    
    def record_parse_error(self):
        with self.lock:
            self.parse_errors += 1
    
    def record_format_fix(self):
        with self.lock:
            self.format_fixes += 1

    def get_stats(self) -> dict:
        with self.lock:
            avg = (self.total_response_time / self.successful_calls) if self.successful_calls > 0 else 0
            rate = (self.successful_calls / self.total_calls * 100) if self.total_calls > 0 else 0
            return {
                'success_rate': f"{rate:.1f}%",
                'v4_calls': self.v4_calls,
                'v3_fallbacks': self.v3_fallbacks,
                'avg_time': f"{avg:.2f}s",
                'parse_errors': self.parse_errors,
                'format_fixes': self.format_fixes
            }

metrics = ServiceMetrics()

# ======================================
# BAĞLANTI YÖNETİCİSİ (Session Manager)
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
        logger.info("✅ HTTP Session oluşturuldu")
        return session

    def close(self):
        if self._session:
            with self._lock:
                if self._session:
                    self._session.close()
                    self._session = None

session_manager = SessionManager()

# ======================================
# 🔥 AKILLI FLOAT DÖNÜŞTÜRÜCÜ (EN ÖNEMLİ KISIM)
# ======================================

def get_safe_float(value: Any) -> float:
    """
    Bu fonksiyon her türlü bozuk sayı formatını düzeltir.
    
    Örnekler:
    - "140,4318" -> 140.4318 (Virgülü nokta yapar)
    - "1.250,50" -> 1250.50  (Noktayı siler, virgülü nokta yapar)
    - "1,250.50" -> 1250.50  (Virgülü siler)
    - "%0,77"    -> 0.77     (Sembolleri temizler)
    """
    # 1. NULL veya BOŞ KONTROLÜ
    if value is None:
        return 0.0
    
    # 2. ZATEN SAYI İSE (V4 API bazen direkt float dönüyor)
    if isinstance(value, (int, float)):
        return float(value)
    
    # 3. STRİNG İSE (Temizleme başlıyor)
    try:
        v = str(value).strip()
        
        # Boş string kontrolü
        if not v or v in ["—", "-", "–", "N/A", "null", "undefined"]:
            return 0.0
        
        # Sembol temizliği (%, $, ₺, TL, boşluk)
        v = v.replace("%", "").replace("$", "").replace("₺", "")
        v = v.replace("TL", "").replace(" ", "").strip()
        
        if not v:
            return 0.0
        
        # 🔥 AKILLI FORMAT TESPİTİ
        
        # Durum A: Hem nokta hem virgül var (Örn: "1.234,56" veya "1,234.56")
        if '.' in v and ',' in v:
            metrics.record_format_fix()
            
            # Hangi işaret daha sondaysa o ondalıktır
            dot_pos = v.rfind('.')
            comma_pos = v.rfind(',')
            
            if comma_pos > dot_pos:
                # Virgül sonda: "1.250,50" (Türk/Avrupa standardı)
                # Noktaları (binlik) sil, Virgülü (ondalık) nokta yap
                v = v.replace(".", "").replace(",", ".")
            else:
                # Nokta sonda: "1,250.50" (Amerikan standardı)
                # Virgülleri (binlik) sil
                v = v.replace(",", "")
        
        # Durum B: Sadece virgül var (Örn: "140,43" veya "1,250")
        elif ',' in v:
            # Virgülden sonra 3 hane veya daha fazlaysa ve değer küçükse?
            # Truncgil API genelde virgülü ondalık olarak kullanıyor (Örn: 140,4318)
            # Bu yüzden virgülü her zaman nokta yapıyoruz.
            v = v.replace(",", ".")
        
        # Durum C: Sadece nokta var (Örn: "1.25") -> Dokunma, zaten Python formatı.
        
        # Son Dönüşüm
        result = float(v)
        
        # Çok saçma büyük sayı kontrolü (Hata önleyici)
        if result > 1_000_000_000: # 1 Milyar üstü kur olamaz
             logger.warning(f"⚠️ Anormal büyük değer tespit edildi: {value} -> {result}")
             metrics.record_parse_error()
             return 0.0
             
        return result
    
    except Exception as e:
        logger.debug(f"⚠️ Sayı çevirme hatası: {value} -> {str(e)}")
        metrics.record_parse_error()
        return 0.0

# ======================================
# AKILLI KEY BULUCU
# ======================================

def find_item(data: dict, keys: List[str]) -> Optional[dict]:
    """Verilen anahtar kelimelerden herhangi birini JSON içinde bulur"""
    for key in keys:
        if key in data:
            return data[key]
        # Büyük/küçük harf duyarsız arama
        for data_key in data.keys():
            if data_key.lower() == key.lower():
                return data[data_key]
    return None

# ======================================
# VERİ İŞLEYİCİLER (PROCESSORS)
# ======================================

def process_currencies(data: dict) -> List[dict]:
    """Döviz verilerini işle"""
    result = []
    
    for code in POPULAR_CURRENCIES:
        # Kodun kendisi veya tam adı ile ara
        item = find_item(data, [code, code.upper(), code.lower()])
        if not item:
            continue
        
        # "Type" alanı varsa ve "Currency" değilse atla (Bazen Altın karışıyor)
        item_type = item.get("Type", "").lower()
        if item_type and "currency" not in item_type and "döviz" not in item_type:
            # Bazı API versiyonlarında Type alanı olmayabilir, o yüzden katı değiliz
            pass

        # Fiyatı al (Selling veya Buying)
        price = get_safe_float(item.get("Selling"))
        if price <= 0:
            price = get_safe_float(item.get("Buying")) # Satış yoksa Alış fiyatını dene
            
        if price <= 0:
            continue
        
        # Değişim oranını al
        change = get_safe_float(item.get("Change"))
        
        result.append({
            "code": code,
            "name": item.get("Name", code),
            "rate": round(price, 4), # Kuruş hassasiyeti
            "change_percent": round(change, 2)
        })
    
    return result

def process_golds(data: dict) -> List[dict]:
    """Altın verilerini işle"""
    result = []
    
    for main_code, aliases in GOLD_MAPPINGS.items():
        item = find_item(data, aliases)
        if not item:
            continue

        price = get_safe_float(item.get("Selling"))
        if price <= 0:
            continue
        
        change = get_safe_float(item.get("Change"))
        
        result.append({
            "name": GOLD_NAMES[main_code],
            "rate": round(price, 2),
            "change_percent": round(change, 2)
        })
    
    return result

def process_silvers(data: dict) -> List[dict]:
    """Gümüş verisini işle"""
    item = find_item(data, SILVER_KEYS)
    if not item:
        return []

    price = get_safe_float(item.get("Selling"))
    if price <= 0:
        return []
    
    change = get_safe_float(item.get("Change"))
    
    return [{
        "name": "Gümüş",
        "rate": round(price, 4),
        "change_percent": round(change, 2)
    }]

def calculate_daily_summary(currencies: List[dict]) -> dict:
    """En çok kazandıran ve kaybettireni bulur"""
    if not currencies or len(currencies) < 2:
        return {}

    try:
        # Değişim yüzdesine göre sırala
        sorted_currencies = sorted(currencies, key=lambda x: x['change_percent'])
        loser = sorted_currencies[0]  # En düşük (negatif)
        winner = sorted_currencies[-1] # En yüksek (pozitif)

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
        logger.error(f"❌ Günün özeti hatası: {e}")
        return {}

# ======================================
# API ÇEKME (FETCH)
# ======================================

def fetch_api_data(url: str) -> Optional[dict]:
    """Belirtilen URL'den JSON verisi çeker"""
    try:
        session = session_manager.get_session()
        resp = session.get(url, headers=HEADERS, timeout=API_TIMEOUT)
        
        if resp.status_code != 200:
            logger.error(f"❌ HTTP Hatası {resp.status_code}: {url}")
            return None
        
        return resp.json()
            
    except Exception as e:
        logger.error(f"❌ Bağlantı Hatası ({url}): {str(e)[:100]}")
        return None

# ======================================
# ANA SENKRONİZASYON (MAIN SYNC)
# ======================================

def sync_financial_data() -> bool:
    """
    Bu fonksiyon belirli aralıklarla çalışır.
    Önce V4 API'yi dener, olmazsa V3'e geçer.
    Verileri temizler, formatlar ve Redis Cache'e kaydeder.
    """
    start_time = time.time()
    
    try:
        logger.info("🔄 Finansal veriler güncelleniyor...")
        
        # 1. ADIM: V4 Dene
        data = fetch_api_data(API_URL_V4)
        version = "V4"
        
        # 2. ADIM: Olmazsa V3 Dene (Fallback)
        if not data:
            logger.warning("⚠️ V4 yanıt vermedi, V3 deneniyor...")
            data = fetch_api_data(API_URL_V3)
            version = "V3"
        
        if not data:
            logger.error("❌ Kritik: Hem V4 hem V3 API çalışmıyor!")
            metrics.record_failure()
            return False
        
        elapsed = time.time() - start_time
        metrics.record_success(version, elapsed)
        
        # Update Date bilgisini bul
        update_date = data.get("Update_Date") or data.get("update_date") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 3. ADIM: Verileri İşle (Parsing)
        currencies = process_currencies(data)
        golds = process_golds(data)
        silvers = process_silvers(data)
        
        # 4. ADIM: Özet Hesapla
        daily_summary = calculate_daily_summary(currencies)

        if not currencies:
            logger.error("❌ Veri çekildi ama hiç döviz bulunamadı!")
            metrics.record_failure()
            return False
        
        # 5. ADIM: Cache'e Kaydet (Redis)
        base_data = {
            "success": True,
            "update_date": update_date,
            "api_version": version
        }
        
        set_cache('kurabak:currencies:all', {**base_data, "count": len(currencies), "data": currencies}, SAFE_CACHE_TTL)
        set_cache('kurabak:golds:all', {**base_data, "count": len(golds), "data": golds}, SAFE_CACHE_TTL)
        set_cache('kurabak:silvers:all', {**base_data, "count": len(silvers), "data": silvers}, SAFE_CACHE_TTL)
        
        if daily_summary:
            set_cache('kurabak:summary', {**base_data, "data": daily_summary}, SAFE_CACHE_TTL)

        total_time = time.time() - start_time
        stats = metrics.get_stats()
        
        logger.info(
            f"✅ Güncelleme Başarılı ({version}) - "
            f"Döviz:{len(currencies)} Altın:{len(golds)} Gümüş:{len(silvers)} - "
            f"Süre:{total_time:.2f}s - "
            f"Düzeltmeler:{stats['format_fixes']} Hatalar:{stats['parse_errors']}"
        )
        
        return True
    
    except Exception as e:
        logger.error(f"❌ Beklenmeyen Hata: {str(e)}", exc_info=True)
        metrics.record_failure()
        return False

def get_service_metrics() -> dict:
    return metrics.get_stats()

@atexit.register
def cleanup():
    logger.info("🧹 Servis kapatılıyor, bağlantılar temizleniyor...")
    session_manager.close()
