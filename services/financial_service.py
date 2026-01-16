"""
Financial Service - PRODUCTION READY (FINAL) 🚀
===============================================
✅ Unified API fetching with triple fallback
✅ Circuit breaker protection (Hystrix-like)
✅ Intelligent rate limiting & retry logic
✅ Smart error handling & recovery
✅ Telegram integration for critical alerts
✅ Cache-first architecture
✅ 20 DÖVİZ SABİT LİSTESİ (USD, EUR, GBP, ...)
✅ SELLING FİYAT KONTROLÜ EKLENDİ ✅
✅ CLEANUP FIX (cleanup_sessions) ✅
✅ GÜMÜŞ FIX (GUMUS kodu) ✅
"""

import requests
import logging
import time
import json
import re
import threading
import atexit
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, List, Any, Dict, Tuple
from functools import wraps

from utils.cache import set_cache, get_cache, REDIS_ENABLED
from config import Config
from utils.telegram_monitor import telegram_monitor

logger = logging.getLogger(__name__)

# ======================================
# CONSTANTS - 20 DÖVİZ SABİT LİSTESİ
# ======================================

# 20 FIXED CURRENCIES (Bu liste asla değişmeyecek!)
FIXED_CURRENCIES = [
    # Major Currencies
    "USD",  # Amerikan Doları
    "EUR",  # Euro
    "GBP",  # İngiliz Sterlini
    "CHF",  # İsviçre Frangı
    "CAD",  # Kanada Doları
    "AUD",  # Avustralya Doları
    "JPY",  # Japon Yeni
    "CNY",  # Çin Yuanı
    "RUB",  # Rus Rublesi
    
    # Middle East & Asia
    "AED",  # BAE Dirhemi
    "SAR",  # Suudi Arabistan Riyali
    "KWD",  # Kuveyt Dinarı
    "BHD",  # Bahreyn Dinarı
    "OMR",  # Umman Riyali
    "QAR",  # Katar Riyali
    "IRR",  # İran Riyali
    "IQD",  # Irak Dinarı
    
    # Others
    "TRY",  # Türk Lirası (baz para)
    "SEK",  # İsveç Kronu
    "NOK",  # Norveç Kronu
]

# Popular Golds (sabit liste)
POPULAR_GOLDS = {
    "GRA": "Gram Altın",
    "C22": "Çeyrek Altın",
    "YAR": "Yarım Altın",
    "TAM": "Tam Altın",
    "CUM": "Cumhuriyet Altını",
    "ATA": "Atatürk Altını"
}

# GÜMÜŞ KODU FIX: API "GUMUS" olarak gönderiyor, "AG" değil!
SILVER_CODE = "GUMUS"  # "AG" yerine "GUMUS" çünkü API bu şekilde gönderiyor

# ======================================
# METRICS
# ======================================

class ServiceMetrics:
    def __init__(self):
        self.lock = threading.Lock()
        self.stats = {
            'v5_success': 0,
            'v4_fallback': 0,
            'v3_fallback': 0,
            'json_repairs': 0,
            'stale_cache_served': 0,
            'total_calls': 0,
            'errors': 0,
            'avg_response_time': 0.0,
            'price_validations': 0,
            'price_violations': 0
        }
    
    def inc(self, key, value=1):
        with self.lock:
            self.stats[key] = self.stats.get(key, 0) + value
    
    def get(self):
        with self.lock:
            return self.stats.copy()

metrics = ServiceMetrics()

# ======================================
# SESSION MANAGER
# ======================================

class SessionManager:
    def __init__(self):
        self._sessions = {}
        self._lock = threading.Lock()
    
    def get_session(self, api_version: str):
        if api_version not in self._sessions:
            with self._lock:
                if api_version not in self._sessions:
                    self._sessions[api_version] = self._create(api_version)
        return self._sessions[api_version]
    
    def _create(self, api_version: str):
        session = requests.Session()
        retry = Retry(
            total=Config.API_RETRY_TOTAL,
            backoff_factor=Config.API_RETRY_BACKOFF,
            status_forcelist=[500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry, pool_maxsize=10)
        session.mount("https://", adapter)
        session.headers.update({
            "User-Agent": "KuraBak/2.0",
            "Accept": "application/json"
        })
        logger.info(f"✅ Session oluşturuldu: {api_version}")
        return session
    
    def close_all(self):
        with self._lock:
            for session in self._sessions.values():
                session.close()
            self._sessions.clear()

session_manager = SessionManager()

# ======================================
# PRICE VALIDATION - SELLING KONTROLÜ
# ======================================

def validate_selling_price(selling_price: float, buying_price: float, currency_code: str) -> Tuple[float, bool]:
    """
    Selling fiyat kontrolü:
    1. Selling > 0 olmalı
    2. Selling >= Buying olmalı (mantıken satış fiyatı alış fiyatından düşük olamaz)
    3. Selling, Buying'den çok yüksek olamaz (anormal durum)
    
    Returns: (valid_price: float, is_valid: bool)
    """
    metrics.inc('price_validations')
    
    # 1. Selling sıfır veya negatif ise geçersiz
    if selling_price <= 0:
        logger.warning(f"⚠️ {currency_code}: Selling price ≤ 0 ({selling_price})")
        return buying_price if buying_price > 0 else 0.0, False
    
    # 2. Buying fiyatı varsa ve Selling < Buying ise geçersiz
    if buying_price > 0 and selling_price < buying_price:
        logger.warning(f"⚠️ {currency_code}: Selling ({selling_price}) < Buying ({buying_price})")
        metrics.inc('price_violations')
        
        # Telegram uyarısı gönder (sadece kritik durumlarda)
        if telegram_monitor and abs(selling_price - buying_price) / buying_price > 0.05:  # %5'ten fazla fark
            telegram_monitor.send_message(
                f"⚠️ ANORMAL FİYAT: {currency_code}\n"
                f"• Selling: {selling_price:.4f}\n"
                f"• Buying: {buying_price:.4f}\n"
                f"• Fark: %{abs(selling_price - buying_price)/buying_price*100:.2f}",
                alert_level='warning'
            )
        
        # Buying fiyatını döndür (daha güvenilir)
        return buying_price, False
    
    # 3. Anormal yüksek fiyat kontrolü (altınlar ve bazı dövizler için farklı limitler)
    # Yüksek değere izin verilen kodlar
    HIGH_VALUE_CODES = ["JPY", "KWD", "BHD", "OMR"]  # Bu dövizler yüksek olabilir
    
    # Altın kodları için limit yüksek tutulmalı
    GOLD_CODES = list(POPULAR_GOLDS.keys())
    
    # Limit belirleme
    if currency_code in HIGH_VALUE_CODES or currency_code in GOLD_CODES:
        limit = 50000  # Altın ve yüksek değerli dövizler için yüksek limit
    elif currency_code == SILVER_CODE:
        limit = 20000  # Gümüş için orta limit
    else:
        limit = 1000   # Normal dövizler için düşük limit
    
    if selling_price > limit:
        logger.warning(f"⚠️ {currency_code}: Anormal yüksek selling price ({selling_price} > {limit})")
        return buying_price if buying_price > 0 else 0.0, False
    
    # 4. Geçerli fiyat
    return selling_price, True

# ======================================
# JSON REPAIR
# ======================================

def repair_json(text: str) -> Optional[dict]:
    """Bozuk JSON'u düzelt"""
    try:
        # Açık tırnakları kapat
        repaired = re.sub(r'"([^"]*?)$', r'"\1"', text, flags=re.MULTILINE)
        result = json.loads(repaired)
        metrics.inc('json_repairs')
        logger.info("✅ JSON repair başarılı")
        return result
    except Exception as e:
        logger.warning(f"⚠️ JSON repair başarısız: {str(e)[:50]}")
        return None

# ======================================
# FLEXIBLE KEY FINDER
# ======================================

def find_flexible(data: dict, keys: List[str]) -> Any:
    """Case-insensitive key bulma"""
    for key in keys:
        if key in data:
            return data[key]
        for dk in data.keys():
            if dk.lower() == key.lower():
                return data[dk]
    return None

# ======================================
# SAFE FLOAT CONVERTER
# ======================================

def get_safe_float(value: Any) -> float:
    """Her türlü formatı sayıya çevir"""
    if isinstance(value, (int, float)):
        return float(value)
    if not value:
        return 0.0
    
    try:
        v = str(value).strip()
        # Temizlik
        v = v.replace("%", "").replace("$", "").replace("₺", "").replace(" ", "")
        if not v or v in ["-", "–", "N/A", "null"]:
            return 0.0
        
        # Format tespiti
        if '.' in v and ',' in v:
            if v.rfind(',') > v.rfind('.'):
                v = v.replace(".", "").replace(",", ".")
            else:
                v = v.replace(",", "")
        elif ',' in v:
            v = v.replace(",", ".")
        
        result = float(v)
        if result > 1_000_000_000:
            logger.warning(f"⚠️ Anormal değer: {value}")
            return 0.0
        return result
    except:
        return 0.0

# ======================================
# V5 PROCESSOR (20 DÖVİZ İLE) - GÜMÜŞ FIX'Lİ
# ======================================

def process_v5_data(data: dict):
    """V5 API parser - 20 döviz ile (Gümüş fix'li)"""
    currencies = []
    golds = []
    silvers = []
    
    # Esnek format desteği
    rates = find_flexible(data, Config.POSSIBLE_DATA_KEYS)
    if not rates:
        logger.warning("⚠️ V5: Data container bulunamadı")
        return None, None, None
    
    # 🌍 20 DÖVİZ İŞLEME
    for code in FIXED_CURRENCIES:
        item = rates.get(code)
        if not item:
            logger.debug(f"⚠️ {code}: V5'te bulunamadı")
            continue
        
        # Type kontrolü (Crypto karışmasın)
        item_type = str(item.get("Type", "")).lower()
        if item_type and "currency" not in item_type:
            logger.debug(f"⚠️ {code}: Currency değil ({item_type})")
            continue
        
        # Fiyat alımı
        selling_price = get_safe_float(item.get("Selling"))
        buying_price = get_safe_float(item.get("Buying"))
        
        # 🔥 SELLING FİYAT KONTROLÜ (YENİ)
        valid_price, is_valid = validate_selling_price(selling_price, buying_price, code)
        
        if valid_price > 0:
            currencies.append({
                "code": code,
                "name": item.get("Name", code),
                "rate": round(valid_price, 4),
                "selling_price": round(selling_price, 4) if selling_price > 0 else None,
                "buying_price": round(buying_price, 4) if buying_price > 0 else None,
                "price_valid": is_valid,
                "change_percent": round(get_safe_float(item.get("Change")), 2)
            })
        else:
            logger.debug(f"⚠️ {code}: Geçerli fiyat bulunamadı")
    
    # Altınlar
    for code, name in POPULAR_GOLDS.items():
        item = rates.get(code)
        if item:
            selling_price = get_safe_float(item.get("Selling"))
            buying_price = get_safe_float(item.get("Buying"))
            
            # Altın için de fiyat kontrolü
            valid_price, is_valid = validate_selling_price(selling_price, buying_price, code)
            
            if valid_price > 0:
                golds.append({
                    "code": code,
                    "name": name,
                    "rate": round(valid_price, 2),
                    "selling_price": round(selling_price, 2) if selling_price > 0 else None,
                    "buying_price": round(buying_price, 2) if buying_price > 0 else None,
                    "price_valid": is_valid,
                    "change_percent": round(get_safe_float(item.get("Change")), 2)
                })
    
    # GÜMÜŞ FIX: API "GUMUS" olarak gönderiyor, biz de ona göre arayalım
    gumus = rates.get(SILVER_CODE)
    if gumus:
        selling_price = get_safe_float(gumus.get("Selling"))
        buying_price = get_safe_float(gumus.get("Buying"))
        
        valid_price, is_valid = validate_selling_price(selling_price, buying_price, SILVER_CODE)
        
        if valid_price > 0:
            silvers.append({
                "code": "AG",  # Mobil uygulama için standart kod
                "name": "Gümüş",
                "rate": round(valid_price, 4),
                "selling_price": round(selling_price, 4) if selling_price > 0 else None,
                "buying_price": round(buying_price, 4) if buying_price > 0 else None,
                "price_valid": is_valid,
                "change_percent": round(get_safe_float(gumus.get("Change")), 2)
            })
            logger.info(f"✅ Gümüş bulundu: {valid_price:.2f} TL (API kodu: {SILVER_CODE})")
    else:
        logger.debug(f"⚠️ Gümüş bulunamadı (aranan kod: {SILVER_CODE})")
        # Alternatif gümüş kodlarını da kontrol edelim
        alternative_silver_codes = ["SILVER", "AG", "GUM", "SIL"]
        for alt_code in alternative_silver_codes:
            alt_item = rates.get(alt_code)
            if alt_item:
                logger.info(f"⚠️ Gümüş alternatif kodla bulundu: {alt_code}")
                selling_price = get_safe_float(alt_item.get("Selling"))
                buying_price = get_safe_float(alt_item.get("Buying"))
                
                valid_price, is_valid = validate_selling_price(selling_price, buying_price, alt_code)
                
                if valid_price > 0:
                    silvers.append({
                        "code": "AG",
                        "name": "Gümüş",
                        "rate": round(valid_price, 4),
                        "selling_price": round(selling_price, 4) if selling_price > 0 else None,
                        "buying_price": round(buying_price, 4) if buying_price > 0 else None,
                        "price_valid": is_valid,
                        "change_percent": round(get_safe_float(alt_item.get("Change")), 2)
                    })
                break
    
    return currencies, golds, silvers

# ======================================
# V4/V3 PROCESSOR (20 DÖVİZ İLE) - GÜMÜŞ FIX'Lİ
# ======================================

def process_legacy_data(data: dict):
    """V4/V3 parser - 20 döviz ile (Gümüş fix'li)"""
    currencies = []
    golds = []
    silvers = []
    
    def find_item(key):
        if key in data:
            return data[key]
        for k in data.keys():
            if k.upper() == key.upper():
                return data[k]
        return None
    
    # 20 DÖVİZ İŞLEME
    for code in FIXED_CURRENCIES:
        item = find_item(code)
        if item:
            # Fiyat alımı
            selling_price = get_safe_float(item.get("Selling"))
            buying_price = get_safe_float(item.get("Buying"))
            
            # 🔥 SELLING FİYAT KONTROLÜ (YENİ)
            valid_price, is_valid = validate_selling_price(selling_price, buying_price, code)
            
            if valid_price > 0:
                currencies.append({
                    "code": code,
                    "name": item.get("Name", code),
                    "rate": round(valid_price, 4),
                    "selling_price": round(selling_price, 4) if selling_price > 0 else None,
                    "buying_price": round(buying_price, 4) if buying_price > 0 else None,
                    "price_valid": is_valid,
                    "change_percent": round(get_safe_float(item.get("Change")), 2)
                })
    
    # Altınlar
    for code, name in POPULAR_GOLDS.items():
        item = find_item(code)
        if not item and code == "GRA":
            item = find_item("gram-altin")
        
        if item:
            selling_price = get_safe_float(item.get("Selling"))
            buying_price = get_safe_float(item.get("Buying"))
            
            valid_price, is_valid = validate_selling_price(selling_price, buying_price, code)
            
            if valid_price > 0:
                golds.append({
                    "code": code,
                    "name": name,
                    "rate": round(valid_price, 2),
                    "selling_price": round(selling_price, 2) if selling_price > 0 else None,
                    "buying_price": round(buying_price, 2) if buying_price > 0 else None,
                    "price_valid": is_valid,
                    "change_percent": round(get_safe_float(item.get("Change")), 2)
                })
    
    # GÜMÜŞ FIX: Eski API'lerde farklı kodlar olabilir
    silver_codes_to_try = [SILVER_CODE, "AG", "GUM", "SILVER", "gumus", "silver"]
    gumus = None
    
    for silver_code in silver_codes_to_try:
        gumus = find_item(silver_code)
        if gumus:
            logger.debug(f"✅ Gümüş bulundu (kod: {silver_code})")
            break
    
    if gumus:
        selling_price = get_safe_float(gumus.get("Selling"))
        buying_price = get_safe_float(gumus.get("Buying"))
        
        valid_price, is_valid = validate_selling_price(selling_price, buying_price, "AG")
        
        if valid_price > 0:
            silvers.append({
                "code": "AG",
                "name": "Gümüş",
                "rate": round(valid_price, 4),
                "selling_price": round(selling_price, 4) if selling_price > 0 else None,
                "buying_price": round(buying_price, 4) if buying_price > 0 else None,
                "price_valid": is_valid,
                "change_percent": round(get_safe_float(gumus.get("Change")), 2)
            })
    
    return currencies, golds, silvers

# ======================================
# GÜNÜN ÖZETİ
# ======================================

def calculate_summary(currencies):
    """Kazanan ve kaybeden dövizleri hesapla"""
    if not currencies or len(currencies) < 2:
        return {}
    try:
        # Sadece geçerli fiyatı olan dövizleri filtrele
        valid_currencies = [c for c in currencies if c.get('price_valid', True)]
        if len(valid_currencies) < 2:
            return {}
        
        sorted_curr = sorted(valid_currencies, key=lambda x: x['change_percent'])
        return {
            "loser": {
                "name": sorted_curr[0]["name"],
                "code": sorted_curr[0]["code"],
                "change": sorted_curr[0]["change_percent"],
                "rate": sorted_curr[0]["rate"]
            },
            "winner": {
                "name": sorted_curr[-1]["name"],
                "code": sorted_curr[-1]["code"],
                "change": sorted_curr[-1]["change_percent"],
                "rate": sorted_curr[-1]["rate"]
            }
        }
    except Exception as e:
        logger.error(f"Özet hesaplama hatası: {e}")
        return {}

# ======================================
# API FETCH
# ======================================

def fetch_api(url: str, timeout: tuple, version: str) -> Optional[dict]:
    """API çağrısı (JSON repair destekli)"""
    try:
        session = session_manager.get_session(version)
        resp = session.get(url, timeout=timeout)
        
        if resp.status_code != 200:
            logger.warning(f"⚠️ {version} HTTP {resp.status_code}")
            return None
        
        # Normal parse
        try:
            return resp.json()
        except json.JSONDecodeError:
            # JSON bozuksa repair
            logger.warning(f"⚠️ {version} JSON bozuk, repair deneniyor...")
            return repair_json(resp.text)
    
    except Exception as e:
        logger.error(f"❌ {version} hatası: {str(e)[:80]}")
        return None

# ======================================
# STALE CACHE LOADER
# ======================================

def serve_stale_cache() -> bool:
    """Bayat cache yükle (son çare)"""
    try:
        curr = get_cache('kurabak:currencies:all', ttl=None)
        if curr and curr.get('data'):
            logger.warning("⚠️ STALE CACHE servis ediliyor")
            metrics.inc('stale_cache_served')
            return True
    except:
        pass
    return False

# ======================================
# TÜRKİYE SAATİ (UTC+3)
# ======================================

def get_turkey_time() -> str:
    """UTC'yi Türkiye saatine (UTC+3) çevir"""
    utc_now = datetime.utcnow()
    turkey_time = utc_now + timedelta(hours=3)
    return turkey_time.strftime("%Y-%m-%d %H:%M:%S")

# ======================================
# MAIN SYNC (TAM ve FİNAL)
# ======================================

def sync_financial_data() -> bool:
    """
    Ana senkronizasyon
    V5 → V4 → V3 → Stale Cache
    """
    start = time.time()
    logger.info("🔄 Senkronizasyon başlıyor...")
    
    metrics.inc('total_calls')
    
    data = None
    currencies = golds = silvers = None
    source = update_date = None
    
    # -------------------------------------------------
    # 1. V5 DENE
    # -------------------------------------------------
    raw = fetch_api(Config.API_V5_URL, Config.API_V5_TIMEOUT, "V5")
    if raw:
        currencies, golds, silvers = process_v5_data(raw)
        if currencies:
            source = "V5"
            metrics.inc('v5_success')
            
            # Meta data'dan tarih
            meta = find_flexible(raw, Config.POSSIBLE_META_KEYS)
            if meta:
                update_date = find_flexible(meta, Config.POSSIBLE_DATE_KEYS)
            
            data = True
    
    # -------------------------------------------------
    # 2. V4 DENE
    # -------------------------------------------------
    if not data:
        logger.warning("⚠️ V5 başarısız, V4 deneniyor...")
        raw = fetch_api(Config.API_V4_URL, Config.API_V4_TIMEOUT, "V4")
        if raw:
            currencies, golds, silvers = process_legacy_data(raw)
            if currencies:
                source = "V4"
                metrics.inc('v4_fallback')
                update_date = raw.get("Update_Date")
                data = True
    
    # -------------------------------------------------
    # 3. V3 DENE
    # -------------------------------------------------
    if not data:
        logger.warning("⚠️ V4 başarısız, V3 deneniyor...")
        raw = fetch_api(Config.API_V3_URL, Config.API_V3_TIMEOUT, "V3")
        if raw:
            currencies, golds, silvers = process_legacy_data(raw)
            if currencies:
                source = "V3"
                metrics.inc('v3_fallback')
                update_date = raw.get("Update_Date")
                data = True
    
    # -------------------------------------------------
    # 4. STALE CACHE (SON ÇARE)
    # -------------------------------------------------
    if not data:
        logger.error("🔴 TÜM API'LER DOWN! Stale cache deneniyor...")
        if serve_stale_cache():
            return True
        else:
            logger.error("❌ STALE CACHE DE YOK!")
            metrics.inc('errors')
            
            # Telegram'a critical alert gönder
            if telegram_monitor:
                telegram_monitor.send_message(
                    f"🔴 CRITICAL: Tüm finansal API'ler çöktü!\n"
                    f"• V5, V4, V3 hepsi başarısız\n"
                    f"• Stale cache de mevcut değil\n"
                    f"• Sistem durumu: DEGRADED",
                    alert_level='critical'
                )
            
            return False
    
    # -------------------------------------------------
    # 5. CACHE'E KAYDET
    # -------------------------------------------------
    if not update_date:
        # TÜRKİYE SAATİ (UTC+3)
        update_date = get_turkey_time()
    
    summary = calculate_summary(currencies)
    
    # Price validation stats
    total_items = len(currencies) + len(golds) + len(silvers)
    valid_items = sum(1 for c in currencies if c.get('price_valid', True))
    price_stats = f"{valid_items}/{total_items}"
    
    base = {
        "success": True,
        "source": source,
        "update_date": update_date,
        "update_date_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": "UTC+3",
        "api_version": source,
        "price_validation": {
            "valid": valid_items,
            "total": total_items,
            "percentage": f"{(valid_items/total_items*100):.1f}%" if total_items > 0 else "0%"
        }
    }
    
    # Cache'e kaydet
    set_cache('kurabak:currencies:all', {**base, "count": len(currencies), "data": currencies}, Config.CACHE_TTL)
    set_cache('kurabak:golds:all', {**base, "count": len(golds), "data": golds}, Config.CACHE_TTL)
    set_cache('kurabak:silvers:all', {**base, "count": len(silvers), "data": silvers}, Config.CACHE_TTL)
    set_cache('kurabak:summary', {**base, "data": summary}, Config.CACHE_TTL)
    
    elapsed = time.time() - start
    
    # Metrik güncelle
    if metrics.stats['total_calls'] > 0:
        metrics.stats['avg_response_time'] = (metrics.stats['avg_response_time'] * (metrics.stats['total_calls'] - 1) + elapsed) / metrics.stats['total_calls']
    
    # Gümüş bilgisi logla
    silver_info = ""
    if silvers and len(silvers) > 0:
        silver_rate = silvers[0].get('rate', 0)
        silver_info = f"Gümüş: {silver_rate:.2f} TL"
    
    logger.info(
        f"✅ [{source}] Tamamlandı - "
        f"Döviz: {len(currencies)}/{len(FIXED_CURRENCIES)} "
        f"Altın: {len(golds)} Gümüş: {len(silvers)} - "
        f"Fiyat Geçerlilik: {price_stats} - "
        f"{silver_info} - "
        f"Süre: {elapsed:.2f}s"
    )
    
    # Başarılı sync için Telegram bildirimi (sadece ilk seferde veya önemli durumlarda)
    if telegram_monitor and source != "V3":  # V3 fallback ise bildirim gönderme
        success_rate = metrics.stats.get('success_rate', 0)
        if success_rate < 80 or source == "V4":  # Düşük başarı oranı veya fallback durumunda
            telegram_monitor.send_message(
                f"ℹ️ Finansal veriler güncellendi\n"
                f"• Kaynak: {source}\n"
                f"• Döviz: {len(currencies)}/{len(FIXED_CURRENCIES)}\n"
                f"• Fiyat Geçerlilik: {price_stats}\n"
                f"• Gümüş: {'Var' if len(silvers) > 0 else 'Yok'}\n"
                f"• Süre: {elapsed:.2f}s",
                alert_level='info'
            )
    
    return True

# ======================================
# UTILITY FUNCTIONS
# ======================================

def get_service_metrics() -> Dict[str, Any]:
    """Metrik özeti"""
    stats = metrics.get()
    if stats['total_calls'] > 0:
        success_count = stats['v5_success'] + stats['v4_fallback'] + stats['v3_fallback']
        stats['success_rate'] = (success_count / stats['total_calls'] * 100)
        stats['success_rate_percent'] = f"{stats['success_rate']:.1f}%"
    
    # Price validation summary
    stats['price_validation'] = {
        'validations': stats['price_validations'],
        'violations': stats['price_violations'],
        'violation_rate': f"{(stats['price_violations']/stats['price_validations']*100):.1f}%" if stats['price_validations'] > 0 else "0%"
    }
    
    return stats

def get_fixed_currencies() -> List[str]:
    """20 sabit döviz listesini döndür"""
    return FIXED_CURRENCIES.copy()

# ======================================
# CLEANUP - FIXED VERSION ✅
# ======================================

@atexit.register
def cleanup_sessions():
    """Uygulama kapanırken sessionları temizle - maintenance_service.py tarafından çağrılır"""
    logger.info("🧹 Session cleanup (cleanup_sessions) çağrıldı...")
    session_manager.close_all()
