"""
Financial Service - PRODUCTION READY (ULTIMATE EDITION) 🚀
==========================================================
✅ TRIPLE FALLBACK: V5 -> V4 -> V3 -> Backup
✅ UNIVERSAL PARSER: Her türlü sayı formatını (43,20 | 6.374,59) anlar
✅ AUTO-MAPPING: 'gram-altin' -> 'GRA', 'GUMUS' -> 'AG' çevirisi
✅ 15-MIN BACKUP: Her 15 dakikada bir "Kara Kutu" yedeği alır
✅ SELF-HEALING: Tüm kaynaklar çökerse yedekten ayağa kalkar
✅ ZERO-ERROR: Hatalı veriyi sessizce eler, sistemi durdurmaz
✅ TELEGRAM ALERTS: Kritik durumlarda bildirim gönderir
"""

import requests
import logging
import time
import json
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from utils.cache import set_cache, get_cache
from config import Config

logger = logging.getLogger(__name__)

# ======================================
# SABİT LİSTELER VE MAPPING
# ======================================

# 20 Sabit Döviz Listesi
FIXED_CURRENCIES = [
    "USD", "EUR", "GBP", "CHF", "CAD", 
    "RUB", "AED", "AUD", "DKK", "SEK", 
    "NOK", "JPY", "KWD", "ZAR", "BHD", 
    "LYD", "SAR", "IQD", "ILS", "IRR"
]

# Altın Kod Haritası (API'deki karmaşık key'leri standartlaştırır)
GOLD_MAPPING = {
    # V5 Standart Kodlar
    "GRA": "GRA", "HAS": "HAS", "GUMUS": "AG",
    "CEYREKALTIN": "C22", "YARIMALTIN": "YAR", "TAMALTIN": "TAM",
    "CUMHURIYETALTINI": "CUM", "ATAALTIN": "ATA",
    "14AYARALTIN": "14K", "18AYARALTIN": "18K", "22AYARBILEZIK": "22K",
    "GREMSEALTIN": "GRE", "RESATALTIN": "RES", "HAMITALTIN": "HAM",
    "GPL": "PLT", "PAL": "PAL", "ONS": "ONS",
    
    # V3/V4 Kebap Case Kodlar
    "gram-altin": "GRA", "gram-has-altin": "HAS", "gumus": "AG",
    "ceyrek-altin": "C22", "yarim-altin": "YAR", "tam-altin": "TAM",
    "cumhuriyet-altini": "CUM", "ata-altin": "ATA",
    "14-ayar-altin": "14K", "18-ayar-altin": "18K", "22-ayar-bilezik": "22K",
    "gremse-altin": "GRE", "resat-altin": "RES", "hamit-altin": "HAM",
    "gram-platin": "PLT", "gram-paladyum": "PAL", "ons": "ONS"
}

# Metrikler
class Metrics:
    stats = {'v5': 0, 'v4': 0, 'v3': 0, 'backup': 0, 'errors': 0}
    
    @classmethod
    def inc(cls, key):
        cls.stats[key] = cls.stats.get(key, 0) + 1

    @classmethod
    def get(cls):
        return cls.stats.copy()

# ======================================
# EVRENSEL PARSER
# ======================================

def clean_money_string(value: Any) -> float:
    """
    ULTIMATE NUMBER PARSER 🧮
    Örnekler:
    - 43.2723 (Float) -> 43.2723
    - "43,2723" (V4) -> 43.2723
    - "6.374,59" (V3) -> 6374.59
    - "%0,22" (Change) -> 0.22
    - "$4.581,61" -> 4581.61
    """
    if isinstance(value, (int, float)):
        return float(value)
    
    if not value:
        return 0.0
        
    v = str(value).strip()
    
    # Gereksiz karakterleri temizle
    v = v.replace("%", "").replace("$", "").replace("TL", "").replace("₺", "").strip()
    
    if not v or v.lower() in ["-", "nan", "null", "none"]:
        return 0.0

    try:
        # Senaryo 1: Binlik nokta, ondalık virgül (6.374,59)
        if "." in v and "," in v:
            v = v.replace(".", "").replace(",", ".")
            
        # Senaryo 2: Sadece virgül (43,27)
        elif "," in v:
            v = v.replace(",", ".")
            
        # Senaryo 3: Sadece nokta (43.27) -> Dokunma
        
        return float(v)
    except Exception:
        return 0.0

def create_item(code: str, raw_item: dict, item_type: str) -> dict:
    """Standart veri objesi oluşturur"""
    buying = clean_money_string(raw_item.get("Buying"))
    selling = clean_money_string(raw_item.get("Selling"))
    change = clean_money_string(raw_item.get("Change"))
    
    # Selling yoksa Buying kullan
    if selling == 0: selling = buying
    if buying == 0: buying = selling
    
    return {
        "code": code,
        "name": raw_item.get("Name", code),
        "buying": round(buying, 4),
        "selling": round(selling, 4),
        "rate": round(selling, 4),
        "change_percent": round(change, 2),
        "type": item_type
    }

# ======================================
# DATA PROCESSOR
# ======================================

def process_data_generic(data: dict):
    """V5/V4/V3 verilerini işleyen akıllı fonksiyon"""
    currencies = []
    golds = []
    silvers = []
    
    # Veri kaynağını bul (V5'te "Rates" var, diğerlerinde yok)
    source_data = data.get("Rates", data)
    
    # 1. Dövizleri İşle
    for code in FIXED_CURRENCIES:
        item = source_data.get(code)
        if item:
            # Crypto karışmasın
            i_type = str(item.get("Type", "")).lower()
            if "crypto" in i_type:
                continue
            
            currencies.append(create_item(code, item, "currency"))
    
    # 2. Altınları İşle
    processed_codes = set()
    
    for api_key, standard_code in GOLD_MAPPING.items():
        if standard_code in processed_codes:
            continue
            
        # API key ile veriyi bul (Case-insensitive)
        item = None
        if api_key in source_data:
            item = source_data[api_key]
        else:
            for k in source_data.keys():
                if k.lower() == api_key.lower():
                    item = source_data[k]
                    break
        
        if item:
            is_silver = (standard_code == "AG")
            obj = create_item(standard_code, item, "silver" if is_silver else "gold")
            
            if is_silver:
                silvers.append(obj)
            else:
                golds.append(obj)
                
            processed_codes.add(standard_code)
    
    return currencies, golds, silvers

# ======================================
# API FETCH
# ======================================

def fetch_from_api(version: str, url: str, timeout: tuple) -> Optional[dict]:
    """Tekil API isteği"""
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "KuraBak/Backend"})
        if resp.status_code == 200:
            try:
                return resp.json()
            except json.JSONDecodeError:
                # JSON bozuksa basit temizlik
                text = resp.text.strip()
                if not text.endswith('}'):
                    text += '}'
                try:
                    return json.loads(text)
                except:
                    pass
        return None
    except Exception as e:
        logger.warning(f"⚠️ {version} Fetch Error: {str(e)[:50]}")
        return None

def calculate_summary(currencies):
    """Kazanan ve Kaybeden Özeti"""
    if len(currencies) < 2:
        return {}
    
    sorted_curr = sorted(currencies, key=lambda x: x['change_percent'])
    return {
        "loser": sorted_curr[0],
        "winner": sorted_curr[-1]
    }

# ======================================
# MAIN SYNC FUNCTION
# ======================================

def sync_financial_data() -> bool:
    """
    ANA SENKRONİZASYON
    V5 -> V4 -> V3 -> Backup zinciri
    """
    start_time = time.time()
    data_raw = None
    source = None
    
    # Telegram import (Circular import önlemek için burada)
    telegram_monitor = None
    try:
        from utils.telegram_monitor import telegram_monitor as tm
        telegram_monitor = tm
    except:
        pass
    
    # 1. V5 Dene
    if not data_raw:
        data_raw = fetch_from_api("V5", Config.API_V5_URL, Config.API_V5_TIMEOUT)
        if data_raw:
            source = "V5"

    # 2. V4 Dene
    if not data_raw:
        data_raw = fetch_from_api("V4", Config.API_V4_URL, Config.API_V4_TIMEOUT)
        if data_raw:
            source = "V4"

    # 3. V3 Dene
    if not data_raw:
        data_raw = fetch_from_api("V3", Config.API_V3_URL, Config.API_V3_TIMEOUT)
        if data_raw:
            source = "V3"

    # 4. BACKUP (Kara Kutu)
    if not data_raw:
        logger.error("🔴 TÜM API'LER ÇÖKTÜ! Backup verisi aranıyor...")
        backup_data = get_cache("kurabak:backup:all")
        
        if backup_data:
            logger.warning("✅ Backup verisi başarıyla yüklendi (Sistem ayakta).")
            
            # 🔥 TELEGRAM ALERT
            if telegram_monitor:
                telegram_monitor.send_message(
                    "⚠️ *TÜM API'LER ÇÖKTÜ!*\n\n"
                    "Sistem 15 dakikalık yedeği kullanıyor.\n"
                    "API'lerin durumu kontrol edilmeli.",
                    "critical"
                )
            
            # Backup'ı cache'e yükle
            set_cache(Config.CACHE_KEYS['currencies_all'], backup_data['currencies'], ttl=0)
            set_cache(Config.CACHE_KEYS['golds_all'], backup_data['golds'], ttl=0)
            set_cache(Config.CACHE_KEYS['silvers_all'], backup_data['silvers'], ttl=0)
            set_cache(Config.CACHE_KEYS['summary'], backup_data['summary'], ttl=0)
            
            Metrics.inc('backup')
            return True
        else:
            logger.critical("❌ BACKUP DA YOK! Sistem tamamen veri alamıyor.")
            
            # 🔥 TELEGRAM CRITICAL ALERT
            if telegram_monitor:
                telegram_monitor.send_message(
                    "🚨 *KRİTİK: SİSTEM VERİ ALMIYOR!*\n\n"
                    "• Tüm API'ler çöktü\n"
                    "• Backup verisi de mevcut değil\n"
                    "• Acil müdahale gerekli!",
                    "critical"
                )
            
            Metrics.inc('errors')
            return False

    # 5. Veriyi İşle
    try:
        currencies, golds, silvers = process_data_generic(data_raw)
        
        if not currencies:
            logger.error(f"❌ {source} verisi boş geldi.")
            Metrics.inc('errors')
            return False
        
        summary = calculate_summary(currencies)
        Metrics.inc(source.lower())
        
        # Tarih bilgisi
        update_date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        meta = data_raw.get("Meta_Data", {})
        if "Update_Date" in data_raw:
            update_date_str = data_raw["Update_Date"]
        elif "Update_Date" in meta:
            update_date_str = meta["Update_Date"]

        base_meta = {
            "source": source,
            "update_date": update_date_str,
            "timestamp": time.time()
        }

        # 6. Redis'e Kaydet (TTL=0 -> Süresiz)
        set_cache(Config.CACHE_KEYS['currencies_all'], {**base_meta, "data": currencies}, ttl=0)
        set_cache(Config.CACHE_KEYS['golds_all'], {**base_meta, "data": golds}, ttl=0)
        set_cache(Config.CACHE_KEYS['silvers_all'], {**base_meta, "data": silvers}, ttl=0)
        set_cache(Config.CACHE_KEYS['summary'], {**base_meta, "data": summary}, ttl=0)

        # 7. 15 Dakikalık Backup
        last_backup_time = get_cache("kurabak:backup:timestamp") or 0
        current_time = time.time()
        
        if current_time - float(last_backup_time) > 900:  # 900sn = 15dk
            logger.info("📦 15 Dakikalık Backup Alınıyor...")
            backup_payload = {
                "currencies": {**base_meta, "data": currencies},
                "golds": {**base_meta, "data": golds},
                "silvers": {**base_meta, "data": silvers},
                "summary": {**base_meta, "data": summary}
            }
            set_cache("kurabak:backup:all", backup_payload, ttl=0)
            set_cache("kurabak:backup:timestamp", current_time, ttl=0)

        elapsed = time.time() - start_time
        logger.info(
            f"✅ [{source}] Veri güncellendi. "
            f"(Döviz: {len(currencies)}, Altın: {len(golds)}, Gümüş: {len(silvers)}) "
            f"Süre: {elapsed:.2f}s"
        )
        return True

    except Exception as e:
        logger.error(f"❌ Veri işleme hatası: {e}", exc_info=True)
        Metrics.inc('errors')
        return False

def get_service_metrics():
    """Metrik özeti döndür"""
    return Metrics.get()
