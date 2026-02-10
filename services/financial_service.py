"""
Financial Service - PRODUCTION READY V5.5 🚀💰🔥
=========================================================
✅ V5 API: Tek ve güvenilir kaynak
✅ BACKUP SYSTEM: 15 dakikalık otomatik yedekleme
✅ MOBİL OPTİMİZE: 23 Döviz + 6 Altın + 1 Gümüş
✅ WORKER + SNAPSHOT + BANNER + BAKIM MODU
✅ SELF-HEALING: Otomatik sistem kurtarma
✅ CIRCUIT BREAKER V2: Sadece durum değişiminde kaydet
✅ TREND ANALİZİ: %5 eşiği ile güçlü trend tespiti
✅ 💰 MARKET MARGIN SYSTEM V5.5: TAM MARJ + İKİ SNAPSHOT
✅ 🔥 JEWELER REBUILD: Marj değişince cache otomatik yenilenir
✅ 🔥 SNAPSHOT GÜNCELLEME: Marj değişince snapshot düzeltilir
✅ 🔥 SMOOTH MARJ GEÇİŞİ: Kademeli geçiş (alarm patlaması önlenir)

V5.5 Değişiklikler:
- 🔥 get_dynamic_margins(): 'dynamic:margins' (TAM MARJ, yarım değil)
- 🔥 save_daily_snapshot(): İki ayrı snapshot (raw + jeweler)
- 🔥 rebuild_jeweler_cache(): Marj değişince jeweler yenile
- 🔥 update_jeweler_snapshot(): Marj değişince snapshot düzelt
- 🔥 Worker'da jeweler_snapshot kullanımı
"""

import requests
import logging
import time
import json
import pytz
import copy
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from utils.cache import set_cache, get_cache, delete_cache
from utils.event_manager import get_todays_banner
from config import Config

logger = logging.getLogger(__name__)

# ======================================
# 🛡️ CIRCUIT BREAKER SYSTEM V2
# ======================================

class CircuitBreaker:
    """
    🔥 V4.5 FIX: Sadece durum değişiminde state kaydet!
    
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
        self.state = "CLOSED"
        self.failure_count = 0
        self.last_failure_time = 0
        self.last_open_time = 0
        
        self.failure_threshold = Config.CIRCUIT_BREAKER_FAILURE_THRESHOLD
        self.timeout = Config.CIRCUIT_BREAKER_TIMEOUT
        
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
            logger.debug(f"💾 [CIRCUIT] Durum kaydedildi: {self.state}")
        except Exception as e:
            logger.warning(f"⚠️ [CIRCUIT] Durum kaydetme hatası: {e}")
    
    def can_attempt(self) -> bool:
        """API çağrısı yapılabilir mi?"""
        current_time = time.time()
        
        if self.state == "CLOSED":
            return True
        
        if self.state == "OPEN":
            if current_time - self.last_open_time >= self.timeout:
                self.state = "HALF_OPEN"
                self._save_state()
                logger.info("🔄 [CIRCUIT] OPEN → HALF_OPEN (Test denemesi)")
                return True
            else:
                remaining = int(self.timeout - (current_time - self.last_open_time))
                logger.debug(f"⏳ [CIRCUIT] OPEN durumda, {remaining} saniye bekle")
                return False
        
        if self.state == "HALF_OPEN":
            return True
        
        return False
    
    def record_success(self):
        """Başarılı API çağrısı kaydı"""
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            self.failure_count = 0
            self._save_state()
            logger.info("✅ [CIRCUIT] HALF_OPEN → CLOSED (Sistem kurtarıldı!)")
            self._send_recovery_notification()
        
        elif self.state == "CLOSED":
            if self.failure_count > 0:
                logger.info(f"✅ [CIRCUIT] Başarılı çağrı, hata sayacı sıfırlandı (önceki: {self.failure_count})")
                self.failure_count = 0
    
    def record_failure(self):
        """Başarısız API çağrısı kaydı"""
        current_time = time.time()
        self.failure_count += 1
        self.last_failure_time = current_time
        
        if self.state == "HALF_OPEN":
            self.state = "OPEN"
            self.last_open_time = current_time
            self._save_state()
            logger.warning(f"❌ [CIRCUIT] HALF_OPEN → OPEN (Test başarısız, {self.timeout}s bekle)")
        
        elif self.state == "CLOSED":
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                self.last_open_time = current_time
                self._save_state()
                logger.error(f"🔴 [CIRCUIT] CLOSED → OPEN ({self.failure_count} hata, {self.timeout}s beklenecek)")
                self._send_open_notification()
            else:
                remaining = self.failure_threshold - self.failure_count
                logger.warning(f"⚠️ [CIRCUIT] Hata kaydedildi ({self.failure_count}/{self.failure_threshold}, {remaining} hata kaldı)")
    
    def _send_open_notification(self):
        """Circuit OPEN olduğunda Telegram bildirimi"""
        try:
            from utils.telegram_monitor import telegram_instance
            if telegram_instance:
                tz = pytz.timezone('Europe/Istanbul')
                now_str = datetime.now(tz).strftime("%H:%M:%S")
                
                msg = (
                    f"🔴 *CIRCUIT BREAKER AÇILDI!*\n\n"
                    f"V5 API {self.failure_count} kere üst üste hata verdi.\n"
                    f"⏳ Sistem {self.timeout} saniye bekleyecek.\n\n"
                    f"🕐 Zaman: {now_str}\n"
                    f"🔄 Otomatik kurtarma denenecek."
                )
                telegram_instance._send_raw(msg)
                logger.info("📤 [CIRCUIT] Telegram bildirimi gönderildi (OPEN)")
        except Exception as e:
            logger.warning(f"⚠️ [CIRCUIT] Telegram bildirimi hatası: {e}")
    
    def _send_recovery_notification(self):
        """Circuit CLOSED olduğunda Telegram bildirimi"""
        try:
            from utils.telegram_monitor import telegram_instance
            if telegram_instance:
                tz = pytz.timezone('Europe/Istanbul')
                now_str = datetime.now(tz).strftime("%H:%M:%S")
                
                msg = (
                    f"✅ *CIRCUIT BREAKER KAPANDI!*\n\n"
                    f"V5 API tekrar çalışıyor.\n"
                    f"Sistem normale döndü.\n\n"
                    f"🕐 Zaman: {now_str}\n"
                    f"🚀 Veri akışı devam ediyor."
                )
                telegram_instance._send_raw(msg)
                logger.info("📤 [CIRCUIT] Telegram bildirimi gönderildi (RECOVERY)")
        except Exception as e:
            logger.warning(f"⚠️ [CIRCUIT] Telegram bildirimi hatası: {e}")
    
    def get_status(self) -> dict:
        """Circuit Breaker durumunu döner"""
        return {
            'state': self.state,
            'failure_count': self.failure_count,
            'last_failure_time': self.last_failure_time,
            'last_open_time': self.last_open_time,
            'timeout': self.timeout,
            'can_attempt': self.can_attempt()
        }

circuit_breaker = CircuitBreaker()

# ======================================
# 📱 MOBİL KODLARI
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

TURKISH_NAMES = {
    "USD": "Amerikan Doları", "EUR": "Euro", "GBP": "İngiliz Sterlini",
    "CHF": "İsviçre Frangı", "CAD": "Kanada Doları", "AUD": "Avustralya Doları",
    "RUB": "Rus Rublesi", "SAR": "Suudi Arabistan Riyali", "AED": "BAE Dirhemi",
    "KWD": "Kuveyt Dinarı", "BHD": "Bahreyn Dinarı", "OMR": "Umman Riyali",
    "QAR": "Katar Riyali", "CNY": "Çin Yuanı", "SEK": "İsveç Kronu",
    "NOK": "Norveç Kronu", "PLN": "Polonya Zlotisi", "RON": "Romanya Leyi",
    "CZK": "Çek Kronu", "EGP": "Mısır Lirası", "RSD": "Sırp Dinarı",
    "HUF": "Macar Forinti", "BAM": "Bosna Markı",
    "GRA": "Gram Altın", "C22": "Çeyrek Altın", "YAR": "Yarım Altın",
    "TAM": "Tam Altın", "CUM": "Cumhuriyet Altını", "ATA": "Atatürk Altını",
    "AG": "Gümüş", "GUMUS": "Gümüş", "SILVER": "Gümüş"
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
        stats_copy = cls.stats.copy()
        stats_copy['circuit_breaker'] = circuit_breaker.get_status()
        return stats_copy

# ======================================
# YARDIMCI FONKSİYONLAR
# ======================================

def clean_money_string(value: Any) -> float:
    """Sayı parser"""
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
# 🔥 DİNAMİK MARJ SİSTEMİ V5.5 (TAM MARJ)
# ======================================

def get_dynamic_margins() -> Dict[str, float]:
    """
    🔥 V5.5: Redis'ten TAM MARJLARI al
    
    DEĞİŞİKLİK:
    - Önceki (V5.4): 'dynamic:half_margins' (yarım marj)
    - Yeni (V5.5): 'dynamic:margins' (TAM MARJ)
    
    Returns:
        Dict: {"GRA": 0.047, "C22": 0.016, ...}
    """
    # 1. Bugünkü TAM marjlar
    dynamic_margins = get_cache(Config.CACHE_KEYS.get('dynamic_margins', 'dynamic:margins'))
    
    if dynamic_margins and isinstance(dynamic_margins, dict):
        logger.debug(f"✅ [DİNAMİK MARJ] Redis'ten alındı: {len(dynamic_margins)} TAM MARJ")
        return dynamic_margins
    
    # 2. Fallback: margin_last_update
    last_update = get_cache(Config.CACHE_KEYS.get('margin_last_update', 'margin:last_update'))
    if last_update and isinstance(last_update, dict):
        margins = last_update.get('margins')
        if margins and isinstance(margins, dict):
            logger.warning("⚠️ [DİNAMİK MARJ] Fallback kullanıldı (margin_last_update)")
            return margins
    
    # 3. Son fallback: Boş dict (ham fiyat)
    logger.warning("⚠️ [DİNAMİK MARJ] Redis'te yok, HAM FİYAT kullanılacak")
    return {}


def get_cache_key_for_profile(base_key: str, profile: str) -> str:
    """
    Profile göre cache key döner
    
    Args:
        base_key: "currencies_all", "golds_all", "silvers_all"
        profile: "raw" veya "jeweler"
    
    Returns:
        Redis cache key
    """
    if profile == "raw":
        return Config.CACHE_KEYS[base_key]
    elif profile == "jeweler":
        jeweler_key = base_key.replace('_all', '_jeweler')
        return Config.CACHE_KEYS.get(jeweler_key, Config.CACHE_KEYS[base_key])
    else:
        logger.warning(f"⚠️ [CACHE KEY] Bilinmeyen profil: {profile}, raw key döndürülüyor")
        return Config.CACHE_KEYS[base_key]

# ======================================
# V5 FETCH
# ======================================

def fetch_from_v5() -> Optional[dict]:
    """V5 API'den veri çek (Circuit Breaker korumalı)"""
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
            circuit_breaker.record_success()
            logger.info("✅ [V5] Veri başarıyla çekildi")
            return resp.json()
        else:
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
    
    for code in MOBILE_CURRENCIES:
        item = source_data.get(code)
        if item and "crypto" not in str(item.get("Type", "")).lower():
            currencies.append(create_item(code, item, "currency"))
    
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
    """Banner mesajını döndür"""
    if get_cache("system_mute"):
        return None
    
    manual_banner = get_cache("system_banner")
    if manual_banner:
        return manual_banner
    
    auto_banner = get_todays_banner()
    return auto_banner

# ======================================
# 🔥 SNAPSHOT SİSTEMİ V5.5 (İKİ AYRI)
# ======================================

def save_daily_snapshot() -> bool:
    """
    🔥 V5.5: İKİ AYRI SNAPSHOT KAYDET (RAW + JEWELER)
    
    Gece 00:00:00'da çağrılır.
    
    DEĞİŞİKLİK:
    - Önceki isim: take_snapshot()
    - Yeni isim: save_daily_snapshot()
    - Yeni özellik: İki ayrı snapshot (raw + jeweler)
    
    GÖREV:
    1. Raw cache'lerden snapshot al
    2. Raw snapshot kaydet (raw_snapshot)
    3. Dinamik TAM marjları al
    4. Jeweler snapshot hesapla
    5. Jeweler snapshot kaydet (jeweler_snapshot)
    6. Telegram rapor gönder
    """
    logger.info("📸 [SNAPSHOT] Gün sonu kapanış fiyatları alınıyor (Raw + Jeweler)...")
    
    try:
        # 1. Raw cache'lerden veri al
        currencies_raw = get_cache(Config.CACHE_KEYS['currencies_all'])
        golds_raw = get_cache(Config.CACHE_KEYS['golds_all'])
        silvers_raw = get_cache(Config.CACHE_KEYS['silvers_all'])
        
        if not currencies_raw:
            logger.warning("⚠️ [SNAPSHOT] Canlı veri yok!")
            return False
        
        # 2. RAW SNAPSHOT oluştur
        raw_snapshot = {}
        
        for item in currencies_raw.get("data", []):
            code = item.get("code")
            selling = item.get("selling", 0)
            if code and selling > 0:
                raw_snapshot[code] = selling
        
        if golds_raw:
            for item in golds_raw.get("data", []):
                code = item.get("code")
                selling = item.get("selling", 0)
                if code and selling > 0:
                    raw_snapshot[code] = selling
        
        if silvers_raw:
            for item in silvers_raw.get("data", []):
                code = item.get("code")
                selling = item.get("selling", 0)
                if code and selling > 0:
                    raw_snapshot[code] = selling
        
        if not raw_snapshot:
            logger.error("❌ [SNAPSHOT] Raw snapshot boş!")
            return False
        
        # 3. RAW SNAPSHOT kaydet
        set_cache(
            Config.CACHE_KEYS['raw_snapshot'],
            raw_snapshot,
            ttl=0,
            force_disk_backup=True
        )
        logger.info(f"✅ [SNAPSHOT] RAW kaydedildi: {len(raw_snapshot)} varlık (Redis + Disk)")
        
        # 4. Dinamik TAM marjları al
        margin_map = get_dynamic_margins()
        
        # 5. JEWELER SNAPSHOT hesapla
        jeweler_snapshot = {}
        for code, raw_price in raw_snapshot.items():
            margin = margin_map.get(code, 0.0)
            jeweler_price = raw_price * (1 + margin)
            jeweler_snapshot[code] = round(jeweler_price, 4)
        
        # 6. JEWELER SNAPSHOT kaydet
        set_cache(
            Config.CACHE_KEYS['jeweler_snapshot'],
            jeweler_snapshot,
            ttl=0,
            force_disk_backup=True
        )
        logger.info(f"✅ [SNAPSHOT] JEWELER kaydedildi: {len(jeweler_snapshot)} varlık (Redis + Disk)")
        
        # 7. Telegram rapor gönder
        try:
            from utils.telegram_monitor import telegram_instance
            if telegram_instance:
                tz = pytz.timezone('Europe/Istanbul')
                date_str = datetime.now(tz).strftime("%d.%m.%Y")
                
                report_lines = []
                
                # Dövizler
                for code in ["USD", "EUR", "GBP", "CHF"]:
                    if code in raw_snapshot:
                        raw_val = raw_snapshot[code]
                        report_lines.append(f"💵 {code}: *{raw_val:.4f} ₺*")
                
                # Altınlar
                for code, name in [("GRA", "Gram"), ("C22", "Çeyrek"), ("CUM", "Cumhuriyet")]:
                    if code in raw_snapshot:
                        raw_val = raw_snapshot[code]
                        jeweler_val = jeweler_snapshot[code]
                        
                        raw_f = f"{raw_val:,.2f}".replace(",", ".")
                        jeweler_f = f"{jeweler_val:,.2f}".replace(",", ".")
                        
                        report_lines.append(
                            f"🟡 {name}:\n"
                            f"   Ham: {raw_f} ₺\n"
                            f"   Kuyumcu: {jeweler_f} ₺"
                        )
                
                # Gümüş
                if "AG" in raw_snapshot:
                    raw_val = raw_snapshot["AG"]
                    jeweler_val = jeweler_snapshot["AG"]
                    
                    report_lines.append(
                        f"⚪ Gümüş:\n"
                        f"   Ham: {raw_val:.2f} ₺\n"
                        f"   Kuyumcu: {jeweler_val:.2f} ₺"
                    )
                
                msg = (
                    f"📸 *SNAPSHOT ALINDI* | {date_str}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Yarına kadar değişimler bu fiyatlara göre hesaplanacak:\n\n"
                    + "\n".join(report_lines) +
                    f"\n\n📦 Toplam: {len(raw_snapshot)} varlık\n"
                    f"✅ İki profil (Raw + Kuyumcu) hazır\n"
                    f"🔥 TAM MARJ kullanıldı"
                )
                telegram_instance._send_raw(msg)
                
        except Exception as tg_err:
            logger.error(f"⚠️ [SNAPSHOT] Telegram hatası: {tg_err}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ [SNAPSHOT] Hata: {e}", exc_info=True)
        return False


# ======================================
# 🔥 JEWELER REBUILD V5.5
# ======================================

def rebuild_jeweler_cache() -> bool:
    """
    🔥 V5.5: JEWELER CACHE'İNİ YENİDEN OLUŞTUR
    
    Marj güncellendiğinde (00:05) çağrılır.
    
    GÖREV:
    1. Raw cache'leri al
    2. Yeni TAM marjları al
    3. Jeweler fiyatları hesapla
    4. Jeweler cache'lere kaydet
    """
    logger.info("🔧 [JEWELER REBUILD] Kuyumcu fiyatları yeniden hesaplanıyor...")
    
    try:
        # 1. Raw cache'leri al
        currencies_raw = get_cache(Config.CACHE_KEYS['currencies_all'])
        golds_raw = get_cache(Config.CACHE_KEYS['golds_all'])
        silvers_raw = get_cache(Config.CACHE_KEYS['silvers_all'])
        
        if not currencies_raw:
            logger.error("❌ [JEWELER REBUILD] Raw cache yok!")
            return False
        
        # 2. Yeni TAM marjları al
        margin_map = get_dynamic_margins()
        
        # 3. Marj uygulama fonksiyonu
        def apply_margins_to_items(items, margin_map):
            result = []
            for item in items:
                code = item.get("code")
                margin = margin_map.get(code, 0.0)
                
                new_item = copy.deepcopy(item)
                
                if margin > 0:
                    new_item["selling"] = round(new_item["selling"] * (1 + margin), 4)
                    new_item["buying"] = round(new_item["buying"] * (1 + margin), 4)
                    new_item["rate"] = new_item["selling"]
                
                result.append(new_item)
            
            return result
        
        # 4. Jeweler fiyatları hesapla
        currencies_jeweler = apply_margins_to_items(currencies_raw.get("data", []), margin_map)
        golds_jeweler = apply_margins_to_items(golds_raw.get("data", []), margin_map)
        silvers_jeweler = apply_margins_to_items(silvers_raw.get("data", []), margin_map)
        
        # 5. Jeweler cache'lere kaydet
        tz = pytz.timezone('Europe/Istanbul')
        now = datetime.now(tz)
        
        base_meta = {
            "source": "V5",
            "update_date": now.strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": time.time(),
            "status": "OPEN",
            "market_msg": "Piyasalar Canlı",
            "last_update": now.strftime("%H:%M:%S"),
            "banner": determine_banner_message()
        }
        
        jeweler_currencies_payload = {**base_meta, "data": currencies_jeweler}
        jeweler_golds_payload = {**base_meta, "data": golds_jeweler}
        jeweler_silvers_payload = {**base_meta, "data": silvers_jeweler}
        
        set_cache(Config.CACHE_KEYS['currencies_jeweler'], jeweler_currencies_payload, ttl=0)
        set_cache(Config.CACHE_KEYS['golds_jeweler'], jeweler_golds_payload, ttl=0)
        set_cache(Config.CACHE_KEYS['silvers_jeweler'], jeweler_silvers_payload, ttl=0)
        
        logger.info(
            f"✅ [JEWELER REBUILD] Tamamlandı: "
            f"{len(currencies_jeweler)} döviz, "
            f"{len(golds_jeweler)} altın, "
            f"{len(silvers_jeweler)} gümüş (YENİ TAM MARJLARLA)"
        )
        
        return True
        
    except Exception as e:
        logger.error(f"❌ [JEWELER REBUILD] Hata: {e}", exc_info=True)
        return False


def update_jeweler_snapshot() -> bool:
    """
    🔥 V5.5: JEWELER SNAPSHOT'I GÜNCELLE
    
    Marj güncellendiğinde (00:05) çağrılır.
    
    GÖREV:
    1. Raw snapshot al (asla değişmez)
    2. Yeni TAM marjları al
    3. Jeweler snapshot hesapla
    4. Jeweler snapshot güncelle
    """
    logger.info("🔧 [JEWELER SNAPSHOT] Güncelleniyor...")
    
    try:
        # 1. Raw snapshot al
        raw_snapshot = get_cache(Config.CACHE_KEYS['raw_snapshot'])
        
        if not raw_snapshot:
            logger.error("❌ [JEWELER SNAPSHOT] Raw snapshot yok!")
            return False
        
        # 2. Yeni TAM marjları al
        margin_map = get_dynamic_margins()
        
        # 3. Jeweler snapshot hesapla
        jeweler_snapshot = {}
        for code, raw_price in raw_snapshot.items():
            margin = margin_map.get(code, 0.0)
            jeweler_price = raw_price * (1 + margin)
            jeweler_snapshot[code] = round(jeweler_price, 4)
        
        # 4. Jeweler snapshot kaydet
        set_cache(
            Config.CACHE_KEYS['jeweler_snapshot'],
            jeweler_snapshot,
            ttl=0,
            force_disk_backup=True
        )
        
        logger.info(f"✅ [JEWELER SNAPSHOT] Güncellendi: {len(jeweler_snapshot)} varlık (YENİ TAM MARJLARLA)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ [JEWELER SNAPSHOT] Hata: {e}", exc_info=True)
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
# WORKER V5.5 (TAM MARJ + İKİ SNAPSHOT)
# ======================================

def update_financial_data():
    """
    🔥 V5.5: Worker (TAM MARJ + İKİ SNAPSHOT kullanımı)
    
    Her 1 dakikada bir çalışır.
    
    DEĞİŞİKLİKLER:
    - raw_snapshot kullanımı (önceki: yesterday_prices)
    - jeweler_snapshot kullanımı (önceki: yesterday_prices_jeweler)
    - TAM MARJ (önceki: yarım marj)
    """
    tz = pytz.timezone('Europe/Istanbul')
    now = datetime.now(tz)
    
    # Bakım modu kontrolü
    is_maintenance, maint_status, maint_message = check_maintenance_mode()
    if is_maintenance:
        logger.info(f"🚧 [WORKER] Bakım Modu Aktif ({maint_status})")
        return True
    
    # Piyasa kapalı kontrolü
    is_saturday = now.weekday() == 5
    is_friday_closed = now.weekday() == 4 and now.hour >= Config.MARKET_CLOSE_FRIDAY_HOUR
    is_sunday_morning_closed = now.weekday() == 6 and now.hour < Config.WEEKEND_REOPEN_HOUR
    
    if is_saturday or is_friday_closed or is_sunday_morning_closed:
        if not get_cache("market_closed_logged"):
            logger.info(f"🔒 [WORKER] Piyasa Kapalı - Hafta sonu modu başladı")
            set_cache("market_closed_logged", "true", ttl=43200)
        return True
    
    if get_cache("market_closed_logged"):
        logger.info("🔓 [WORKER] Piyasa açıldı - Normal mod başladı")
        delete_cache("market_closed_logged")
    
    logger.info("🔄 [WORKER] Piyasa açık, V5'ten veri çekiliyor...")
    
    # Telegram instance
    telegram_instance = None
    try:
        from utils.telegram_monitor import telegram_instance as tm
        telegram_instance = tm
    except:
        pass
    
    was_system_down = get_cache("system_was_down") or False
    
    # V5 API çağrısı
    data_raw = fetch_from_v5()
    source = "V5"
    
    if not data_raw:
        logger.error("🔴 V5 API ÇÖKTÜ! Backup aranıyor...")
        set_cache("system_was_down", True, ttl=0)
        
        backup_data = get_cache("kurabak:backup:all")
        if backup_data:
            logger.warning("✅ Backup verisi yüklendi")
            if telegram_instance:
                telegram_instance._send_raw("⚠️ *V5 API ÇÖKTÜ!*\n\nSistem yedeği kullanıyor.")
            
            for asset_type in ['currencies', 'golds', 'silvers']:
                backup_data[asset_type]['status'] = "OPEN"
                raw_key = Config.CACHE_KEYS[f'{asset_type}_all']
                set_cache(raw_key, backup_data[asset_type], ttl=0)
                
                if f"{asset_type}_jeweler" in backup_data:
                    jeweler_key = Config.CACHE_KEYS[f'{asset_type}_jeweler']
                    set_cache(jeweler_key, backup_data[f"{asset_type}_jeweler"], ttl=0)
            
            Metrics.inc('backup')
            return True
        else:
            logger.critical("❌ BACKUP DA YOK!")
            if telegram_instance:
                telegram_instance._send_raw("🚨 *KRİTİK: SİSTEM VERİ ALMIYOR!*")
            Metrics.inc('errors')
            return False
    
    if was_system_down and data_raw:
        logger.info("✅ [WORKER] Sistem tekrar online!")
        delete_cache("system_was_down")
        if telegram_instance:
            telegram_instance._send_raw(f"✅ *SİSTEM TEKRAR ONLINE!*\n\nKaynak: {source}\n⏰ {now.strftime('%H:%M:%S')}")
    
    try:
        # Parse
        currencies, golds, silvers = process_data_mobile_optimized(data_raw)
        
        if not currencies:
            logger.error(f"❌ {source} verisi boş")
            Metrics.inc('errors')
            return False
        
        # 🔥 V5.5: İKİ SNAPSHOT kullanımı
        raw_snapshot = get_cache(Config.CACHE_KEYS['raw_snapshot']) or {}
        jeweler_snapshot = get_cache(Config.CACHE_KEYS['jeweler_snapshot']) or {}
        
        def enrich_with_calculation(items, snapshot):
            """Değişim hesapla"""
            enriched = []
            for item in items:
                code = item['code']
                current_price = item['selling']
                change_percent = 0.0
                
                if code in snapshot:
                    old_price = snapshot[code]
                    if old_price > 0:
                        change_percent = ((current_price - old_price) / old_price) * 100
                
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
        
        # RAW veriler
        currencies_raw = enrich_with_calculation(currencies, raw_snapshot)
        golds_raw = enrich_with_calculation(golds, raw_snapshot)
        silvers_raw = enrich_with_calculation(silvers, raw_snapshot)
        
        if not currencies_raw:
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
        
        # RAW cache kaydet
        raw_currencies_payload = {**base_meta, "data": currencies_raw}
        raw_golds_payload = {**base_meta, "data": golds_raw}
        raw_silvers_payload = {**base_meta, "data": silvers_raw}
        
        set_cache(Config.CACHE_KEYS['currencies_all'], raw_currencies_payload, ttl=0)
        set_cache(Config.CACHE_KEYS['golds_all'], raw_golds_payload, ttl=0)
        set_cache(Config.CACHE_KEYS['silvers_all'], raw_silvers_payload, ttl=0)
        
        logger.info(f"✅ RAW veriler kaydedildi: {len(currencies_raw)} döviz, {len(golds_raw)} altın, {len(silvers_raw)} gümüş")
        
        # JEWELER veriler
        jeweler_currencies_items = copy.deepcopy(currencies)
        jeweler_golds_items = copy.deepcopy(golds)
        jeweler_silvers_items = copy.deepcopy(silvers)
        
        # 🔥 V5.5: TAM MARJ uygula
        margin_map = get_dynamic_margins()
        
        for item in jeweler_currencies_items:
            code = item.get("code")
            margin = margin_map.get(code, 0.0)
            if margin > 0:
                item["selling"] = round(item["selling"] * (1 + margin), 4)
                item["buying"] = round(item["buying"] * (1 + margin), 4)
                item["rate"] = item["selling"]
        
        for item in jeweler_golds_items:
            code = item.get("code")
            margin = margin_map.get(code, 0.0)
            if margin > 0:
                item["selling"] = round(item["selling"] * (1 + margin), 4)
                item["buying"] = round(item["buying"] * (1 + margin), 4)
                item["rate"] = item["selling"]
        
        for item in jeweler_silvers_items:
            code = item.get("code")
            margin = margin_map.get(code, 0.0)
            if margin > 0:
                item["selling"] = round(item["selling"] * (1 + margin), 4)
                item["buying"] = round(item["buying"] * (1 + margin), 4)
                item["rate"] = item["selling"]
        
        # Jeweler değişim hesapla
        jeweler_currencies = enrich_with_calculation(jeweler_currencies_items, jeweler_snapshot)
        jeweler_golds = enrich_with_calculation(jeweler_golds_items, jeweler_snapshot)
        jeweler_silvers = enrich_with_calculation(jeweler_silvers_items, jeweler_snapshot)
        
        # Jeweler cache kaydet
        jeweler_currencies_payload = {**base_meta, "data": jeweler_currencies}
        jeweler_golds_payload = {**base_meta, "data": jeweler_golds}
        jeweler_silvers_payload = {**base_meta, "data": jeweler_silvers}
        
        set_cache(Config.CACHE_KEYS['currencies_jeweler'], jeweler_currencies_payload, ttl=0)
        set_cache(Config.CACHE_KEYS['golds_jeweler'], jeweler_golds_payload, ttl=0)
        set_cache(Config.CACHE_KEYS['silvers_jeweler'], jeweler_silvers_payload, ttl=0)
        
        logger.info(f"✅ JEWELER veriler kaydedildi: {len(jeweler_currencies)} döviz, {len(jeweler_golds)} altın, {len(jeweler_silvers)} gümüş (TAM MARJ)")
        
        # Worker run timestamp
        set_cache("kurabak:last_worker_run", time.time(), ttl=0)
        
        # Backup (15 dakikada bir)
        last_backup_time = get_cache("kurabak:backup:timestamp") or 0
        current_time = time.time()
        
        if current_time - float(last_backup_time) > 900:
            logger.info("📦 15 Dakikalık Backup (Raw + Jeweler)...")
            
            backup_payload = {
                "currencies": raw_currencies_payload,
                "golds": raw_golds_payload,
                "silvers": raw_silvers_payload,
                "currencies_jeweler": jeweler_currencies_payload,
                "golds_jeweler": jeweler_golds_payload,
                "silvers_jeweler": jeweler_silvers_payload,
            }
            
            set_cache("kurabak:backup:all", backup_payload, ttl=0, force_disk_backup=True)
            set_cache("kurabak:backup:timestamp", current_time, ttl=0)
        
        banner_info = f"Banner: {banner_message[:30]}..." if banner_message else "Banner: Yok"
        cb_status = circuit_breaker.get_status()
        cb_info = f" | CB: {cb_status['state']}"
        
        logger.info(
            f"✅ [{source}] Worker Başarılı: "
            f"{len(currencies_raw)} Döviz + {len(golds_raw)} Altın + {len(silvers_raw)} Gümüş "
            f"(Raw + Jeweler TAM MARJ) ({banner_info}){cb_info}"
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


# ======================================
# ESKİ FONKSİYON UYUMLULUĞU
# ======================================

def take_snapshot():
    """
    🔥 V5.5: Geriye uyumluluk için
    
    Eski kod save_daily_snapshot() yerine take_snapshot() çağırıyorsa
    çalışmaya devam etsin diye bu wrapper var.
    """
    logger.warning("⚠️ [COMPAT] take_snapshot() kullanımı deprecated! save_daily_snapshot() kullanın.")
    return save_daily_snapshot()
