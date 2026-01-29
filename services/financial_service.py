"""
Financial Service - PRODUCTION READY V4.4 🚀
=========================================================
✅ V5 API: Tek ve güvenilir kaynak
✅ BACKUP SYSTEM: 15 dakikalık otomatik yedekleme
✅ MOBİL OPTİMİZE: 23 Döviz + 6 Altın + 1 Gümüş
✅ WORKER + SNAPSHOT + BANNER + BAKIM MODU
✅ SELF-HEALING: Otomatik sistem kurtarma
✅ NAME FIX: Tüm varlıklar Türkçe isimlerle gösteriliyor
✅ BANNER FIX: Takvim mesajları öncelikli
✅ AKILLI LOGLAMA: Piyasa kapalı spam önleme
✅ CIRCUIT BREAKER: 3 hata = 60 saniye bekle, otomatik kurtarma
✅ TREND ANALİZİ: %5 eşiği ile güçlü trend tespiti
✅ SUMMARY KALDIRMA: Günün özeti artık gönderilmiyor
"""

import requests
import logging
import time
import json
import pytz
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from utils.cache import set_cache, get_cache, delete_cache
from utils.event_manager import get_todays_banner
from config import Config

logger = logging.getLogger(__name__)

# ======================================
# 🛡️ CIRCUIT BREAKER SYSTEM
# ======================================

class CircuitBreaker:
    """
    API hatalarını yöneten sigorta sistemi.
    
    STATES:
    - CLOSED: Normal çalışma (API çağrıları yapılır)
    - OPEN: Devre açık (API çağrıları yapılmaz, 60 saniye bekle)
    - HALF_OPEN: Test modu (1 deneme yapılır, başarılıysa CLOSED)
    
    RULES:
    - 3 kere üst üste hata → OPEN (60 saniye bekle)
    - OPEN süresi dolunca → HALF_OPEN (1 deneme)
    - HALF_OPEN'da başarı → CLOSED (normal moda dön)
    - HALF_OPEN'da hata → tekrar OPEN
    """
    
    def __init__(self):
        self.state = "CLOSED"  # CLOSED | OPEN | HALF_OPEN
        self.failure_count = 0
        self.last_failure_time = 0
        self.last_open_time = 0
        
        # Config'den oku
        self.failure_threshold = Config.CIRCUIT_BREAKER_FAILURE_THRESHOLD
        self.timeout = Config.CIRCUIT_BREAKER_TIMEOUT
        
        # Cache'den mevcut durumu yükle
        self._load_state()
    
    def _load_state(self):
        """Redis/RAM'den mevcut durumu yükle"""
        try:
            state_data = get_cache(Config.CACHE_KEYS['circuit_breaker_state'])
            if state_data:
                self.state = state_data.get('state', 'CLOSED')
                self.failure_count = state_data.get('failure_count', 0)
                self.last_failure_time = state_data.get('last_failure_time', 0)
                self.last_open_time = state_data.get('last_open_time', 0)
                logger.info(f"🔄 [CIRCUIT] Durum yüklendi: {self.state} (Hatalar: {self.failure_count})")
        except Exception as e:
            logger.warning(f"⚠️ [CIRCUIT] Durum yükleme hatası: {e}")
    
    def _save_state(self):
        """Mevcut durumu Redis/RAM'e kaydet"""
        try:
            state_data = {
                'state': self.state,
                'failure_count': self.failure_count,
                'last_failure_time': self.last_failure_time,
                'last_open_time': self.last_open_time
            }
            set_cache(Config.CACHE_KEYS['circuit_breaker_state'], state_data, ttl=0)
        except Exception as e:
            logger.warning(f"⚠️ [CIRCUIT] Durum kaydetme hatası: {e}")
    
    def can_attempt(self) -> bool:
        """
        API çağrısı yapılabilir mi?
        
        Returns:
            True: Çağrı yap
            False: Bekle, çağrı yapma
        """
        current_time = time.time()
        
        # CLOSED durumu → Her zaman çağrı yapabilir
        if self.state == "CLOSED":
            return True
        
        # OPEN durumu → Timeout doldu mu?
        if self.state == "OPEN":
            if current_time - self.last_open_time >= self.timeout:
                # Timeout doldu, HALF_OPEN'a geç
                self.state = "HALF_OPEN"
                self._save_state()
                logger.info("🔄 [CIRCUIT] OPEN → HALF_OPEN (Test denemesi)")
                return True
            else:
                # Henüz timeout dolmadı
                remaining = int(self.timeout - (current_time - self.last_open_time))
                logger.debug(f"⏳ [CIRCUIT] OPEN durumda, {remaining} saniye bekle")
                return False
        
        # HALF_OPEN durumu → 1 deneme yapılabilir
        if self.state == "HALF_OPEN":
            return True
        
        return False
    
    def record_success(self):
        """
        Başarılı API çağrısı kaydı
        
        - HALF_OPEN → CLOSED (Kurtarıldı!)
        - CLOSED → failure_count sıfırla
        """
        previous_state = self.state
        
        if self.state == "HALF_OPEN":
            # Test başarılı, normal moda dön
            self.state = "CLOSED"
            self.failure_count = 0
            self._save_state()
            logger.info("✅ [CIRCUIT] HALF_OPEN → CLOSED (Sistem kurtarıldı!)")
            
            # Telegram bildirimi gönder
            self._send_recovery_notification()
        
        elif self.state == "CLOSED":
            # Normal durumda başarı → failure_count sıfırla
            if self.failure_count > 0:
                logger.info(f"✅ [CIRCUIT] Başarılı çağrı, hata sayacı sıfırlandı (önceki: {self.failure_count})")
                self.failure_count = 0
                self._save_state()
    
    def record_failure(self):
        """
        Başarısız API çağrısı kaydı
        
        - failure_count artır
        - Threshold aşıldı mı? → OPEN
        - HALF_OPEN'da hata → tekrar OPEN
        """
        current_time = time.time()
        self.failure_count += 1
        self.last_failure_time = current_time
        
        previous_state = self.state
        
        if self.state == "HALF_OPEN":
            # Test başarısız, tekrar OPEN
            self.state = "OPEN"
            self.last_open_time = current_time
            self._save_state()
            logger.warning(f"❌ [CIRCUIT] HALF_OPEN → OPEN (Test başarısız, {self.timeout}s bekle)")
        
        elif self.state == "CLOSED":
            # Normal durumda hata sayacı
            if self.failure_count >= self.failure_threshold:
                # Threshold aşıldı, OPEN'a geç
                self.state = "OPEN"
                self.last_open_time = current_time
                self._save_state()
                logger.error(
                    f"🔴 [CIRCUIT] CLOSED → OPEN "
                    f"({self.failure_count} hata, {self.timeout}s beklenecek)"
                )
                
                # Telegram bildirimi gönder
                self._send_open_notification()
            else:
                # Henüz threshold'a ulaşılmadı
                remaining = self.failure_threshold - self.failure_count
                logger.warning(
                    f"⚠️ [CIRCUIT] Hata kaydedildi "
                    f"({self.failure_count}/{self.failure_threshold}, {remaining} hata kaldı)"
                )
                self._save_state()
    
    def _send_open_notification(self):
        """Circuit OPEN olduğunda Telegram bildirimi gönder"""
        try:
            from utils.telegram_monitor import telegram_monitor
            if telegram_monitor:
                tz = pytz.timezone('Europe/Istanbul')
                now_str = datetime.now(tz).strftime("%H:%M:%S")
                
                msg = (
                    f"🔴 *CIRCUIT BREAKER AÇILDI!*\n\n"
                    f"V5 API {self.failure_count} kere üst üste hata verdi.\n"
                    f"⏳ Sistem {self.timeout} saniye bekleyecek.\n\n"
                    f"🕐 Zaman: {now_str}\n"
                    f"🔄 Otomatik kurtarma denenecek."
                )
                telegram_monitor.send_message(msg, level='critical')
                logger.info("📤 [CIRCUIT] Telegram bildirimi gönderildi (OPEN)")
        except Exception as e:
            logger.warning(f"⚠️ [CIRCUIT] Telegram bildirimi hatası: {e}")
    
    def _send_recovery_notification(self):
        """Circuit CLOSED olduğunda Telegram bildirimi gönder"""
        try:
            from utils.telegram_monitor import telegram_monitor
            if telegram_monitor:
                tz = pytz.timezone('Europe/Istanbul')
                now_str = datetime.now(tz).strftime("%H:%M:%S")
                
                msg = (
                    f"✅ *CIRCUIT BREAKER KAPANDI!*\n\n"
                    f"V5 API tekrar çalışıyor.\n"
                    f"Sistem normale döndü.\n\n"
                    f"🕐 Zaman: {now_str}\n"
                    f"🚀 Veri akışı devam ediyor."
                )
                telegram_monitor.send_message(msg, level='report')
                logger.info("📤 [CIRCUIT] Telegram bildirimi gönderildi (RECOVERY)")
        except Exception as e:
            logger.warning(f"⚠️ [CIRCUIT] Telegram bildirimi hatası: {e}")
    
    def get_status(self) -> dict:
        """
        Circuit Breaker durumunu döner
        
        Returns:
            {
                'state': 'CLOSED' | 'OPEN' | 'HALF_OPEN',
                'failure_count': int,
                'last_failure_time': float,
                'last_open_time': float,
                'timeout': int
            }
        """
        return {
            'state': self.state,
            'failure_count': self.failure_count,
            'last_failure_time': self.last_failure_time,
            'last_open_time': self.last_open_time,
            'timeout': self.timeout,
            'can_attempt': self.can_attempt()
        }

# Global Circuit Breaker instance
circuit_breaker = CircuitBreaker()

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
# 🆕 TÜRKÇE İSİM HARITALAMASI
# ======================================

TURKISH_NAMES = {
    # Dövizler
    "USD": "Amerikan Doları",
    "EUR": "Euro",
    "GBP": "İngiliz Sterlini",
    "CHF": "İsviçre Frangı",
    "CAD": "Kanada Doları",
    "AUD": "Avustralya Doları",
    "RUB": "Rus Rublesi",
    "SAR": "Suudi Arabistan Riyali",
    "AED": "BAE Dirhemi",
    "KWD": "Kuveyt Dinarı",
    "BHD": "Bahreyn Dinarı",
    "OMR": "Umman Riyali",
    "QAR": "Katar Riyali",
    "CNY": "Çin Yuanı",
    "SEK": "İsveç Kronu",
    "NOK": "Norveç Kronu",
    "PLN": "Polonya Zlotisi",
    "RON": "Romanya Leyi",
    "CZK": "Çek Kronu",
    "EGP": "Mısır Lirası",
    "RSD": "Sırp Dinarı",
    "HUF": "Macar Forinti",
    "BAM": "Bosna Markı",
    
    # Altınlar
    "GRA": "Gram Altın",
    "C22": "Çeyrek Altın",
    "YAR": "Yarım Altın",
    "TAM": "Tam Altın",
    "CUM": "Cumhuriyet Altını",
    "ATA": "Atatürk Altını",
    
    # Gümüş
    "AG": "Gümüş",
    "GUMUS": "Gümüş",
    "SILVER": "Gümüş"
}

# ======================================
# METRİKLER
# ======================================

class Metrics:
    stats = {'v5': 0, 'backup': 0, 'errors': 0, 'circuit_breaker_trips': 0}
    
    @classmethod
    def inc(cls, key):
        cls.stats[key] = cls.stats.get(key, 0) + 1

    @classmethod
    def get(cls):
        # Circuit breaker durumunu ekle
        stats_copy = cls.stats.copy()
        stats_copy['circuit_breaker'] = circuit_breaker.get_status()
        return stats_copy

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
    """Standart veri objesi - Türkçe isimlerle"""
    buying = clean_money_string(raw_item.get("Buying"))
    selling = clean_money_string(raw_item.get("Selling"))
    change = clean_money_string(raw_item.get("Change"))
    if selling == 0: selling = buying
    if buying == 0: buying = selling
    
    turkish_name = TURKISH_NAMES.get(code, code)
    
    return {
        "code": code, 
        "name": turkish_name,
        "buying": round(buying, 4), 
        "selling": round(selling, 4),
        "rate": round(selling, 4), 
        "change_percent": round(change, 2),
        "type": item_type
    }

# ======================================
# V5 FETCH (CIRCUIT BREAKER İLE)
# ======================================

def fetch_from_v5() -> Optional[dict]:
    """
    V5 API'den veri çek (Circuit Breaker korumalı)
    
    Returns:
        dict: Başarılıysa veri
        None: Hata varsa veya circuit açıksa
    """
    # Circuit Breaker kontrolü
    if not circuit_breaker.can_attempt():
        logger.warning("🔴 [V5] Circuit Breaker OPEN - API çağrısı yapılamıyor")
        Metrics.inc('circuit_breaker_trips')
        return None
    
    try:
        resp = requests.get(
            Config.API_V5_URL,
            timeout=Config.API_V5_TIMEOUT,
            headers={"User-Agent": "KuraBak/Mobile"}
        )
        
        if resp.status_code == 200:
            # Başarılı çağrı
            circuit_breaker.record_success()
            logger.info("✅ [V5] Veri başarıyla çekildi")
            return resp.json()
        else:
            # HTTP hatası
            circuit_breaker.record_failure()
            logger.warning(f"⚠️ [V5] HTTP {resp.status_code}")
            return None
            
    except requests.Timeout:
        circuit_breaker.record_failure()
        logger.warning("⚠️ [V5] Timeout hatası")
        return None
    except requests.ConnectionError:
        circuit_breaker.record_failure()
        logger.warning("⚠️ [V5] Bağlantı hatası")
        return None
    except Exception as e:
        circuit_breaker.record_failure()
        logger.warning(f"⚠️ [V5] Fetch Error: {str(e)[:50]}")
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

# ======================================
# BANNER
# ======================================

def determine_banner_message() -> Optional[str]:
    """Banner öncelik sırası"""
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
    Her 1 dakikada bir çalışır.
    V5 API (Tek Kaynak + Circuit Breaker) → Backup
    """
    tz = pytz.timezone('Europe/Istanbul')
    now = datetime.now(tz)
    
    # 1. Bakım kontrolü
    is_maintenance, maint_status, maint_message = check_maintenance_mode()
    if is_maintenance:
        logger.info(f"🚧 [WORKER] Bakım Modu Aktif ({maint_status})")
        for key in [Config.CACHE_KEYS['currencies_all'], Config.CACHE_KEYS['golds_all'], 
                    Config.CACHE_KEYS['silvers_all']]:
            data = get_cache(key)
            if data:
                data['status'] = maint_status
                data['market_msg'] = maint_message or "Sistem Bakımda"
                data['last_update'] = now.strftime("%H:%M:%S")
                data['banner'] = maint_message
                set_cache(key, data, ttl=0)
        return True
    
    # 2. Hafta sonu kilidi (Akıllı loglama)
    if now.weekday() == 5 or (now.weekday() == 6 and now.hour < 23):
        if not get_cache("market_closed_logged"):
            logger.info(f"🔒 [WORKER] Piyasa Kapalı - Hafta sonu modu başladı")
            set_cache("market_closed_logged", "true", ttl=43200)
        else:
            logger.debug(f"🔒 [WORKER] Piyasa Kapalı ({now.strftime('%A %H:%M')})")
        
        for key in [Config.CACHE_KEYS['currencies_all'], Config.CACHE_KEYS['golds_all'],
                    Config.CACHE_KEYS['silvers_all']]:
            data = get_cache(key)
            if data:
                data['status'] = "CLOSED"
                data['market_msg'] = "Piyasalar Kapalı"
                data['last_update'] = now.strftime("%H:%M:%S")
                set_cache(key, data, ttl=0)
        return True
    
    if get_cache("market_closed_logged"):
        logger.info("🔓 [WORKER] Piyasa açıldı - Normal mod başladı")
        delete_cache("market_closed_logged")
    
    # 3. Veri çek (V5 + Circuit Breaker)
    logger.info("🔄 [WORKER] Piyasa açık, V5'ten veri çekiliyor...")
    
    telegram_monitor = None
    try:
        from utils.telegram_monitor import telegram_monitor as tm
        telegram_monitor = tm
    except:
        pass
    
    was_system_down = get_cache("system_was_down") or False
    
    # V5 API'den veri çek (Circuit Breaker korumalı)
    data_raw = fetch_from_v5()
    source = "V5"
    
    # Backup kontrolü
    if not data_raw:
        logger.error("🔴 V5 API ÇÖKTÜ! Backup aranıyor...")
        set_cache("system_was_down", True, ttl=0)
        
        backup_data = get_cache("kurabak:backup:all")
        if backup_data:
            logger.warning("✅ Backup verisi yüklendi")
            if telegram_monitor:
                telegram_monitor.send_message(
                    "⚠️ *V5 API ÇÖKTÜ!*\n\nSistem yedeği kullanıyor.",
                    "critical"
                )
            for key in ['currencies', 'golds', 'silvers']:
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
                
                # 🔥 YENİ TREND THRESHOLD: %5
                trend = "NORMAL"
                if change_percent >= Config.TREND_HIGH_THRESHOLD:
                    trend = "HIGH_UP"
                elif change_percent <= -Config.TREND_HIGH_THRESHOLD:
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
        
        Metrics.inc('v5')
        
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
        
        # Cache'e kaydet (Summary olmadan)
        set_cache(Config.CACHE_KEYS['currencies_all'], {
            **base_meta, 
            "data": currencies
        }, ttl=0)
        
        set_cache(Config.CACHE_KEYS['golds_all'], {**base_meta, "data": golds}, ttl=0)
        set_cache(Config.CACHE_KEYS['silvers_all'], {**base_meta, "data": silvers}, ttl=0)
        set_cache("kurabak:last_worker_run", time.time(), ttl=0)
        
        # 15 dakikalık backup
        last_backup_time = get_cache("kurabak:backup:timestamp") or 0
        current_time = time.time()
        if current_time - float(last_backup_time) > 900:
            logger.info("📦 15 Dakikalık Backup...")
            backup_payload = {
                "currencies": {**base_meta, "data": currencies},
                "golds": {**base_meta, "data": golds},
                "silvers": {**base_meta, "data": silvers}
            }
            set_cache("kurabak:backup:all", backup_payload, ttl=0)
            set_cache("kurabak:backup:timestamp", current_time, ttl=0)
        
        banner_info = f"Banner: {banner_message[:30]}..." if banner_message else "Banner: Yok"
        
        # Circuit Breaker durumu
        cb_status = circuit_breaker.get_status()
        cb_info = f" | CB: {cb_status['state']}"
        
        logger.info(
            f"✅ [{source}] Worker Başarılı: "
            f"{len(currencies)} Döviz + {len(golds)} Altın + {len(silvers)} Gümüş "
            f"({banner_info}){cb_info}"
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
    """Metrikler + Circuit Breaker durumu"""
    return Metrics.get()

def get_circuit_breaker_status():
    """Circuit Breaker durumunu döner"""
    return circuit_breaker.get_status()
