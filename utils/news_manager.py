import os
import logging
import requests
import time
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import google.generativeai as genai
from difflib import SequenceMatcher
from bs4 import BeautifulSoup

from utils.cache import get_cache, set_cache, delete_cache
from config import Config

logger = logging.getLogger(__name__)

GNEWS_API_KEY = os.getenv('GNEWS_API_KEY')
NEWSDATA_API_KEY = os.getenv('NEWSDATA_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

_bootstrap_lock = threading.Lock()
_bootstrap_in_progress = {
    'morning': False,
    'evening': False
}

_bootstrap_last_attempt = {
    'morning': 0,
    'evening': 0
}
_bootstrap_cooldown = 3600

_margin_bootstrap_lock = threading.Lock()
_margin_bootstrap_in_progress = False

_last_logged_banner = None

# ─────────────────────────────────────────────────────────────
# Türkiye resmi tatil takvimi — Gemini'ye güvenmek yerine sabit
# liste kullanılır. Her yıl başında _TURKEY_VARIABLE_HOLIDAYS
# güncellenmesi yeterli.
# ─────────────────────────────────────────────────────────────

# Yıl bağımsız tekrar eden tatiller
# Format: (ay, gün_başlangıç, gün_bitiş, mesaj, emoji)
_TURKEY_RECURRING_HOLIDAYS = [
    (1,  1,  1,  "Yılbaşı",                     "🎆"),
    (4,  23, 23, "23 Nisan Ulusal Egemenlik",     "🇹🇷"),
    (5,  1,  1,  "1 Mayıs İşçi Bayramı",         "🌸"),
    (5,  19, 19, "19 Mayıs Atatürk'ü Anma",      "🇹🇷"),
    (7,  15, 15, "15 Temmuz Demokrasi Bayramı",  "🇹🇷"),
    (8,  30, 30, "30 Ağustos Zafer Bayramı",     "🇹🇷"),
    (10, 29, 29, "29 Ekim Cumhuriyet Bayramı",   "🇹🇷"),
    (11, 10, 10, "10 Kasım Atatürk'ü Anma",      "🕯️"),
]

# Yıla göre değişen dini bayramlar — her yıl buraya ekle
# Format: (yıl, ay, gün_başlangıç, gün_bitiş, mesaj, emoji)
_TURKEY_VARIABLE_HOLIDAYS = [
    # Ramazan Bayramı
    (2024, 4,  10, 12, "Ramazan Bayramı", "🌙"),
    (2025, 3,  30,  1, "Ramazan Bayramı", "🌙"),
    (2026, 3,  20, 22, "Ramazan Bayramı", "🌙"),
    (2027, 3,  10, 12, "Ramazan Bayramı", "🌙"),
    # Kurban Bayramı
    (2024, 6,  16, 19, "Kurban Bayramı",  "🐑"),
    (2025, 6,   6,  9, "Kurban Bayramı",  "🐑"),
    (2026, 5,  27, 30, "Kurban Bayramı",  "🐑"),
    (2027, 5,  17, 20, "Kurban Bayramı",  "🐑"),
]


def get_today_holiday() -> Optional[tuple]:
    """
    Bugün Türkiye'de resmi tatil/bayram varsa (mesaj, emoji, bitiş_tarihi) döndür.
    Yoksa None döndür. Gemini'ye güvenmek yerine sabit takvim kullanır.
    """
    today = datetime.now().date()
    y, m, d = today.year, today.month, today.day

    # Değişken dini bayramlar (yıla göre)
    for entry in _TURKEY_VARIABLE_HOLIDAYS:
        hy, hm, hd_start, hd_end, msg, emoji = entry
        # Ramazan 2025: 30 Mart - 1 Nisan ay geçişi için özel kontrol
        if hy == y:
            from datetime import date as date_type
            try:
                start = date_type(hy, hm, hd_start)
                # bitiş ayı farklı olabilir (örn. Mart 30 - Nisan 1)
                if hd_end < hd_start:
                    # ay geçişi var
                    import calendar
                    last_day = calendar.monthrange(hy, hm)[1]
                    end_month = hm + 1 if hm < 12 else 1
                    end_year  = hy if hm < 12 else hy + 1
                    end = date_type(end_year, end_month, hd_end)
                else:
                    end = date_type(hy, hm, hd_end)
                if start <= today <= end:
                    return msg, emoji, end
            except Exception:
                pass

    # Tekrar eden sabit tatiller
    for entry in _TURKEY_RECURRING_HOLIDAYS:
        hm, hd_start, hd_end, msg, emoji = entry
        if hm == m and hd_start <= d <= hd_end:
            from datetime import date as date_type
            end_date = date_type(y, hm, hd_end)
            return msg, emoji, end_date

    return None


_FALLBACK_GOLD_MARGINS = {
    'GRA':   0.030,
    'C22':   0.025,
    'YAR':   0.025,
    'TAM':   0.020,
    'CUM':   0.015,
    'ATA':   0.017,
    'AG':    0.080,
    'GUMUS': 0.080,
}

_FALLBACK_CURRENCY_MARGINS = {
    'USD': 0.030, 'EUR': 0.030, 'GBP': 0.030,
    'CHF': 0.030, 'CAD': 0.030, 'AUD': 0.030,
    'SEK': 0.030, 'NOK': 0.030, 'SAR': 0.030,
    'DKK': 0.030, 'JPY': 0.030,
    'RUB': 0.015, 'AED': 0.013, 'KWD': 0.013,
    'BHD': 0.013, 'OMR': 0.013, 'QAR': 0.013,
    'CNY': 0.014, 'PLN': 0.014, 'RON': 0.015,
    'CZK': 0.015, 'EGP': 0.018, 'RSD': 0.018,
    'HUF': 0.015, 'BAM': 0.015,
}

# ─────────────────────────────────────────────────────────────
# Harem'in gerçek spread'leri ölçülerek upper bound'lar güncellendi.
# GRA ~%5, C22 ~%18, YAR ~%9, TAM ~%5, ATA ~%5, AG ~%7
# C22 için max %25'e yükseltildi — Harem çeyrek spread gerçekte ~%18.
# ─────────────────────────────────────────────────────────────
_MARGIN_VALID_RANGES = {
    'GRA':   (0.008, 0.130),
    'C22':   (0.003, 0.250),
    'YAR':   (0.003, 0.150),
    'TAM':   (0.003, 0.120),
    'CUM':   (0.008, 0.120),
    'ATA':   (0.003, 0.120),
    'AG':    (0.020, 0.130),
    'GUMUS': (0.020, 0.130),
    'USD':   (0.005, 0.050),
    'EUR':   (0.005, 0.050),
    'GBP':   (0.005, 0.050),
    'CHF':   (0.005, 0.050),
    'CAD':   (0.005, 0.050),
    'AUD':   (0.005, 0.050),
    'SEK':   (0.005, 0.060),
    'NOK':   (0.005, 0.060),
    'SAR':   (0.005, 0.050),
    'DKK':   (0.005, 0.050),
    'JPY':   (0.005, 0.050),
}

# ─────────────────────────────────────────────────────────────
# Harem sitesindeki ürün adı → standart kod eşlemesi.
# CUM Harem sitesinde yok, bu yüzden map'e eklenmedi.
# ATA satır adı "ata altın" olarak geliyor.
# ─────────────────────────────────────────────────────────────
_HAREM_PRODUCT_MAP = {
    'gram altın':   'GRA',
    'gramaltin':    'GRA',
    'çeyrek altın': 'C22',
    'ceyrek altin': 'C22',
    'yarım altın':  'YAR',
    'yarim altin':  'YAR',
    'tam altın':    'TAM',
    'tam altin':    'TAM',
    'ata altın':    'ATA',
    'ata altin':    'ATA',
    'gram gümüş':   'AG',
    'gram gumus':   'AG',
}

_ZIRAAT_CURRENCY_MAP = {
    'abd dolari':             'USD',
    'usd':                    'USD',
    'euro':                   'EUR',
    'eur':                    'EUR',
    'ingiliz sterlini':       'GBP',
    'gbp':                    'GBP',
    'sterlin':                'GBP',
    'isviçre frangı':         'CHF',
    'chf':                    'CHF',
    'franc':                  'CHF',
    'kanada dolari':          'CAD',
    'cad':                    'CAD',
    'avustralya dolari':      'AUD',
    'aud':                    'AUD',
    'isveç kronasi':          'SEK',
    'sek':                    'SEK',
    'norveç kronasi':         'NOK',
    'nok':                    'NOK',
    'suudi arabistan riyali': 'SAR',
    'sar':                    'SAR',
    'danimarka kronasi':      'DKK',
    'dkk':                    'DKK',
    'japon yeni':             'JPY',
    'jpy':                    'JPY',
}

# ─────────────────────────────────────────────────────────────
# CUM ve ATA eklendi. CUM Harem'de olmadığı için
# harem_prices.get('CUM') None döner → otomatik atlanır,
# CUM marjı static/fallback'ten gelmeye devam eder.
# ─────────────────────────────────────────────────────────────
_GOLD_API_MAPPING = {
    'GRA': 'GRA',
    'C22': 'CEYREKALTIN',
    'YAR': 'YARIMALTIN',
    'TAM': 'TAMALTIN',
    'CUM': 'CUMHURIYETALTINI',
    'ATA': 'ATAALTIN',
    'AG':  'GUMUS',
}

_CURRENCY_API_KEYS = [
    'USD', 'EUR', 'GBP', 'CHF',
    'SEK', 'NOK', 'SAR', 'DKK'
]

_GOLD_MIN_PRICE = {
    'GRA': 500.0,
    'C22': 5000.0,
    'YAR': 10000.0,
    'TAM': 20000.0,
    'CUM': 20000.0,
    'ATA': 20000.0,
    'AG':  50.0,
}


def _validate_margin(key: str, value: float) -> bool:
    if key not in _MARGIN_VALID_RANGES:
        return True
    min_val, max_val = _MARGIN_VALID_RANGES[key]
    valid = min_val <= value <= max_val
    if not valid:
        logger.warning(
            f"⚠️ [VALİDASYON] {key} marjı geçersiz: {value:.4f} "
            f"(beklenen: {min_val:.4f}-{max_val:.4f}) → REDDEDİLDİ"
        )
    return valid


def _get_config_fallback_margins() -> Dict[str, float]:
    gold     = getattr(Config, 'DEFAULT_GOLD_MARGINS', _FALLBACK_GOLD_MARGINS)
    currency = getattr(Config, 'DEFAULT_CURRENCY_MARGINS', _FALLBACK_CURRENCY_MARGINS)
    exotic   = getattr(Config, 'STATIC_EXOTIC_MARGINS', {})
    return {**_FALLBACK_GOLD_MARGINS, **_FALLBACK_CURRENCY_MARGINS, **gold, **currency, **exotic}


def _call_gemini_with_retry(model, prompt: str, label: str = "GEMİNİ") -> Optional[str]:
    delays = [60]
    for attempt in range(2):
        try:
            response = model.generate_content(prompt, request_options={"timeout": 120})
            result = response.text.strip()
            if result and len(result) > 10:
                return result
            logger.warning(f"⚠️ [{label} RETRY] Boş yanıt, deneme {attempt+1}/2")
        except Exception as e:
            logger.warning(f"⚠️ [{label} RETRY] Hata: {e} (deneme {attempt+1}/2)")

        if attempt < 1:
            wait = delays[0]
            logger.info(f"⏳ [{label} RETRY] {wait}s bekleniyor...")
            time.sleep(wait)

    logger.error(f"❌ [{label} RETRY] Tüm denemeler başarısız!")
    return None


def is_similar(text1: str, text2: str, threshold: float = 0.7) -> bool:
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio() > threshold

def deduplicate_news(news_list: List[str]) -> List[str]:
    unique_news = []
    for news in news_list:
        is_duplicate = any(is_similar(news, existing, 0.7) for existing in unique_news)
        if not is_duplicate:
            unique_news.append(news)
    logger.info(f"🧹 [DEDUP] {len(news_list)} → {len(unique_news)} benzersiz haber")
    return unique_news

def get_previously_shown_news() -> List[str]:
    return get_cache("news:shown_history") or []

def save_shown_news(news_list: List[str]):
    existing = get_cache("news:shown_history") or []
    unique   = list(set(existing + news_list))
    unique   = unique[-100:]
    set_cache("news:shown_history", unique, ttl=86400)

def filter_already_shown(news_list: List[str]) -> List[str]:
    shown_before = get_previously_shown_news()
    if not shown_before:
        return news_list
    filtered = [
        news for news in news_list
        if not any(is_similar(news, old, 0.8) for old in shown_before)
    ]
    logger.info(f"🧹 [VARDIYA DEDUP] {len(news_list)} → {len(filtered)} yeni haber")
    return filtered

def fetch_with_retry(url: str, max_retries: int = 3, timeout: int = 10) -> Optional[Dict]:
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            wait_time = 2 ** attempt
            logger.warning(f"⚠️ [RETRY] Deneme {attempt + 1}/{max_retries} başarısız. {wait_time}s bekleniyor...")
            if attempt < max_retries - 1:
                time.sleep(wait_time)
            else:
                logger.error(f"❌ [FETCH] Tüm denemeler başarısız: {e}")
                return None
    return None

def fetch_gnews(max_results: int = 30) -> List[str]:
    try:
        if not GNEWS_API_KEY:
            return []
        three_days_ago = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%dT%H:%M:%SZ')
        url = (
            f"https://gnews.io/api/v4/search"
            f"?q=(\"merkez bankası\" OR \"faiz kararı\" OR \"faiz\" OR \"enflasyon\" OR \"TCMB\" OR \"FED\" OR \"ECB\" OR \"büyüme\" OR \"GSYİH\")"
            f"&lang=tr&country=tr&from={three_days_ago}&sortby=publishedAt&max={max_results}&apikey={GNEWS_API_KEY}"
        )
        data = fetch_with_retry(url)
        if not data or data.get('totalArticles', 0) == 0:
            return []
        news_list = []
        for article in data.get('articles', [])[:max_results]:
            title       = article.get('title', '').strip()
            description = article.get('description', '').strip()
            pub_date    = article.get('publishedAt', '')
            full_text   = f"{title}. {description}" if description else title
            if full_text and len(full_text) > 15:
                news_list.append(f"{full_text} [Tarih: {pub_date}]")
        logger.info(f"✅ [GNEWS] {len(news_list)} haber alındı")
        return news_list
    except Exception as e:
        logger.error(f"❌ [GNEWS] Hata: {e}")
        return []

def fetch_newsdata(max_results: int = 40) -> List[str]:
    try:
        if not NEWSDATA_API_KEY:
            return []
        url = (
            f"https://newsdata.io/api/1/news"
            f"?apikey={NEWSDATA_API_KEY}&country=tr&language=tr&category=business"
            f"&q=(merkez AND bankası) OR faiz OR TCMB OR FED OR ECB OR enflasyon OR büyüme"
        )
        data = fetch_with_retry(url)
        if not data or data.get('status') != 'success':
            return []
        news_list = []
        for article in data.get('results', [])[:max_results]:
            title = article.get('title')
            if title is None:
                continue
            title       = title.strip()
            description = article.get('description')
            pub_date    = article.get('pubDate', '')
            full_text   = f"{title}. {description.strip()}" if description else title
            if full_text and len(full_text) > 15:
                news_list.append(f"{full_text} [Tarih: {pub_date}]")
        logger.info(f"✅ [NEWSDATA] {len(news_list)} haber alındı")
        return news_list
    except Exception as e:
        logger.error(f"❌ [NEWSDATA] Hata: {e}")
        return []

def fetch_all_news() -> List[str]:
    logger.info("📰 [NEWS] Haber toplama başlıyor...")
    gnews_list    = fetch_gnews(max_results=Config.NEWS_MAX_RESULTS_PER_SOURCE)
    newsdata_list = fetch_newsdata(max_results=Config.NEWS_MAX_RESULTS_PER_SOURCE)
    all_news      = gnews_list + newsdata_list
    unique_news   = deduplicate_news(all_news)
    logger.info(f"✅ [NEWS] Toplam {len(unique_news)} benzersiz haber toplandı")
    return unique_news

def summarize_news_batch(news_list: List[str]) -> Tuple[List[str], Optional[str], Optional[object]]:
    """
    Haberleri Gemini ile filtreler. Bayram tespiti artık Gemini'ye bırakılmaz,
    sabit takvimden (get_today_holiday) alınır.
    """
    try:
        if not GEMINI_API_KEY or not news_list:
            return [], None, None

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-3-flash-preview')

        numbered_news = '\n'.join([f"{i+1}. {news}" for i, news in enumerate(news_list)])
        today         = datetime.now().strftime('%d %B %Y, %A')
        current_time  = datetime.now().strftime('%H:%M')
        two_days_ago  = (datetime.now() - timedelta(days=2)).strftime('%d %B %Y')

        holiday = get_today_holiday()
        if holiday:
            bayram_name, bayram_emoji, bayram_end_date = holiday
            bayram_msg = f"{bayram_emoji} {bayram_name}".strip()
            logger.info(f"📅 [BAYRAM TAKVİM] Bugün bayram: {bayram_msg} (Bitiş: {bayram_end_date})")
        else:
            bayram_msg      = None
            bayram_end_date = None

        prompt = f"""
SEN BİR FİNANS EDİTÖRÜSÜN. Sadece PİYASAYI ETKİLEYEN kritik haberleri seç.

BUGÜN: {today}, SAAT: {current_time}

⚠️ ÖNEMLİ TARİH FİLTRESİ:
- Haberlerin sonunda [Tarih: ...] etiketi var
- SADECE SON 48 SAAT İÇİNDEKİ ({two_days_ago} - {today}) HABERLERİ AL
- 2025 yılından haberler → KESINLIKLE ATLA
- 3+ gün önceki haberler → ATLA

═══════════════════════════════════════════
GÖREV - ULTRA SIKI FİLTRE + TARİH KONTROLÜ
═══════════════════════════════════════════

✅ SADECE ŞU TİP HABERLERİ AL:

1. MERKEZ BANKASI KARARLARI
2. KRİTİK EKONOMİK VERİ AÇIKLAMALARI
3. DÖVIZ/ALTIN REKORLARI
4. BORSA KRİTİK HAREKETLER
5. GEOPOLİTİK ŞOKLAR
6. YASAL DEĞİŞİKLİKLER

❌ BUNLARI ASLA ALMA:
- Genel yorumlar, BES/emeklilik, şirket kâr/zarar, banka kampanyaları
- Teknik analiz, kripto, eski tarihli haberler

═══════════════════════════════════════════
YAZIM KURALLARI
═══════════════════════════════════════════
🔥 SAAT: "21:00'de", "10:00'da" (kesme işareti OLMALI!)
🔥 RAKAM: "%64.77", "45.50 TL"
🔥 BÜYÜK: FED, TCMB, ECB, BIST, TL, USD, EUR

═══════════════════════════════════════════
HAM HABERLER ({len(news_list)} adet):
═══════════════════════════════════════════
{numbered_news}

═══════════════════════════════════════════
ÇIKTI FORMATI (SADECE HABERLER, BAYRAM SATIRI YOK):
═══════════════════════════════════════════
1. [Tam anlaşılır özet - Max 15 kelime]
2. [Tam anlaşılır özet - Max 15 kelime]

❌ HİÇBİR kritik haber yoksa: "HABER: YOK"
"""

        logger.info(f"🤖 [GEMİNİ] {len(news_list)} haber filtreleniyor...")

        result = _call_gemini_with_retry(model, prompt, label="GEMİNİ HABER")
        if not result:
            logger.error("❌ [GEMİNİ HABER] Tüm denemeler başarısız!")
            return [], bayram_msg, bayram_end_date

        summaries = []
        for line in result.split('\n'):
            clean_line = line.strip()
            if not clean_line:
                continue
            if "HABER:" in clean_line.upper() and "YOK" in clean_line.upper():
                break
            if '. ' in clean_line:
                parts = clean_line.split('. ', 1)
                if len(parts) > 1:
                    clean_line = parts[1]
            if clean_line and len(clean_line) > 10:
                summaries.append(clean_line)

        logger.info(f"✅ [GEMİNİ] {len(summaries)} kritik haber filtrelendi")
        return summaries, bayram_msg, bayram_end_date

    except Exception as e:
        logger.error(f"❌ [GEMİNİ] Hata: {e}")
        return [], None, None


def fetch_harem_prices() -> Optional[Dict[str, Dict[str, float]]]:
    try:
        url     = Config.HAREM_PRICE_URL
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=Config.HAREM_FETCH_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        prices = {}
        rows   = soup.find_all('tr')
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 2:
                continue
            name = cells[0].get_text(strip=True).lower()
            if 'eski' in name:
                continue
            code = None
            for key, val in _HAREM_PRODUCT_MAP.items():
                if key in name:
                    code = val
                    break
            if not code:
                continue
            min_price = _GOLD_MIN_PRICE.get(code, 1.0)
            nums = []
            for cell in cells[1:]:
                txt = cell.get_text(strip=True).replace('.', '').replace(',', '.').replace('₺', '').replace(' ', '')
                try:
                    v = float(txt)
                    if v >= min_price:
                        nums.append(v)
                except ValueError:
                    continue
            if len(nums) >= 2:
                prices[code] = {'buying': nums[0], 'selling': nums[1]}
            elif len(nums) == 1:
                prices[code] = {'buying': nums[0], 'selling': nums[0]}

        if not prices:
            logger.error("❌ [HAREM PARSE] Hiç fiyat parse edilemedi")
            return None

        logger.info(f"✅ [HAREM PARSE] {len(prices)} ürün parse edildi: {list(prices.keys())}")
        return prices

    except Exception as e:
        logger.error(f"❌ [HAREM PARSE] Hata: {e}")
        return None


def fetch_harem_html() -> Optional[str]:
    prices = fetch_harem_prices()
    if prices:
        lines = []
        for code, p in prices.items():
            lines.append(f"{code}: Alış={p['buying']:.2f} Satış={p['selling']:.2f}")
        result = "\n".join(lines)
        logger.info(f"✅ [HAREM HTML] {len(prices)} ürün → {len(result)} karakter")
        return result

    try:
        url     = Config.HAREM_PRICE_URL
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=Config.HAREM_FETCH_TIMEOUT)
        response.raise_for_status()
        soup  = BeautifulSoup(response.content, 'html.parser')
        table = soup.find('table') or soup.find_all('div', class_='data')
        if table:
            html_text = str(table)[:3000]
            logger.warning(f"⚠️ [HAREM HTML] Parse başarısız, raw HTML fallback: {len(html_text)} karakter")
            return html_text
        return None
    except Exception as e:
        logger.error(f"❌ [HAREM HTML] Fallback hata: {e}")
        return None


def fetch_ziraat_prices() -> Optional[Dict[str, Dict[str, float]]]:
    try:
        url     = Config.ZIRAAT_CURRENCY_URL
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=Config.ZIRAAT_FETCH_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        prices = {}
        rows   = soup.find_all('tr')
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 2:
                continue
            name = cells[0].get_text(strip=True).lower()
            code = None
            for key, val in _ZIRAAT_CURRENCY_MAP.items():
                if key in name:
                    code = val
                    break
            if not code:
                continue
            if code in prices:
                continue
            nums = []
            for cell in cells[1:]:
                raw_txt = cell.get_text(strip=True)
                if ':' in raw_txt:
                    continue
                if raw_txt.startswith('%'):
                    continue
                txt = raw_txt.replace(',', '.').replace(' ', '')
                try:
                    v = float(txt)
                    if 0.001 < v < 10000:
                        nums.append(v)
                except ValueError:
                    continue
            if len(nums) >= 2:
                prices[code] = {'buying': nums[0], 'selling': nums[1]}
            elif len(nums) == 1:
                prices[code] = {'buying': nums[0], 'selling': nums[0]}

        if not prices:
            logger.error("❌ [ZİRAAT PARSE] Hiç fiyat parse edilemedi")
            return None

        logger.info(f"✅ [ZİRAAT PARSE] {len(prices)} döviz parse edildi: {list(prices.keys())}")
        return prices

    except Exception as e:
        logger.error(f"❌ [ZİRAAT PARSE] Hata: {e}")
        return None


def fetch_ziraat_html() -> Optional[str]:
    prices = fetch_ziraat_prices()
    if prices:
        lines = []
        for code, p in prices.items():
            lines.append(f"{code}: Alış={p['buying']:.4f} Satış={p['selling']:.4f}")
        result = "\n".join(lines)
        logger.info(f"✅ [ZİRAAT HTML] {len(prices)} döviz → {len(result)} karakter")
        return result

    try:
        url     = Config.ZIRAAT_CURRENCY_URL
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=Config.ZIRAAT_FETCH_TIMEOUT)
        response.raise_for_status()
        html_text = response.text[:5000]
        logger.warning(f"⚠️ [ZİRAAT HTML] Parse başarısız, raw HTML fallback: {len(html_text)} karakter")
        return html_text
    except Exception as e:
        logger.error(f"❌ [ZİRAAT HTML] Fallback hata: {e}")
        return None


def calculate_all_margins_direct(
    harem_prices: Optional[Dict],
    ziraat_prices: Optional[Dict],
    api_rates: Dict,
    old_margins: Dict = None
) -> Optional[Dict]:
    old_margins = old_margins or {}
    margins     = {}
    rates       = api_rates.get('Rates', api_rates)

    if harem_prices:
        for code, api_key in _GOLD_API_MAPPING.items():
            harem = harem_prices.get(code)
            if not harem:
                logger.warning(f"⚠️ [DİREKT MARJ] {code}: Harem verisi yok → atlandı")
                continue

            harem_selling = harem.get('selling', 0)
            if harem_selling == 0:
                logger.warning(f"⚠️ [DİREKT MARJ] {code}: Harem satış sıfır → atlandı")
                continue

            api_entry   = rates.get(api_key, {})
            api_selling = api_entry.get('Selling', 0)
            if not api_selling or api_selling == 0:
                logger.warning(f"⚠️ [DİREKT MARJ] {code}: API verisi yok → atlandı")
                continue

            margin = (harem_selling - api_selling) / api_selling
            logger.info(
                f"  ✅ [DİREKT MARJ] {code}: "
                f"Harem={harem_selling:.2f} API={api_selling:.2f} "
                f"→ %{margin*100:.3f}"
            )

            if _validate_margin(code, margin):
                margins[code] = round(margin, 6)
            else:
                if code in old_margins:
                    margins[code] = old_margins[code]
                    logger.warning(
                        f"  ⚠️ [DİREKT MARJ] {code}: geçersiz ({margin:.4f}), "
                        f"eski marj korundu: {old_margins[code]:.4f}"
                    )

        if 'AG' in margins:
            margins['GUMUS'] = margins['AG']
            logger.debug(f"🔄 [DİREKT MARJ] GUMUS = AG: {margins['AG']:.4f}")
    else:
        logger.warning("⚠️ [DİREKT MARJ] Harem verisi yok, altın marjları hesaplanamadı")

    if ziraat_prices:
        for code in _CURRENCY_API_KEYS:
            ziraat      = ziraat_prices.get(code)
            api_entry   = rates.get(code, {})
            api_selling = api_entry.get('Selling', 0)

            if not ziraat or not api_selling or api_selling == 0:
                logger.warning(f"⚠️ [DİREKT MARJ] {code}: veri eksik → atlandı")
                continue

            ziraat_selling = ziraat.get('selling', 0)
            if ziraat_selling == 0:
                logger.warning(f"⚠️ [DİREKT MARJ] {code}: Ziraat satış sıfır → atlandı")
                continue

            margin = (ziraat_selling - api_selling) / api_selling

            if _validate_margin(code, margin):
                margins[code] = round(margin, 6)
                logger.info(
                    f"  ✅ [DİREKT MARJ] {code}: "
                    f"Ziraat={ziraat_selling:.4f} API={api_selling:.4f} "
                    f"→ %{margin*100:.3f}"
                )
            else:
                if code in old_margins:
                    margins[code] = old_margins[code]
                    logger.warning(
                        f"  ⚠️ [DİREKT MARJ] {code}: geçersiz ({margin:.4f}), "
                        f"eski marj korundu: {old_margins[code]:.4f}"
                    )
    else:
        logger.warning("⚠️ [DİREKT MARJ] Ziraat verisi yok, döviz marjları hesaplanamadı")

    if not margins:
        logger.error("❌ [DİREKT MARJ] Hiç marj hesaplanamadı!")
        return None

    gold_keys     = [k for k in margins if k in _GOLD_API_MAPPING or k == 'GUMUS']
    currency_keys = [k for k in margins if k in _CURRENCY_API_KEYS]
    logger.info(
        f"✅ [DİREKT MARJ] Toplam {len(margins)} marj hesaplandı: "
        f"ALTIN={gold_keys}, DÖVİZ={currency_keys}"
    )
    return margins


def calculate_all_margins_with_gemini(
    harem_html: str,
    ziraat_html: str,
    gold_api_prices: Dict,
    currency_api_prices: Dict,
    old_margins: Dict = None
) -> Optional[Dict]:
    logger.warning("⚠️ [COMPAT] calculate_all_margins_with_gemini çağrıldı → direkt hesaplamaya yönlendiriliyor")
    try:
        harem_prices  = fetch_harem_prices()
        ziraat_prices = fetch_ziraat_prices()
        from services.financial_service import fetch_from_v5
        api_data = fetch_from_v5()
        if not api_data:
            logger.error("❌ [COMPAT] API verisi alınamadı")
            return None
        return calculate_all_margins_direct(harem_prices, ziraat_prices, api_data, old_margins)
    except Exception as e:
        logger.error(f"❌ [COMPAT] Yönlendirme hatası: {e}")
        return None


def calculate_full_margins_with_gemini(html_data: str, api_prices: Dict, old_margins: Dict = None) -> Optional[Dict]:
    logger.warning("⚠️ [COMPAT] calculate_full_margins_with_gemini çağrıldı, yeni fonksiyona yönlendiriliyor.")
    return None


def calculate_currency_margins_with_gemini(html_data: str, api_prices: Dict, old_margins: Dict = None) -> Optional[Dict]:
    logger.warning("⚠️ [COMPAT] calculate_currency_margins_with_gemini çağrıldı, yeni fonksiyona yönlendiriliyor.")
    return None


def async_margin_bootstrap():
    global _margin_bootstrap_in_progress
    try:
        logger.info("🔄 [ASYNC MARJ] Arka planda başlatıldı...")
        success = update_dynamic_margins()
        if success:
            logger.info("✅ [ASYNC MARJ] Tamamlandı!")
        else:
            logger.warning("⚠️ [ASYNC MARJ] Güncelleme başarısız")
    except Exception as e:
        logger.error(f"❌ [ASYNC MARJ] Hata: {e}")
    finally:
        with _margin_bootstrap_lock:
            _margin_bootstrap_in_progress = False


def update_dynamic_margins() -> bool:
    try:
        logger.info("💰 [DİREKT MARJ] Güncelleme başlıyor...")

        harem_prices  = fetch_harem_prices()
        ziraat_prices = fetch_ziraat_prices()

        try:
            from services.financial_service import fetch_from_v5
            api_data = fetch_from_v5()
            if not api_data or 'Rates' not in api_data:
                logger.error("❌ [DİREKT MARJ] API verisi alınamadı!")
                return False
        except Exception as api_error:
            logger.error(f"❌ [DİREKT MARJ] API çağrısı başarısız: {api_error}")
            return False

        old_margins = get_cache(Config.CACHE_KEYS.get('dynamic_margins', 'dynamic:margins')) or {}

        computed_margins = calculate_all_margins_direct(
            harem_prices, ziraat_prices, api_data, old_margins=old_margins
        ) or {}

        exotic_margins      = getattr(Config, 'STATIC_EXOTIC_MARGINS', {})
        gold_static_margins = getattr(Config, 'STATIC_GOLD_MARGINS', {})

        all_new_margins = {**computed_margins, **exotic_margins, **gold_static_margins}

        if not all_new_margins:
            logger.warning("⚠️ [DİREKT MARJ] Hiç marj hesaplanamadı!")
            return False

        logger.info(
            f"📊 [DİREKT MARJ] Toplam: {len(all_new_margins)} marj "
            f"(HESAPLANAN:{len(computed_margins)} + EXOTIC:{len(exotic_margins)} + GOLD_STATIC:{len(gold_static_margins)})"
        )

        threshold      = Config.MARGIN_SMOOTH_THRESHOLD
        smooth_margins = dict(old_margins)

        for key, new_val in all_new_margins.items():
            if key in exotic_margins or key in gold_static_margins:
                smooth_margins[key] = new_val
                continue
            old_val = old_margins.get(key, new_val)
            diff    = abs(new_val - old_val)
            if diff > threshold and Config.MARGIN_SMOOTH_TRANSITION:
                smooth_margins[key] = round((old_val + new_val) / 2, 4)
            else:
                smooth_margins[key] = new_val

        fallback_applied = []
        for key, fallback_val in _FALLBACK_GOLD_MARGINS.items():
            if key not in smooth_margins or smooth_margins.get(key, 0) == 0:
                if key in old_margins and old_margins[key] > 0:
                    smooth_margins[key] = old_margins[key]
                    logger.warning(f"⚠️ [FALLBACK] {key} → eski marj kullanıldı: {old_margins[key]:.4f}")
                else:
                    smooth_margins[key] = fallback_val
                    logger.warning(f"⚠️ [FALLBACK] {key} → sabit fallback: {fallback_val:.4f}")
                fallback_applied.append(key)

        if fallback_applied:
            logger.warning(f"⚠️ [FALLBACK] Eksik marjlar dolduruldu: {fallback_applied}")
        else:
            logger.info("✅ [FALLBACK] Tüm marjlar mevcut, fallback gerekmedi")

        margin_key = Config.CACHE_KEYS.get('dynamic_margins', 'dynamic:margins')
        set_cache(margin_key, smooth_margins, ttl=86400)

        update_key = Config.CACHE_KEYS.get('margin_last_update', 'margin:last_update')
        set_cache(update_key, {'timestamp': time.time(), 'margins': smooth_margins}, ttl=0)

        logger.info(f"✅ [DİREKT MARJ] Kaydedildi: {len(smooth_margins)} marj")
        return True

    except Exception as e:
        logger.error(f"❌ [DİREKT MARJ] Hata: {e}")
        return False


def get_dynamic_margins() -> Dict[str, float]:
    global _margin_bootstrap_in_progress

    dynamic_margins = get_cache(Config.CACHE_KEYS.get('dynamic_margins', 'dynamic:margins'))
    if dynamic_margins and isinstance(dynamic_margins, dict):
        return dynamic_margins

    last_successful_key = Config.CACHE_KEYS.get('margin_last_update', 'margin:last_update')
    last_successful     = get_cache(last_successful_key)

    if last_successful and isinstance(last_successful, dict):
        margins   = last_successful.get('margins')
        timestamp = last_successful.get('timestamp', 0)

        if margins and isinstance(margins, dict):
            days_ago = (time.time() - timestamp) / 86400

            if days_ago > 1.0:
                with _margin_bootstrap_lock:
                    if not _margin_bootstrap_in_progress:
                        _margin_bootstrap_in_progress = True
                        logger.warning(f"⚠️ [DİREKT MARJ] {days_ago:.1f} gün önce! ASYNC Bootstrap başlatılıyor...")
                        thread = threading.Thread(target=async_margin_bootstrap, daemon=True)
                        thread.start()

            return margins

    logger.error("🔴 [DİREKT MARJ BOOTSTRAP] Marj yok! Hesaplanıyor...")
    bootstrap_success = update_dynamic_margins()

    if bootstrap_success:
        fresh_margins = get_cache(Config.CACHE_KEYS.get('dynamic_margins', 'dynamic:margins'))
        if fresh_margins:
            logger.info("✅ [DİREKT MARJ BOOTSTRAP] Başarılı!")
            return fresh_margins

    logger.critical(
        "💣 [DİREKT MARJ BOOTSTRAP] Hesaplama başarısız! "
        "SABIT FALLBACK MARJLAR kullanılıyor."
    )
    return _get_config_fallback_margins()


def plan_shift_schedule(news_list: List[str], start_hour: int, end_hour: int) -> List[Dict]:
    if not news_list:
        return []

    total_duration_minutes = (end_hour - start_hour) * 60
    news_count             = len(news_list)
    duration_per_news      = total_duration_minutes // news_count

    schedule     = []
    current_time = datetime.now().replace(hour=start_hour, minute=0, second=0, microsecond=0)

    for i, news in enumerate(news_list):
        start_str = current_time.strftime("%H:%M")
        if i == news_count - 1:
            end_time = current_time.replace(hour=23, minute=59) if end_hour == 24 else current_time.replace(hour=end_hour, minute=0)
        else:
            end_time = current_time + timedelta(minutes=duration_per_news)
        end_str = end_time.strftime("%H:%M")
        schedule.append({"start": start_str, "end": end_str, "text": news})
        current_time = end_time

    return schedule


def calculate_bayram_ttl(end_date=None) -> int:
    now = datetime.now()
    if end_date:
        try:
            if isinstance(end_date, str):
                end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            expire_dt = datetime.combine(end_date, datetime.min.time()).replace(hour=15, minute=0, second=0)
            ttl = int((expire_dt - now).total_seconds())
            if ttl > 0:
                return ttl
        except Exception:
            pass
    tomorrow_3am = (now + timedelta(days=1)).replace(hour=3, minute=0, second=0, microsecond=0)
    return int((tomorrow_3am - now).total_seconds())


def _set_bayram_cache(bayram_msg: str, bayram_end_date=None):
    bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
    if not get_cache(bayram_key):
        ttl = calculate_bayram_ttl(bayram_end_date)
        set_cache(bayram_key, bayram_msg, ttl=ttl)
        logger.info(f"🌙 [BAYRAM CACHE] Yazıldı: {bayram_msg} (TTL: {ttl}s)")
    else:
        logger.debug("🌙 [BAYRAM CACHE] Zaten mevcut, üzerine yazılmadı")


def prepare_morning_news() -> bool:
    try:
        news_list  = fetch_all_news()
        fresh_news = filter_already_shown(news_list) if news_list else []
        result     = summarize_news_batch(fresh_news) if fresh_news else ([], None, None)
        summaries, bayram_msg, bayram_end_date = result
        pending_key = Config.CACHE_KEYS.get('news_morning_pending', 'news:morning_pending')
        set_cache(pending_key, {
            'summaries':       summaries,
            'bayram':          bayram_msg,
            'bayram_end_date': str(bayram_end_date) if bayram_end_date else None
        }, ttl=600)
        logger.info(f"✅ [SABAH HAZIRLIK] {len(summaries)} haber hazırlandı")
        return True
    except Exception as e:
        logger.error(f"❌ [SABAH HAZIRLIK] Hata: {e}")
        return False

def publish_morning_news() -> bool:
    try:
        logger.info("🌅 [SABAH YAYINLA] Hazır haberler yayınlanıyor...")
        pending_key  = Config.CACHE_KEYS.get('news_morning_pending', 'news:morning_pending')
        pending_data = get_cache(pending_key)
        if not pending_data:
            logger.error("❌ [SABAH YAYINLA] PENDING verisi yok!")
            return False

        summaries       = pending_data.get('summaries', [])
        bayram_msg      = pending_data.get('bayram')
        bayram_end_date = pending_data.get('bayram_end_date')

        if bayram_msg:
            _set_bayram_cache(bayram_msg, bayram_end_date)

        cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
        if summaries:
            schedule = plan_shift_schedule(summaries, start_hour=0, end_hour=12)
            set_cache(cache_key, schedule, ttl=43200)
            save_shown_news(summaries)
            logger.info(f"✅ [SABAH YAYINLA] {len(schedule)} haber yayınlandı")
        else:
            set_cache(cache_key, [], ttl=43200)

        delete_cache(pending_key)
        update_key = Config.CACHE_KEYS.get('news_last_update', 'news:last_update')
        set_cache(update_key, {
            'shift':      'morning',
            'timestamp':  time.time(),
            'news_count': len(summaries),
            'bayram':     bayram_msg or 'yok'
        }, ttl=86400)
        return True
    except Exception as e:
        logger.error(f"❌ [SABAH YAYINLA] Hata: {e}")
        return False

def prepare_evening_news() -> bool:
    try:
        news_list  = fetch_all_news()
        fresh_news = filter_already_shown(news_list) if news_list else []
        result     = summarize_news_batch(fresh_news) if fresh_news else ([], None, None)
        summaries, bayram_msg, bayram_end_date = result
        pending_key = Config.CACHE_KEYS.get('news_evening_pending', 'news:evening_pending')
        set_cache(pending_key, {
            'summaries':       summaries,
            'bayram':          bayram_msg,
            'bayram_end_date': str(bayram_end_date) if bayram_end_date else None
        }, ttl=600)
        logger.info(f"✅ [AKŞAM HAZIRLIK] {len(summaries)} haber hazırlandı")
        return True
    except Exception as e:
        logger.error(f"❌ [AKŞAM HAZIRLIK] Hata: {e}")
        return False

def publish_evening_news() -> bool:
    try:
        logger.info("🌆 [AKŞAM YAYINLA] Hazır haberler yayınlanıyor...")
        pending_key  = Config.CACHE_KEYS.get('news_evening_pending', 'news:evening_pending')
        pending_data = get_cache(pending_key)
        if not pending_data:
            logger.error("❌ [AKŞAM YAYINLA] PENDING verisi yok!")
            return False

        summaries       = pending_data.get('summaries', [])
        bayram_msg      = pending_data.get('bayram')
        bayram_end_date = pending_data.get('bayram_end_date')

        if bayram_msg:
            _set_bayram_cache(bayram_msg, bayram_end_date)

        cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
        if summaries:
            schedule = plan_shift_schedule(summaries, start_hour=12, end_hour=24)
            set_cache(cache_key, schedule, ttl=43200)
            save_shown_news(summaries)
            logger.info(f"✅ [AKŞAM YAYINLA] {len(schedule)} haber yayınlandı")
        else:
            set_cache(cache_key, [], ttl=43200)

        delete_cache(pending_key)
        update_key = Config.CACHE_KEYS.get('news_last_update', 'news:last_update')
        set_cache(update_key, {
            'shift':      'evening',
            'timestamp':  time.time(),
            'news_count': len(summaries),
            'bayram':     bayram_msg or 'yok'
        }, ttl=86400)
        return True
    except Exception as e:
        logger.error(f"❌ [AKŞAM YAYINLA] Hata: {e}")
        return False

def bootstrap_news_system() -> bool:
    global _bootstrap_last_attempt
    try:
        current_hour = datetime.now().hour
        if 0 <= current_hour < 12:
            cache_key  = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
            shift_name = "SABAH"
            shift_type = "morning"
        else:
            cache_key  = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
            shift_name = "AKŞAM"
            shift_type = "evening"

        now          = time.time()
        last_attempt = _bootstrap_last_attempt[shift_type]
        if last_attempt > 0 and (now - last_attempt) < _bootstrap_cooldown:
            remaining = int(_bootstrap_cooldown - (now - last_attempt))
            logger.debug(f"⏳ [BOOTSTRAP] {shift_name} cooldown: {remaining}s kaldı")
            return False

        with _bootstrap_lock:
            if _bootstrap_in_progress[shift_type]:
                return False
            existing_data = get_cache(cache_key)
            if existing_data is not None and len(existing_data) > 0:
                return False
            _bootstrap_in_progress[shift_type] = True
            logger.warning(f"⚠️ [BOOTSTRAP] {shift_name} vardiyası boş! Doldurma başlıyor...")

        try:
            if shift_type == 'morning':
                success = prepare_morning_news() and publish_morning_news()
            else:
                success = prepare_evening_news() and publish_evening_news()

            _bootstrap_last_attempt[shift_type] = now
            if success:
                logger.info(f"🚀 [BOOTSTRAP] {shift_name} başarılı!")
            else:
                logger.warning(f"❌ [BOOTSTRAP] {shift_name} başarısız! {_bootstrap_cooldown}s bekleme başladı")
            return success
        finally:
            with _bootstrap_lock:
                _bootstrap_in_progress[shift_type] = False

    except Exception as e:
        logger.error(f"❌ [BOOTSTRAP] Hata: {e}")
        try:
            with _bootstrap_lock:
                if 0 <= datetime.now().hour < 12:
                    _bootstrap_in_progress['morning'] = False
                else:
                    _bootstrap_in_progress['evening'] = False
        except Exception:
            pass
        return False

def get_current_news_banner() -> Optional[str]:
    global _last_logged_banner
    try:
        current_hour = datetime.now().hour
        current_time = datetime.now().strftime("%H:%M")

        if 0 <= current_hour < 12:
            cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
        else:
            cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')

        schedule = get_cache(cache_key)
        if schedule is None:
            bootstrap_news_system()
            schedule = get_cache(cache_key)

        if not schedule or len(schedule) == 0:
            return None

        for news_slot in schedule:
            if news_slot['start'] <= current_time < news_slot['end']:
                banner_msg = f"📰 {news_slot['text']}"
                if _last_logged_banner != banner_msg:
                    logger.info(f"📰 [BANNER] Değişti: {banner_msg[:50]}...")
                    _last_logged_banner = banner_msg
                return banner_msg

        return None

    except Exception as e:
        logger.error(f"❌ [BANNER] Hata: {e}")
        return None

def test_news_manager():
    print("🧪 News Manager Test\n")

    print("0️⃣ BAYRAM TAKVİM KONTROLÜ:")
    holiday = get_today_holiday()
    if holiday:
        msg, emoji, end = holiday
        print(f"   🎉 Bugün bayram: {emoji} {msg} (Bitiş: {end})\n")
    else:
        print("   ℹ️ Bugün bayram yok\n")

    print("1️⃣ HABER TOPLAMA:")
    news_list = fetch_all_news()
    print(f"   ✅ {len(news_list)} haber toplandı\n")

    if news_list:
        print("   İlk 3 haber:")
        for i, news in enumerate(news_list[:3], 1):
            print(f"   {i}. {news[:120]}...")
        print()

    fresh_news = []
    if news_list:
        print("2️⃣ VARDIYALAR ARASI DEDUP:")
        fresh_news = filter_already_shown(news_list)
        print(f"   ✅ {len(fresh_news)} yeni haber\n")

    if fresh_news:
        print("3️⃣ GEMINI FİLTRE (SADECE HABERLER İÇİN):")
        summaries, bayram_msg, bayram_end_date = summarize_news_batch(fresh_news)
        print(f"   ✅ {len(summaries)} kritik haber\n")
        if bayram_msg:
            print(f"   🌙 BAYRAM (TAKVİMDEN): {bayram_msg} (Bitiş: {bayram_end_date})\n")
        if summaries:
            print("   Kritik haberler:")
            for i, summary in enumerate(summaries, 1):
                print(f"   {i}. {summary}")
        print()

    print("4️⃣ DİREKT MARJ HESAPLAMA:")
    margins = get_dynamic_margins()
    print(f"   ✅ {len(margins)} marj hesaplandı!\n")
    if margins:
        print(f"   İlk 10 marj: {dict(list(margins.items())[:10])}\n")

    print("5️⃣ BOOTSTRAP:")
    bootstrap_success = bootstrap_news_system()
    print(f"   {'✅ Başarılı' if bootstrap_success else 'ℹ️ Gerek yok veya cooldown'}\n")

    print("6️⃣ BANNER:")
    banner = get_current_news_banner()
    if banner:
        print(f"   ✅ {banner}\n")
    else:
        print("   ℹ️ Haber yok\n")

if __name__ == "__main__":
    test_news_manager()
