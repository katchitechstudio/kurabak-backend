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

_FALLBACK_GOLD_MARGINS = {
    'GRA':   0.030,
    'C22':   0.025,
    'YAR':   0.025,
    'TAM':   0.020,
    'CUM':   0.015,
    'ATA':   0.017,
    'HAS':   0.010,
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

# ✅ Ziraat gerçek spread'i %2-4 arası → validation genişletildi
_MARGIN_VALID_RANGES = {
    'GRA':   (0.008, 0.080),
    'C22':   (0.010, 0.060),
    'YAR':   (0.008, 0.060),
    'TAM':   (0.004, 0.060),
    'CUM':   (0.008, 0.060),
    'ATA':   (0.008, 0.060),
    'HAS':   (0.004, 0.040),
    'AG':    (0.020, 0.120),
    'GUMUS': (0.020, 0.120),
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
    gold = getattr(Config, 'DEFAULT_GOLD_MARGINS', _FALLBACK_GOLD_MARGINS)
    currency = getattr(Config, 'DEFAULT_CURRENCY_MARGINS', _FALLBACK_CURRENCY_MARGINS)
    exotic = getattr(Config, 'STATIC_EXOTIC_MARGINS', {})
    return {**_FALLBACK_GOLD_MARGINS, **_FALLBACK_CURRENCY_MARGINS, **gold, **currency, **exotic}


# ✅ DEĞİŞTİ: 3 deneme → 2 deneme, bekleme 300/900s → 60s
def _call_gemini_with_retry(model, prompt: str, label: str = "GEMİNİ") -> Optional[str]:
    delays = [60]  # Sadece 1 kez 60s bekle, sonra bırak
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
    unique = list(set(existing + news_list))
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
            title = article.get('title', '').strip()
            description = article.get('description', '').strip()
            pub_date = article.get('publishedAt', '')
            full_text = f"{title}. {description}" if description else title
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
            title = title.strip()
            description = article.get('description')
            pub_date = article.get('pubDate', '')
            full_text = f"{title}. {description.strip()}" if description else title
            if full_text and len(full_text) > 15:
                news_list.append(f"{full_text} [Tarih: {pub_date}]")
        logger.info(f"✅ [NEWSDATA] {len(news_list)} haber alındı")
        return news_list
    except Exception as e:
        logger.error(f"❌ [NEWSDATA] Hata: {e}")
        return []

def fetch_all_news() -> List[str]:
    logger.info("📰 [NEWS] Haber toplama başlıyor...")
    gnews_list = fetch_gnews(max_results=Config.NEWS_MAX_RESULTS_PER_SOURCE)
    newsdata_list = fetch_newsdata(max_results=Config.NEWS_MAX_RESULTS_PER_SOURCE)
    all_news = gnews_list + newsdata_list
    unique_news = deduplicate_news(all_news)
    logger.info(f"✅ [NEWS] Toplam {len(unique_news)} benzersiz haber toplandı")
    return unique_news

def summarize_news_batch(news_list: List[str]) -> Tuple[List[str], Optional[str]]:
    try:
        if not GEMINI_API_KEY or not news_list:
            return [], None

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-3-flash-preview')

        numbered_news = '\n'.join([f"{i+1}. {news}" for i, news in enumerate(news_list)])
        today = datetime.now().strftime('%d %B %Y, %A')
        current_time = datetime.now().strftime('%H:%M')
        two_days_ago = (datetime.now() - timedelta(days=2)).strftime('%d %B %Y')

        prompt = f"""
SEN BİR FİNANS EDİTÖRÜSÜN. Sadece PİYASAYI ETKİLEYEN kritik haberleri seç.

BUGÜN: {today}, SAAT: {current_time}

⚠️ ÖNEMLİ TARİH FİLTRESİ:
- Haberlerin sonunda [Tarih: ...] etiketi var
- SADECE SON 48 SAAT İÇİNDEKİ ({two_days_ago} - {today}) HABERLERİ AL
- 2025 yılından haberler → KESINLIKLE ATLA
- 3+ gün önceki haberler → ATLA

═══════════════════════════════════════════
GÖREV 1 - BAYRAM KONTROLÜ
═══════════════════════════════════════════
Bugün Türkiye'de resmi tatil/bayram var mı?
VARSA → "BAYRAM: [tam isim]" | YOKSA → "BAYRAM: YOK"

═══════════════════════════════════════════
GÖREV 2 - ULTRA SIKI FİLTRE + TARİH KONTROLÜ
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
ÇIKTI FORMATI:
═══════════════════════════════════════════
BAYRAM: [VAR/YOK veya isim]
1. [Tam anlaşılır özet - Max 15 kelime]
2. [Tam anlaşılır özet - Max 15 kelime]

❌ HİÇBİR kritik haber yoksa: "HABER: YOK"
"""

        logger.info(f"🤖 [GEMİNİ] {len(news_list)} haber filtreleniyor...")

        result = _call_gemini_with_retry(model, prompt, label="GEMİNİ HABER")
        if not result:
            logger.error("❌ [GEMİNİ HABER] Tüm denemeler başarısız!")
            return [], None

        lines = result.split('\n')
        bayram_msg = None
        first_line = lines[0].strip()

        if first_line.startswith("BAYRAM:"):
            bayram_text = first_line.replace("BAYRAM:", "").strip()
            if bayram_text and bayram_text.upper() != "YOK":
                bayram_msg = f"🏦 {bayram_text}"
            lines = lines[1:]

        summaries = []
        for line in lines:
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
        return summaries, bayram_msg

    except Exception as e:
        logger.error(f"❌ [GEMİNİ] Hata: {e}")
        return [], None

def fetch_harem_html() -> Optional[str]:
    try:
        url = Config.HAREM_PRICE_URL
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=Config.HAREM_FETCH_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        table = soup.find('table') or soup.find_all('div', class_='data')
        if table:
            html_text = str(table)[:5000]
            logger.info(f"✅ [HAREM HTML] {len(html_text)} karakter alındı")
            return html_text
        logger.error("❌ [HAREM HTML] Tablo bulunamadı!")
        return None
    except Exception as e:
        logger.error(f"❌ [HAREM HTML] Hata: {e}")
        return None

def fetch_ziraat_html() -> Optional[str]:
    try:
        url = Config.ZIRAAT_CURRENCY_URL
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=Config.ZIRAAT_FETCH_TIMEOUT)
        response.raise_for_status()
        html_text = response.text[:10000]
        logger.info(f"✅ [ZİRAAT HTML] {len(html_text)} karakter alındı")
        return html_text
    except Exception as e:
        logger.error(f"❌ [ZİRAAT HTML] Hata: {e}")
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


# ✅ YENİ: Altın + Döviz tek Gemini çağrısında birleştirildi (2 çağrı → 1 çağrı)
def calculate_all_margins_with_gemini(
    harem_html: str,
    ziraat_html: str,
    gold_api_prices: Dict,
    currency_api_prices: Dict,
    old_margins: Dict = None
) -> Optional[Dict]:
    try:
        if not GEMINI_API_KEY:
            return None

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-3-flash-preview')

        gold_api_str = "\n".join([f"- {k}: {v:.2f} ₺" for k, v in gold_api_prices.items() if v])
        major_currencies = ["USD", "EUR", "GBP", "CHF", "CAD", "AUD", "SEK", "NOK", "SAR", "DKK", "JPY"]
        currency_api_str = "\n".join([
            f"- {k}: {currency_api_prices.get(k, 0):.4f} ₺"
            for k in major_currencies if currency_api_prices.get(k, 0)
        ])

        prompt = f"""
SEN BİR FİNANS ANALİSTİSİN. İKİ GÖREV var: altın marjları + döviz marjları. Her ikisini TEK SEFERDE hesapla.

════════════════════════════════════════════
GÖREV 1 — ALTIN/GÜMÜŞ MARJI (Harem Altın)
════════════════════════════════════════════

📊 API HAM FİYATLAR — ALTIN (Borsa/Toptan ALIŞ):
{gold_api_str}

🌐 HAREM HTML:
{harem_html[:2500]}

🎯 HESAPLAMA: MARJ = ((Harem SATIŞ - API ALIŞ) / API ALIŞ) × 100

⚠️ SÜTUN SIRASI:
- BİRİNCİ sütun = ALIŞ → KULLANMA
- İKİNCİ sütun = SATIŞ → BUNU KULLAN

📌 ÜRÜN EŞLEMELERİ: GRA=Gram Altın, C22=Çeyrek, YAR=Yarım, TAM=Tam, ATA=Ata Altın, AG=Gram Gümüş
⚠️ HER ÜRÜN İÇİN AYRI HESAPLA! GRA marjını diğerlerine kopyalama.
🔥 Beklenen aralıklar: Altınlar %0.5-8.0, Gümüş %2.0-12.0

════════════════════════════════════════════
GÖREV 2 — DÖVİZ MARJI (Ziraat Bankası)
════════════════════════════════════════════

📊 API HAM FİYATLAR — DÖVİZ (Serbest Piyasa/Truncgil):
{currency_api_str}

🌐 ZİRAAT HTML:
{ziraat_html[:2500]}

🎯 HESAPLAMA: MARJ = ((Ziraat SATIŞ - API) / API) × 100

⚠️ SADECE SATIŞ SÜTUNU! Ziraat'ın spreadi geniştir, marj %1.0-5.0 arası çıkabilir, normaldir.

════════════════════════════════════════════
ÇIKTI — SADECE BU FORMAT, AÇIKLAMA YAPMA!
════════════════════════════════════════════
MARJ_GRA: 1.77
MARJ_C22: 1.50
MARJ_YAR: 1.90
MARJ_TAM: 1.20
MARJ_ATA: 1.70
MARJ_AG: 4.50
MARJ_USD: 2.96
MARJ_EUR: 2.43
MARJ_GBP: 1.89
MARJ_CHF: 2.53
MARJ_CAD: 2.46
MARJ_AUD: 2.00
MARJ_SEK: 2.74
MARJ_NOK: 2.37
MARJ_SAR: 2.94
MARJ_DKK: 2.56
MARJ_JPY: 2.03
"""

        logger.info("🤖 [GEMİNİ BİRLEŞİK MARJ] Altın + Döviz tek çağrıda hesaplanıyor...")

        result = _call_gemini_with_retry(model, prompt, label="GEMİNİ BİRLEŞİK MARJ")
        if not result:
            logger.error("❌ [GEMİNİ BİRLEŞİK MARJ] Tüm denemeler başarısız!")
            return None

        margins = {}
        rejected = []
        for line in result.split('\n'):
            if 'MARJ_' in line:
                parts = line.split(':')
                if len(parts) == 2:
                    key = parts[0].replace('MARJ_', '').strip()
                    try:
                        value = float(parts[1].strip()) / 100
                        if _validate_margin(key, value):
                            margins[key] = value
                            # AG → GUMUS kopyası
                            if key == 'AG':
                                margins['GUMUS'] = value
                                logger.debug(f"🔄 [GEMİNİ MARJ] GUMUS = AG: {value:.4f}")
                        else:
                            # Validation başarısız → eski marjı koru
                            if old_margins and key in old_margins:
                                margins[key] = old_margins[key]
                                logger.warning(
                                    f"⚠️ [VALİDASYON] {key} → eski marj korundu: {old_margins[key]:.4f}"
                                )
                            rejected.append(key)
                    except ValueError:
                        continue

        if rejected:
            logger.warning(f"⚠️ [GEMİNİ BİRLEŞİK MARJ] Reddedilen marjlar: {rejected}")

        if not margins:
            logger.error("❌ [GEMİNİ BİRLEŞİK MARJ] Parse edilemedi veya tümü reddedildi!")
            return None

        # ✅ C22/YAR/TAM türetme KALDIRILDI — Gemini her birini ayrı hesaplıyor
        # Sadece CUM Gemini'den gelmezse GRA'dan fallback yap
        if 'GRA' in margins and 'CUM' not in margins:
            margins['CUM'] = margins['GRA']
            logger.info(f"🔄 [FIX] CUM marjı yok, GRA'dan türetildi: {margins['GRA']:.4f}")

        gold_keys = [k for k in margins if k in ('GRA','C22','YAR','TAM','ATA','AG','GUMUS','CUM')]
        currency_keys = [k for k in margins if k in major_currencies]
        logger.info(
            f"✅ [GEMİNİ BİRLEŞİK MARJ] Toplam {len(margins)} marj: "
            f"ALTIN={gold_keys}, DÖVİZ={currency_keys}"
        )
        return margins

    except Exception as e:
        logger.error(f"❌ [GEMİNİ BİRLEŞİK MARJ] Hata: {e}")
        return None


# Eski fonksiyonlar korunuyor (geriye dönük uyumluluk için)
def calculate_full_margins_with_gemini(html_data: str, api_prices: Dict, old_margins: Dict = None) -> Optional[Dict]:
    """Geriye dönük uyumluluk — artık calculate_all_margins_with_gemini kullanılıyor."""
    logger.warning("⚠️ [COMPAT] calculate_full_margins_with_gemini çağrıldı, yeni fonksiyona yönlendiriliyor.")
    return None


def calculate_currency_margins_with_gemini(html_data: str, api_prices: Dict, old_margins: Dict = None) -> Optional[Dict]:
    """Geriye dönük uyumluluk — artık calculate_all_margins_with_gemini kullanılıyor."""
    logger.warning("⚠️ [COMPAT] calculate_currency_margins_with_gemini çağrıldı, yeni fonksiyona yönlendiriliyor.")
    return None


def update_dynamic_margins() -> bool:
    try:
        logger.info("💰 [HİBRİT MARJ] Güncelleme başlıyor...")

        harem_html = fetch_harem_html()
        ziraat_html = fetch_ziraat_html()

        try:
            from services.financial_service import fetch_from_v5
            api_data = fetch_from_v5()
            if not api_data or 'Rates' not in api_data:
                logger.error("❌ [HİBRİT MARJ] API verisi alınamadı!")
                return False

            ata_buy = (
                api_data['Rates'].get('ATA', {}).get('Buying', 0) or
                api_data['Rates'].get('CUM', {}).get('Buying', 0) or 0
            )
            gold_api_prices = {
                'GRA': api_data['Rates'].get('GRA', {}).get('Buying', 0),
                'C22': api_data['Rates'].get('CEYREKALTIN', {}).get('Buying', 0),
                'YAR': api_data['Rates'].get('YARIMALTIN', {}).get('Buying', 0),
                'TAM': api_data['Rates'].get('TAMALTIN', {}).get('Buying', 0),
                'AG':  api_data['Rates'].get('GUMUS', {}).get('Buying', 0),
                'ATA': ata_buy,
            }

            major_currencies = ["USD", "EUR", "GBP", "CHF", "CAD", "AUD", "SEK", "NOK", "SAR", "DKK", "JPY"]
            currency_api_prices = {
                code: api_data['Rates'].get(code, {}).get('Selling', 0)
                for code in major_currencies
            }
        except Exception as api_error:
            logger.error(f"❌ [HİBRİT MARJ] API çağrısı başarısız: {api_error}")
            return False

        old_margins = get_cache(Config.CACHE_KEYS.get('dynamic_margins', 'dynamic:margins')) or {}

        # ✅ TEK Gemini çağrısı — hem altın hem döviz
        all_computed_margins = {}
        if harem_html and ziraat_html:
            all_computed_margins = calculate_all_margins_with_gemini(
                harem_html, ziraat_html,
                gold_api_prices, currency_api_prices,
                old_margins=old_margins
            ) or {}
        elif harem_html:
            logger.warning("⚠️ [HİBRİT MARJ] Ziraat HTML yok, sadece altın hesaplanacak")
            # Sadece altın için eski yönteme dön
            from services.news_manager import calculate_all_margins_with_gemini as _calc
            all_computed_margins = calculate_all_margins_with_gemini(
                harem_html, "", gold_api_prices, {}, old_margins=old_margins
            ) or {}
        elif ziraat_html:
            logger.warning("⚠️ [HİBRİT MARJ] Harem HTML yok, sadece döviz hesaplanacak")
            all_computed_margins = calculate_all_margins_with_gemini(
                "", ziraat_html, {}, currency_api_prices, old_margins=old_margins
            ) or {}

        exotic_margins = getattr(Config, 'STATIC_EXOTIC_MARGINS', {})
        gold_static_margins = getattr(Config, 'STATIC_GOLD_MARGINS', {})

        all_new_margins = {**all_computed_margins, **exotic_margins, **gold_static_margins}

        if not all_new_margins:
            logger.warning("⚠️ [HİBRİT MARJ] Hiç marj hesaplanamadı!")
            return False

        logger.info(
            f"📊 [HİBRİT MARJ] Toplam: {len(all_new_margins)} marj "
            f"(BİRLEŞİK:{len(all_computed_margins)} + EXOTIC:{len(exotic_margins)} + GOLD_STATIC:{len(gold_static_margins)})"
        )

        smooth_margins = dict(old_margins)
        threshold = Config.MARGIN_SMOOTH_THRESHOLD

        for key, new_val in all_new_margins.items():
            if key in exotic_margins or key in gold_static_margins:
                smooth_margins[key] = new_val
                continue
            old_val = old_margins.get(key, new_val)
            diff = abs(new_val - old_val)
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

        logger.info(f"✅ [HİBRİT MARJ] Kaydedildi: {len(smooth_margins)} marj")
        return True

    except Exception as e:
        logger.error(f"❌ [HİBRİT MARJ] Hata: {e}")
        return False

def get_dynamic_margins() -> Dict[str, float]:
    global _margin_bootstrap_in_progress

    dynamic_margins = get_cache(Config.CACHE_KEYS.get('dynamic_margins', 'dynamic:margins'))
    if dynamic_margins and isinstance(dynamic_margins, dict):
        return dynamic_margins

    last_successful_key = Config.CACHE_KEYS.get('margin_last_update', 'margin:last_update')
    last_successful = get_cache(last_successful_key)

    if last_successful and isinstance(last_successful, dict):
        margins = last_successful.get('margins')
        timestamp = last_successful.get('timestamp', 0)

        if margins and isinstance(margins, dict):
            days_ago = (time.time() - timestamp) / 86400

            if days_ago > 1.0:
                with _margin_bootstrap_lock:
                    if not _margin_bootstrap_in_progress:
                        _margin_bootstrap_in_progress = True
                        logger.warning(f"⚠️ [HİBRİT MARJ] {days_ago:.1f} gün önce! ASYNC Bootstrap başlatılıyor...")
                        thread = threading.Thread(target=async_margin_bootstrap, daemon=True)
                        thread.start()

            return margins

    logger.error("🔴 [HİBRİT MARJ BOOTSTRAP] Marj yok! Gemini çağrılıyor...")
    bootstrap_success = update_dynamic_margins()

    if bootstrap_success:
        fresh_margins = get_cache(Config.CACHE_KEYS.get('dynamic_margins', 'dynamic:margins'))
        if fresh_margins:
            logger.info("✅ [HİBRİT MARJ BOOTSTRAP] Başarılı!")
            return fresh_margins

    logger.critical(
        "💣 [HİBRİT MARJ BOOTSTRAP] Gemini başarısız! "
        "SABIT FALLBACK MARJLAR kullanılıyor — kuyumcu fiyatı ham fiyata EŞİTLENMEYECEK!"
    )
    return _get_config_fallback_margins()


def plan_shift_schedule(news_list: List[str], start_hour: int, end_hour: int) -> List[Dict]:
    if not news_list:
        return []

    total_duration_minutes = (end_hour - start_hour) * 60
    news_count = len(news_list)
    duration_per_news = total_duration_minutes // news_count

    schedule = []
    current_time = datetime.now().replace(hour=start_hour, minute=0, second=0, microsecond=0)

    if start_hour == 0 and datetime.now().hour >= 12:
        current_time += timedelta(days=1)

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

def calculate_bayram_ttl() -> int:
    now = datetime.now()
    tomorrow_3am = (now + timedelta(days=1)).replace(hour=3, minute=0, second=0, microsecond=0)
    return int((tomorrow_3am - now).total_seconds())

def prepare_morning_news() -> bool:
    try:
        news_list = fetch_all_news()
        fresh_news = filter_already_shown(news_list) if news_list else []
        summaries, bayram_msg = summarize_news_batch(fresh_news) if fresh_news else ([], None)
        pending_key = Config.CACHE_KEYS.get('news_morning_pending', 'news:morning_pending')
        set_cache(pending_key, {'summaries': summaries, 'bayram': bayram_msg}, ttl=600)
        logger.info(f"✅ [SABAH HAZIRLIK] {len(summaries)} haber hazırlandı")
        return True
    except Exception as e:
        logger.error(f"❌ [SABAH HAZIRLIK] Hata: {e}")
        return False

def publish_morning_news() -> bool:
    try:
        logger.info("🌅 [SABAH YAYINLA] Hazır haberler yayınlanıyor...")
        pending_key = Config.CACHE_KEYS.get('news_morning_pending', 'news:morning_pending')
        pending_data = get_cache(pending_key)
        if not pending_data:
            logger.error("❌ [SABAH YAYINLA] PENDING verisi yok!")
            return False

        summaries = pending_data.get('summaries', [])
        bayram_msg = pending_data.get('bayram')

        if bayram_msg:
            bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
            set_cache(bayram_key, bayram_msg, ttl=calculate_bayram_ttl())

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
            'shift': 'morning', 'timestamp': time.time(),
            'news_count': len(summaries), 'bayram': bayram_msg or 'yok'
        }, ttl=86400)
        return True
    except Exception as e:
        logger.error(f"❌ [SABAH YAYINLA] Hata: {e}")
        return False

def prepare_evening_news() -> bool:
    try:
        news_list = fetch_all_news()
        fresh_news = filter_already_shown(news_list) if news_list else []
        summaries, bayram_msg = summarize_news_batch(fresh_news) if fresh_news else ([], None)
        pending_key = Config.CACHE_KEYS.get('news_evening_pending', 'news:evening_pending')
        set_cache(pending_key, {'summaries': summaries, 'bayram': bayram_msg}, ttl=600)
        logger.info(f"✅ [AKŞAM HAZIRLIK] {len(summaries)} haber hazırlandı")
        return True
    except Exception as e:
        logger.error(f"❌ [AKŞAM HAZIRLIK] Hata: {e}")
        return False

def publish_evening_news() -> bool:
    try:
        logger.info("🌆 [AKŞAM YAYINLA] Hazır haberler yayınlanıyor...")
        pending_key = Config.CACHE_KEYS.get('news_evening_pending', 'news:evening_pending')
        pending_data = get_cache(pending_key)
        if not pending_data:
            logger.error("❌ [AKŞAM YAYINLA] PENDING verisi yok!")
            return False

        summaries = pending_data.get('summaries', [])
        bayram_msg = pending_data.get('bayram')

        if bayram_msg:
            bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
            set_cache(bayram_key, bayram_msg, ttl=calculate_bayram_ttl())

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
            'shift': 'evening', 'timestamp': time.time(),
            'news_count': len(summaries), 'bayram': bayram_msg or 'yok'
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
            cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
            shift_name = "SABAH"
            shift_type = "morning"
        else:
            cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
            shift_name = "AKŞAM"
            shift_type = "evening"

        now = time.time()
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
        except:
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

        banner_msg = f"📰 {schedule[0]['text']}"
        if _last_logged_banner != banner_msg:
            logger.info(f"📰 [BANNER] Değişti: {banner_msg[:50]}...")
            _last_logged_banner = banner_msg
        return banner_msg

    except Exception as e:
        logger.error(f"❌ [BANNER] Hata: {e}")
        return None

def test_news_manager():
    print("🧪 News Manager Test\n")

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
        print("3️⃣ GEMINI FİLTRE:")
        summaries, bayram_msg = summarize_news_batch(fresh_news)
        print(f"   ✅ {len(summaries)} kritik haber\n")
        if bayram_msg:
            print(f"   🏦 BAYRAM: {bayram_msg}\n")
        if summaries:
            print("   Kritik haberler:")
            for i, summary in enumerate(summaries, 1):
                print(f"   {i}. {summary}")
        print()

    print("4️⃣ HİBRİT MARJ SİSTEMİ:")
    margins = get_dynamic_margins()
    print(f"   ✅ {len(margins)} marj alındı!\n")
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
