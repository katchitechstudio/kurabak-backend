"""
Financial Service - PRODUCTION READY V4.0 🚀
=========================================================
✅ V5 + TRADINGVIEW: Dual source system (V3/V4 removed)
✅ MANUEL KAYNAK GEÇİŞİ: Telegram komutlarıyla kontrol
✅ MOBİL OPTİMİZE: 23 Döviz + 6 Altın + 1 Gümüş
✅ WORKER + SNAPSHOT + BANNER + DEATH STAR + BAKIM MODU
✅ SELF-HEALING: Otomatik kaynak değiştirme
"""

import requests
import logging
import time
import json
import pytz
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from utils.cache import set_cache, get_cache
from utils.event_manager import get_todays_banner
from config import Config

logger = logging.getLogger(__name__)

# ======================================
# 📱 MOBİL UYGULAMANIN KODLARI
# ======================================

MOBILE_CURRENCIES = [
    "USD", "EUR", "GBP", "CHF", "CAD", "AUD", "RUB",
    "SAR", "AED", "KWD", "BHD", "OMR", "QAR",
    "CNY", "SEK", "NOK",
    "PLN", "RON", "CZK", "EGP", "RSD", "HUF", "BAM"
]

MOBILE_GOLDS = {
    "GRA": "GRA", "CEYREKALTIN": "C22", "YARIMALTIN": "YAR",
    "TAMALTIN": "TAM", "CUMHURIYETALTINI": "CUM", "ATAALTIN": "ATA",
    "gram-altin": "GRA", "ceyrek-altin": "C22", "yarim-altin": "YAR",
    "tam-altin": "TAM", "cumhuriyet-altini": "CUM", "ata-altin": "ATA"
}

MOBILE_SILVER_CODES = ["GUMUS", "gumus", "AG", "SILVER"]

# ======================================
# METRİKLER
# ======================================

class Metrics:
    stats = {'v5': 0, 'tradingview': 0, 'backup': 0, 'errors': 0}
    
    @classmethod
    def inc(cls, key):
        cls.stats[key] = cls.stats.get(key, 0) + 1

    @classmethod
    def get(cls):
        return cls.stats.copy()

# ======================================
# YARDIMCI FONKSİYONLAR
# ======================================

def clean_money_string(value: Any) -> float:
    """Number parser"""
    if isinstance(value, (int, float)):
        return float(value)
    if not value:
        return 0.0
    v = str(value).strip().replace("%", "").replace("$", "").replace("TL", "").replace("₺", "").strip()
    if not v or v.lower() in ["-", "nan", "null", "none"]:
        return 0.0
    try:
        if "." in v and "," in v:
            v = v.replace(".", "").replace(",", ".")
        elif "," in v:
            v = v.replace(",", ".")
        return float(v)
    except:
        return 0.0

def create_item(code: str, raw_item: dict, item_type: str) -> dict:
    """Standart veri objesi"""
    buying = clean_money_string(raw_item.get("Buying"))
    selling = clean_money_string(raw_item.get("Selling"))
    change = clean_money_string(raw_item.get("Change"))
    if selling == 0: selling = buying
    if buying == 0: buying = selling
    return {
        "code": code, "name": raw_item.get("Name", code),
        "buying": round(buying, 4), "selling": round(selling, 4),
        "rate": round(selling, 4), "change_percent": round(change, 2),
        "type": item_type
    }

# ======================================
# TRADINGVIEW FETCH (YENİ!)
# ======================================

def fetch_from_tradingview() -> Optional[dict]:
    """
    TradingView'den veri çeker.
    tradingview-ta kütüphanesini kullanır.
    """
    try:
        from tradingview_ta import TA_Handler, Interval
        
        logger.info("📊 [TradingView] Veri çekiliyor...")
        
        rates = {}
        
        # Dövizler
        for code, symbol in Config.TRADINGVIEW_SYMBOLS.items():
            if code in ["GOLD", "SILVER"]:
                continue
            try:
                handler = TA_Handler(
                    symbol=symbol,
                    screener="forex",
                    exchange="FX_IDC",
                    interval=Interval.INTERVAL_1_MINUTE
                )
                analysis = handler.get_analysis()
                price = analysis.indicators.get("close", 0)
                
                if price > 0:
                    rates[code] = {
                        "Name": code,
                        "Buying": price,
                        "Selling": price,
                        "Change": 0,
                        "Type": "Currency"
                    }
            except Exception as e:
                logger.debug(f"TradingView {code} hatası: {e}")
        
        # Altın (USD cinsinden)
        try:
            handler = TA_Handler(
                symbol="GOLD",
                screener="forex",
                exchange="TVC",
                interval=Interval.INTERVAL_1_MINUTE
            )
            analysis = handler.get_analysis()
            gold_usd = analysis.indicators.get("close", 0)
            
            # USD/TRY kuru ile çarp
            usd_try = rates.get("USD", {}).get("Selling", 0)
            
            if gold_usd > 0 and usd_try > 0:
                # Ons altın -> Gram altın (1 ons = 31.1035 gram)
                gram_try = (gold_usd * usd_try) / 31.1035
                
                rates["GRA"] = {
                    "Name": "Gram Altın",
                    "Buying": gram_try,
                    "Selling": gram_try,
                    "Change": 0,
                    "Type": "Gold"
                }
                
                # Diğer altınlar (Yaklaşık hesaplamalar)
                rates["CEYREKALTIN"] = {
                    "Name": "Çeyrek Altın",
                    "Buying": gram_try * 1.75,
                    "Selling": gram_try * 1.75,
                    "Change": 0,
                    "Type": "Gold"
                }
                rates["YARIMALTIN"] = {
                    "Name": "Yarım Altın",
                    "Buying": gram_try * 3.5,
                    "Selling": gram_try * 3.5,
                    "Change": 0,
                    "Type": "Gold"
                }
                rates["TAMALTIN"] = {
                    "Name": "Tam Altın",
                    "Buying": gram_try * 7,
                    "Selling": gram_try * 7,
                    "Change": 0,
                    "Type": "Gold"
                }
                rates["CUMHURIYETALTINI"] = {
                    "Name": "Cumhuriyet Altını",
                    "Buying": gram_try * 7.2,
                    "Selling": gram_try * 7.2,
                    "Change": 0,
                    "Type": "Gold"
                }
                rates["ATAALTIN"] = {
                    "Name": "Ata Altın",
                    "Buying": gram_try * 7.2,
                    "Selling": gram_try * 7.2,
                    "Change": 0,
                    "Type": "Gold"
                }
        except Exception as e:
            logger.debug(f"TradingView GOLD hatası: {e}")
        
        # Gümüş
        try:
            handler = TA_Handler(
                symbol="SILVER",
                screener="forex",
                exchange="TVC",
                interval=Interval.INTERVAL_1_MINUTE
            )
            analysis = handler.get_analysis()
            silver_usd = analysis.indicators.get("close", 0)
            
            usd_try = rates.get("USD", {}).get("Selling", 0)
            
            if silver_usd > 0 and usd_try > 0:
                gram_try = (silver_usd * usd_try) / 31.1035
                rates["GUMUS"] = {
                    "Name": "Gümüş",
                    "Buying": gram_try,
                    "Selling": gram_try,
                    "Change": 0,
                    "Type": "Silver"
                }
        except Exception as e:
            logger.debug(f"TradingView SILVER hatası: {e}")
        
        if rates:
            logger.info(f"✅ [TradingView] {len(rates)} ürün çekildi")
            return {"Rates": rates}
        
        return None
        
    except ImportError:
        logger.error("❌ tradingview-ta kütüphanesi yok! pip install tradingview-ta")
        return None
    except Exception as e:
        logger.error(f"❌ TradingView genel hata: {e}")
        return None

# ======================================
# V5 FETCH
# ======================================

def fetch_from_v5() -> Optional[dict]:
    """V5 API'den veri çek"""
    try:
        resp = requests.get(
            Config.API_V5_URL,
            timeout=Config.API_V5_TIMEOUT,
            headers={"User-Agent": "KuraBak/Mobile"}
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.warning(f"⚠️ V5 Fetch Error: {str(e)[:50]}")
    return None

# ======================================
# PARSER
# ======================================

def process_data_mobile_optimized(data: dict):
    """23 Döviz + 6 Altın + 1 Gümüş parse"""
    currencies, golds, silvers = [], [], []
    source_data = data.get("Rates", data)
    
    # Dövizler
    for code in MOBILE_CURRENCIES:
        item = source_data.get(code)
        if item and "crypto" not in str(item.get("Type", "")).lower():
            currencies.append(create_item(code, item, "currency"))
    
    # Altınlar
    processed_golds = set()
    for api_key, standard_code in MOBILE_GOLDS.items():
        if standard_code in processed_golds:
            continue
        item = source_data.get(api_key)
        if not item:
            for k in source_data.keys():
                if k.lower() == api_key.lower():
                    item = source_data[k]
                    break
        if item:
            golds.append(create_item(standard_code, item, "gold"))
            processed_golds.add(standard_code)
    
    # Gümüş
    for silver_code in MOBILE_SILVER_CODES:
        item = source_data.get(silver_code)
        if not item:
            for k in source_data.keys():
                if k.lower() == silver_code.lower():
                    item = source_data[k]
                    break
        if item:
            silvers.append(create_item("AG", item, "silver"))
            break
    
    return currencies, golds, silvers

def calculate_summary(currencies):
    """Kazanan ve Kaybeden"""
    if len(currencies) < 2:
        return {}
    sorted_curr = sorted(currencies, key=lambda x: x['change_percent'])
    return {"loser": sorted_curr[0], "winner": sorted_curr[-1]}

# ======================================
# BANNER
# ======================================

def determine_banner_message() -> Optional[str]:
    """Banner öncelik: Mute > Manuel > Takvim"""
    if get_cache("system_mute"):
        logger.info("🤫 [BANNER] Sistem susturulmuş")
        return None
    manual_banner = get_cache("system_banner")
    if manual_banner:
        logger.info(f"📢 [BANNER] Manuel: {manual_banner}")
        return manual_banner
    auto_banner = get_todays_banner()
    if auto_banner:
        logger.info(f"📅 [BANNER] Otomatik: {auto_banner}")
        return auto_banner
    return None

# ======================================
# SNAPSHOT
# ======================================

def take_snapshot():
    """Gece 00:00 snapshot + Telegram rapor"""
    logger.info("📸 [SNAPSHOT] Gün sonu kapanış fiyatları alınıyor...")
    try:
        currencies_data = get_cache(Config.CACHE_KEYS['currencies_all'])
        golds_data = get_cache(Config.CACHE_KEYS['golds_all'])
        silvers_data = get_cache(Config.CACHE_KEYS['silvers_all'])
        
        if not currencies_data:
            logger.warning("⚠️ Canlı veri yok, snapshot alınamadı")
            return False
        
        snapshot = {}
        report_lines = []
        
        for item in currencies_data.get("data", []):
            code, selling = item.get("code"), item.get("selling", 0)
            if code and selling > 0:
                snapshot[code] = selling
                if code in ["USD", "EUR", "GBP", "CHF"]:
                    report_lines.append(f"💵 {code}: *{selling:.4f} ₺*")
        
        if golds_data:
            for item in golds_data.get("data", []):
                code, name, selling = item.get("code"), item.get("name", ""), item.get("selling", 0)
                if code and selling > 0:
                    snapshot[code] = selling
                    if code in ["GRA", "C22", "CUM"]:
                        formatted = f"{selling:,.2f}".replace(",", ".")
                        report_lines.append(f"🟡 {name}: *{formatted} ₺*")
        
        if silvers_data:
            for item in silvers_data.get("data", []):
                code, selling = item.get("code"), item.get("selling", 0)
                if code and selling > 0:
                    snapshot[code] = selling
                    report_lines.append(f"⚪ Gümüş: *{selling:.2f} ₺*")
        
        if snapshot:
            set_cache("kurabak:yesterday_prices", snapshot, ttl=0)
            logger.info(f"✅ SNAPSHOT: {len(snapshot)} varlık kaydedildi")
            
            try:
                from utils.telegram_monitor import telegram_monitor
                if telegram_monitor:
                    tz = pytz.timezone('Europe/Istanbul')
                    date_str = datetime.now(tz).strftime("%d.%m.%Y")
                    msg = (
                        f"📸 *REFERANS FİYATLAR ALINDI* | {date_str}\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"Patron, yarına kadar değişimler bu fiyatlara göre hesaplanacak:\n\n"
                        + "\n".join(report_lines) +
                        f"\n\n📦 *Toplam:* {len(snapshot)} varlık kilitlendi.\n✅ Sistem yarına hazır."
                    )
                    telegram_monitor.send_message(msg, level='report')
            except Exception as tg_err:
                logger.error(f"⚠️ Telegram rapor hatası: {tg_err}")
            return True
        return False
    except Exception as e:
        logger.error(f"❌ Snapshot hatası: {e}", exc_info=True)
        return False

# ======================================
# BAKIM MODU
# ======================================

def check_maintenance_mode() -> Tuple[bool, str, Optional[str]]:
    """Bakım modu kontrolü"""
    maintenance_data = get_cache("system_maintenance")
    if not maintenance_data:
        return False, "OPEN", None
    if isinstance(maintenance_data, dict):
        end_time = maintenance_data.get("end_time")
        if end_time and time.time() > end_time:
            from utils.cache import delete_cache
            delete_cache("system_maintenance")
            logger.info("✅ [BAKIM] Bakım süresi doldu")
            return False, "OPEN", None
        message = maintenance_data.get("message", "Sistem bakımda")
        mode = maintenance_data.get("mode", "limited")
        status = "MAINTENANCE_FULL" if mode == "full" else "MAINTENANCE"
        return True, status, message
    return False, "OPEN", None

# ======================================
# WORKER (ANA FONKSİYON)
# ======================================

def update_financial_data():
    """
    Her 2 dakikada bir çalışır.
    V5 -> TradingView -> Backup (V3/V4 kaldırıldı)
    """
    tz = pytz.timezone('Europe/Istanbul')
    now = datetime.now(tz)
    
    # 1. Bakım kontrolü
    is_maintenance, maint_status, maint_message = check_maintenance_mode()
    if is_maintenance:
        logger.info(f"🚧 [WORKER] Bakım Modu Aktif ({maint_status})")
        for key in [Config.CACHE_KEYS['currencies_all'], Config.CACHE_KEYS['golds_all'], 
                    Config.CACHE_KEYS['silvers_all'], Config.CACHE_KEYS['summary']]:
            data = get_cache(key)
            if data:
                data['status'] = maint_status
                data['market_msg'] = maint_message or "Sistem Bakımda"
                data['last_update'] = now.strftime("%H:%M:%S")
                data['banner'] = maint_message
                set_cache(key, data, ttl=0)
        return True
    
    # 2. Hafta sonu kilidi
    if now.weekday() == 5 or (now.weekday() == 6 and now.hour < 23):
        logger.info(f"🔒 [WORKER] Piyasa Kapalı ({now.strftime('%A %H:%M')})")
        for key in [Config.CACHE_KEYS['currencies_all'], Config.CACHE_KEYS['golds_all'],
                    Config.CACHE_KEYS['silvers_all'], Config.CACHE_KEYS['summary']]:
            data = get_cache(key)
            if data:
                data['status'] = "CLOSED"
                data['market_msg'] = "Piyasalar Kapalı"
                data['last_update'] = now.strftime("%H:%M:%S")
                set_cache(key, data, ttl=0)
        return True
    
    # 3. Veri çek
    logger.info("🔄 [WORKER] Piyasa açık, veri çekiliyor...")
    
    telegram_monitor = None
    try:
        from utils.telegram_monitor import telegram_monitor as tm
        telegram_monitor = tm
    except:
        pass
    
    was_system_down = get_cache("system_was_down") or False
    
    # Aktif kaynağı al
    active_source = get_cache(Config.CACHE_KEYS['active_source']) or "v5"
    
    data_raw = None
    source = None
    
    # Kaynak seçimine göre öncelik
    if active_source == "tradingview":
        # Manuel TradingView seçilmiş
        data_raw = fetch_from_tradingview()
        if data_raw:
            source = "TradingView"
        else:
            # TradingView başarısız, V5'e geç
            logger.warning("⚠️ TradingView başarısız, V5'e geçiliyor...")
            data_raw = fetch_from_v5()
            if data_raw:
                source = "V5"
    else:
        # Varsayılan: V5 -> TradingView
        data_raw = fetch_from_v5()
        if data_raw:
            source = "V5"
        else:
            logger.warning("⚠️ V5 başarısız, TradingView'e geçiliyor...")
            data_raw = fetch_from_tradingview()
            if data_raw:
                source = "TradingView"
    
    # Backup
    if not data_raw:
        logger.error("🔴 TÜM KAYNAKLAR ÇÖKTÜ! Backup aranıyor...")
        set_cache("system_was_down", True, ttl=0)
        
        backup_data = get_cache("kurabak:backup:all")
        if backup_data:
            logger.warning("✅ Backup verisi yüklendi")
            if telegram_monitor:
                telegram_monitor.send_message(
                    "⚠️ *TÜM KAYNAKLAR ÇÖKTÜ!*\n\nSistem yedeği kullanıyor.",
                    "critical"
                )
            for key in ['currencies', 'golds', 'silvers', 'summary']:
                backup_data[key]['status'] = "OPEN"
                set_cache(Config.CACHE_KEYS[f'{key}_all'], backup_data[key], ttl=0)
            Metrics.inc('backup')
            return True
        else:
            logger.critical("❌ BACKUP DA YOK!")
            if telegram_monitor:
                telegram_monitor.send_message("🚨 *KRİTİK: SİSTEM VERİ ALMIYOR!*", "critical")
            Metrics.inc('errors')
            return False
    
    # 4. "Düzeldi" bildirimi
    if was_system_down and data_raw:
        logger.info("✅ [WORKER] Sistem tekrar online!")
        from utils.cache import delete_cache
        delete_cache("system_was_down")
        if telegram_monitor:
            telegram_monitor.send_message(
                f"✅ *SİSTEM TEKRAR ONLINE!*\n\n"
                f"Tüm servisler normale döndü.\n"
                f"🚀 Kaynak: {source}\n"
                f"⏰ Zaman: {now.strftime('%H:%M:%S')}",
                level='report'
            )
    
    # 5. Parse ve hesapla
    try:
        currencies, golds, silvers = process_data_mobile_optimized(data_raw)
        
        if not currencies:
            logger.error(f"❌ {source} verisi boş")
            Metrics.inc('errors')
            return False
        
        yesterday_prices = get_cache("kurabak:yesterday_prices") or {}
        
        def enrich_with_calculation(items):
            enriched = []
            for item in items:
                code, current_price = item['code'], item['selling']
                change_percent = 0.0
                if code in yesterday_prices:
                    old_price = yesterday_prices[code]
                    if old_price > 0:
                        change_percent = ((current_price - old_price) / old_price) * 100
                trend = "NORMAL"
                if change_percent >= 2.0:
                    trend = "HIGH_UP"
                elif change_percent <= -2.0:
                    trend = "HIGH_DOWN"
                item['change_percent'] = round(change_percent, 2)
                item['trend'] = trend
                if current_price > 0:
                    enriched.append(item)
            return enriched
        
        currencies = enrich_with_calculation(currencies)
        golds = enrich_with_calculation(golds)
        silvers = enrich_with_calculation(silvers)
        
        if not currencies:
            logger.error("❌ Tüm veriler zehirli!")
            Metrics.inc('errors')
            return False
        
        summary = calculate_summary(currencies)
        Metrics.inc(source.lower().replace(" ", "_"))
        
        update_date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        banner_message = determine_banner_message()
        
        base_meta = {
            "source": source,
            "update_date": update_date_str,
            "timestamp": time.time(),
            "status": "OPEN",
            "market_msg": "Piyasalar Canlı",
            "last_update": now.strftime("%H:%M:%S"),
            "banner": banner_message
        }
        
        set_cache(Config.CACHE_KEYS['currencies_all'], {**base_meta, "data": currencies}, ttl=0)
        set_cache(Config.CACHE_KEYS['golds_all'], {**base_meta, "data": golds}, ttl=0)
        set_cache(Config.CACHE_KEYS['silvers_all'], {**base_meta, "data": silvers}, ttl=0)
        set_cache(Config.CACHE_KEYS['summary'], {**base_meta, "data": summary}, ttl=0)
        set_cache("kurabak:last_worker_run", time.time(), ttl=0)
        
        # 15 dakikalık backup
        last_backup_time = get_cache("kurabak:backup:timestamp") or 0
        current_time = time.time()
        if current_time - float(last_backup_time) > 900:
            logger.info("📦 15 Dakikalık Backup...")
            backup_payload = {
                "currencies": {**base_meta, "data": currencies},
                "golds": {**base_meta, "data": golds},
                "silvers": {**base_meta, "data": silvers},
                "summary": {**base_meta, "data": summary}
            }
            set_cache("kurabak:backup:all", backup_payload, ttl=0)
            set_cache("kurabak:backup:timestamp", current_time, ttl=0)
        
        banner_info = f"Banner: {banner_message[:30]}..." if banner_message else "Banner: Yok"
        logger.info(
            f"✅ [{source}] Worker Başarılı: "
            f"{len(currencies)} Döviz + {len(golds)} Altın + {len(silvers)} Gümüş "
            f"({banner_info})"
        )
        return True
        
    except Exception as e:
        logger.error(f"❌ Worker hatası: {e}", exc_info=True)
        Metrics.inc('errors')
        return False

def sync_financial_data() -> bool:
    """Eski kod uyumluluğu"""
    return update_financial_data()

def get_service_metrics():
    return Metrics.get()
