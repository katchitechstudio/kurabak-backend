"""
News Manager - GÜNLÜK HABER SİSTEMİ V4.3 ULTIMATE 📰🚀💰
=========================================================
✅ ULTRA SIKI FİLTRE: Sadece kritik finansal olaylar
✅ DUYURU + SONUÇ: Hem "açıklanacak" hem "açıklandı" 
✅ GELİŞMİŞ DEDUP: Benzerlik + Vardiyalar arası
✅ GÜÇLÜ FALLBACK: Gemini patlarsa da sistem ayakta
✅ RATE-LIMIT KORUMA: Retry + exponential backoff
✅ BAYRAM MANTIKLI TTL: Gece 03:00'e kadar geçerli
✅ GEMİNİ 3 FLASH: Yeni model desteği 🔥
✅ RACE CONDITION FIX: Bootstrap lock mekanizması
✅ ÇİFT KAYNAK: GNews + NewsData
✅ 3 GÜN GERİYE + 48 SAAT FİLTRE: Optimal zaman aralığı
✅ VARDİYALAR ARASI DEDUP: Aynı haber 2. kez gösterilmez
✅ 🔥 DİNAMİK TAM MARJ V4.3: Hibrit sistem (Harem + Ziraat + Config)
✅ 🔥 SMOOTH MARJ GEÇİŞİ: 3-4 günde kademeli (alarm patlaması önlenir)
✅ 🔥 PREPARE/PUBLISH AYRI: Haberler 5 dakika önce hazırlanır
✅ 🔥 GÜMÜŞ + TAM + ATA MARJ FIX: Doğru isimlendirme ve negatif marj desteği
✅ 🔥 DÖVİZ PROMPT FIX: Ziraat SATIŞ sütunu uyarısı güçlendirildi
✅ 🔥 GÜMÜŞ PROMPT FIX: Harem SATIŞ sütunu uyarısı güçlendirildi
✅ 🔥 BOOTSTRAP COOLDOWN: Başarısız olsa bile 1 saat spam yapmaz
✅ 🔥 YAZIM KURALLARI: Saat formatı düzeltildi (22:00'da gibi)
✅ 🔥 LOG OPTİMİZASYONU: Gereksiz loglar temizlendi
"""

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

# 🔒 BOOTSTRAP LOCK - Race condition önleme
_bootstrap_lock = threading.Lock()
_bootstrap_in_progress = {
    'morning': False,
    'evening': False
}

# 🔥 BOOTSTRAP COOLDOWN - Başarısız olsa bile spam yapmaz
_bootstrap_last_attempt = {
    'morning': 0,
    'evening': 0
}
_bootstrap_cooldown = 3600  # 1 saat (saniye)

# 🔥 MARGIN ASYNC BOOTSTRAP LOCK
_margin_bootstrap_lock = threading.Lock()
_margin_bootstrap_in_progress = False


# ======================================
# 🔧 GELIŞMIŞ DEDUP - SIMILARITY KONTROLÜ
# ======================================

def is_similar(text1: str, text2: str, threshold: float = 0.7) -> bool:
    """İki haberin benzerlik oranını hesaplar"""
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio() > threshold


def deduplicate_news(news_list: List[str]) -> List[str]:
    """Gelişmiş deduplication - Benzer haberleri temizler"""
    unique_news = []
    
    for news in news_list:
        is_duplicate = False
        
        for existing_news in unique_news:
            if is_similar(news, existing_news, threshold=0.7):
                is_duplicate = True
                break
        
        if not is_duplicate:
            unique_news.append(news)
    
    logger.info(f"🧹 [DEDUP] {len(news_list)} → {len(unique_news)} benzersiz haber")
    return unique_news


# ======================================
# 🛡️ VARDİYALAR ARASI DEDUP
# ======================================

def get_previously_shown_news() -> List[str]:
    """Son 24 saatte gösterilen haberleri getir"""
    history_key = "news:shown_history"
    history = get_cache(history_key) or []
    return history


def save_shown_news(news_list: List[str]):
    """Gösterilen haberleri kaydet (24 saat TTL)"""
    history_key = "news:shown_history"
    existing = get_cache(history_key) or []
    updated = existing + news_list
    unique = list(set(updated))
    set_cache(history_key, unique, ttl=86400)


def filter_already_shown(news_list: List[str]) -> List[str]:
    """Daha önce gösterilenleri filtrele"""
    shown_before = get_previously_shown_news()
    
    if not shown_before:
        return news_list
    
    filtered = []
    
    for news in news_list:
        is_duplicate = False
        for old_news in shown_before:
            if is_similar(news, old_news, threshold=0.8):
                is_duplicate = True
                break
        
        if not is_duplicate:
            filtered.append(news)
    
    logger.info(f"🧹 [VARDIYA DEDUP] {len(news_list)} → {len(filtered)} yeni haber")
    return filtered


# ======================================
# 🛡️ RATE-LIMIT KORUMALI API ÇAĞRILARI
# ======================================

def fetch_with_retry(url: str, max_retries: int = 3, timeout: int = 10) -> Optional[Dict]:
    """Retry + exponential backoff ile güvenli API çağrısı"""
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
    """GNews API'den ekonomi haberleri çeker - SON 3 GÜN"""
    try:
        if not GNEWS_API_KEY:
            return []
        
        three_days_ago = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%dT%H:%M:%SZ')
        
        url = (
            f"https://gnews.io/api/v4/search"
            f"?q=(\"merkez bankası\" OR \"faiz kararı\" OR \"faiz\" OR \"enflasyon\" OR \"TCMB\" OR \"FED\" OR \"ECB\" OR \"büyüme\" OR \"GSYİH\")"
            f"&lang=tr"
            f"&country=tr"
            f"&from={three_days_ago}"
            f"&sortby=publishedAt"
            f"&max={max_results}"
            f"&apikey={GNEWS_API_KEY}"
        )
        
        logger.info("📡 [GNEWS] Haberler çekiliyor...")
        data = fetch_with_retry(url)
        
        if not data or data.get('totalArticles', 0) == 0:
            return []
        
        articles = data.get('articles', [])[:max_results]
        news_list = []
        
        for article in articles:
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
    """NewsData API'den ekonomi haberleri çeker"""
    try:
        if not NEWSDATA_API_KEY:
            return []
        
        url = (
            f"https://newsdata.io/api/1/news"
            f"?apikey={NEWSDATA_API_KEY}"
            f"&country=tr"
            f"&language=tr"
            f"&category=business"
            f"&q=(merkez AND bankası) OR faiz OR TCMB OR FED OR ECB OR enflasyon OR büyüme"
        )
        
        logger.info("📡 [NEWSDATA] Haberler çekiliyor...")
        data = fetch_with_retry(url)
        
        if not data or data.get('status') != 'success':
            return []
        
        results = data.get('results', [])[:max_results]
        news_list = []
        
        for article in results:
            title = article.get('title')
            description = article.get('description')
            pub_date = article.get('pubDate', '')
            
            if title is None:
                continue
            
            title = title.strip()
            
            if description is None:
                full_text = title
            else:
                description = description.strip()
                full_text = f"{title}. {description}" if description else title
            
            if full_text and len(full_text) > 15:
                news_list.append(f"{full_text} [Tarih: {pub_date}]")
        
        logger.info(f"✅ [NEWSDATA] {len(news_list)} haber alındı")
        return news_list
        
    except Exception as e:
        logger.error(f"❌ [NEWSDATA] Hata: {e}")
        return []


def fetch_all_news() -> List[str]:
    """Tüm kaynaklardan haberleri çeker ve dedup yapar"""
    logger.info("📰 [NEWS] Haber toplama başlıyor...")
    
    gnews_list = fetch_gnews(max_results=Config.NEWS_MAX_RESULTS_PER_SOURCE)
    newsdata_list = fetch_newsdata(max_results=Config.NEWS_MAX_RESULTS_PER_SOURCE)
    
    all_news = gnews_list + newsdata_list
    unique_news = deduplicate_news(all_news)
    
    logger.info(f"✅ [NEWS] Toplam {len(unique_news)} benzersiz haber toplandı")
    return unique_news


# ======================================
# 🛡️ GÜÇLÜ FALLBACK İLE GEMİNİ FİLTRE
# ======================================

def summarize_news_batch(news_list: List[str]) -> Tuple[List[str], Optional[str]]:
    """ULTRA SIKI FİLTRE + TARİH FİLTRESİ + YAZIM KURALLARI"""
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

1. MERKEZ BANKASI KARARLARI:
   📅 DUYURU: "FED bugün saat 21:00'de faiz kararını açıklayacak"
   ✅ SONUÇ: "FED faizi %4.5'te sabit tuttu"

2. KRİTİK EKONOMİK VERİ AÇIKLAMALARI:
   📅 DUYURU: "Enflasyon rakamları bugün saat 10:00'da açıklanacak"
   ✅ SONUÇ: "Ocak enflasyonu %64.77 açıklandı"

3. DÖVIZ/ALTIN REKORLARI:
   ✅ "Dolar TARİHİ REKOR kırdı: 45.50 TL"

4. BORSA KRİTİK HAREKETLER:
   ✅ "BIST 100 %5+ düşüşle 10.000'in altına indi"

5. GEOPOLİTİK ŞOKLAR:
   ✅ "ABD Çin'e yeni gümrük vergisi uygulamaya başladı"

6. YASAL DEĞİŞİKLİKLER:
   ✅ "Yeni asgari ücret 20.000 TL olarak açıklandı"

❌ BUNLARI ASLA ALMA:
- Genel yorumlar
- BES/emeklilik fon performansları
- Şirket kâr/zarar açıklamaları
- Banka kampanya/kredi haberleri
- Teknik analiz/tahmin haberleri
- Kripto para haberleri
- ESKİ TARİHLİ HABERLER

═══════════════════════════════════════════
YAZIM KURALLARI - ÇOK ÖNEMLİ!
═══════════════════════════════════════════

🔥 SAAT FORMATI:
✅ DOĞRU: "FED bugün saat 21:00'de faiz kararını açıklayacak"
✅ DOĞRU: "Enflasyon rakamları bugün saat 10:00'da açıklanacak"
❌ YANLIŞ: "21:00da" veya "21:00de" (kesme işareti OLMALI!)

🔥 NOKTALAMA:
✅ Her cümle nokta ile biter
✅ Rakamlardan sonra birim: "%64.77", "45.50 TL"
✅ Kesme işareti: "21:00'de", "10:00'da", "TCMB'nin"

🔥 BÜYÜK HARF:
✅ Kurum isimleri: FED, TCMB, ECB, BIST
✅ Para birimleri: TL, USD, EUR
✅ Cümle başları büyük

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

KURALLAR:
✅ Her özet TAM CÜMLE (max 15 kelime)
✅ Duyuru haberlerinde SAAT belirt (21:00'de formatında!)
✅ Sonuç haberlerinde RAKAM belirt
✅ Rekor haberlerinde RAKAM belirt
✅ Emoji YOK
✅ [Tarih: ...] etiketini gösterme
✅ Kesme işareti kullan: 21:00'de, 10:00'da
❌ HİÇBİR kritik haber yoksa: "HABER: YOK"
"""
        
        logger.info(f"🤖 [GEMİNİ] {len(news_list)} haber filtreleniyor...")
        
        try:
            response = model.generate_content(prompt)
            result = response.text.strip()
            
            if not result or len(result) < 10:
                logger.error("❌ [GEMİNİ] Boş yanıt!")
                return [], None
                
        except Exception as gemini_error:
            logger.error(f"❌ [GEMİNİ] API hatası: {gemini_error}")
            return [], None
        
        lines = result.split('\n')
        
        # Bayram kontrolü
        bayram_msg = None
        first_line = lines[0].strip()
        
        if first_line.startswith("BAYRAM:"):
            bayram_text = first_line.replace("BAYRAM:", "").strip()
            if bayram_text and bayram_text.upper() != "YOK":
                bayram_msg = f"🏦 {bayram_text}"
            lines = lines[1:]
        
        # Filtrelenmiş haberler
        summaries = []
        for line in lines:
            clean_line = line.strip()
            
            if not clean_line:
                continue
            
            if "HABER:" in clean_line.upper() and "YOK" in clean_line.upper():
                break
            
            # Numarayı kaldır
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


# ======================================
# 🔥 DİNAMİK TAM MARJ SİSTEMİ V4.3 (HİBRİT)
# ======================================

def fetch_harem_html() -> Optional[str]:
    """Harem sayfasının HTML'ini çeker (Altın + Gümüş)"""
    try:
        url = Config.HAREM_PRICE_URL
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=Config.HAREM_FETCH_TIMEOUT)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        table = soup.find('table')
        
        if not table:
            table = soup.find_all('div', class_='data')
        
        if table:
            html_text = str(table)[:5000]
            logger.info(f"✅ [HAREM HTML] {len(html_text)} karakter alındı")
            return html_text
        else:
            logger.error("❌ [HAREM HTML] Tablo bulunamadı!")
            return None
        
    except Exception as e:
        logger.error(f"❌ [HAREM HTML] Hata: {e}")
        return None


def fetch_ziraat_html() -> Optional[str]:
    """Ziraat Bankası döviz kurları HTML'ini çeker"""
    try:
        url = Config.ZIRAAT_CURRENCY_URL
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=Config.ZIRAAT_FETCH_TIMEOUT)
        response.raise_for_status()
        
        html_text = response.text[:10000]
        logger.info(f"✅ [ZİRAAT HTML] {len(html_text)} karakter alındı")
        return html_text
        
    except Exception as e:
        logger.error(f"❌ [ZİRAAT HTML] Hata: {e}")
        return None


def async_margin_bootstrap():
    """Arka planda marj güncelle (non-blocking)"""
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


def calculate_full_margins_with_gemini(html_data: str, api_prices: Dict) -> Optional[Dict]:
    """Gemini'ye HTML verisini göndererek TAM MARJLARI hesaplat (ALTIN + GÜMÜŞ)"""
    try:
        if not GEMINI_API_KEY:
            return None
        
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-3-flash-preview')
        
        api_str = "\n".join([
            f"- {k}: {v:.2f} ₺" for k, v in api_prices.items()
        ])
        
        prompt = f"""
SEN BİR FİNANS ANALİSTİSİN. Harem Altın web sitesindeki SATIŞ fiyatlarını kullanarak kuyumcu marjlarını hesapla.

📊 API'DEN GELEN HAM FİYATLAR (Borsa/Toptan):
{api_str}

🌐 HAREM WEB SİTESİ HTML VERİSİ:
{html_data[:3000]}

🎯 GÖREV:
1. HTML tablosundan Harem'in SATIŞ fiyatlarını çıkar
2. Her ürün için TAM MARJ hesapla: ((Harem Satış - API Satış) / API Satış) × 100
3. ONDALIK NOKTA KULLAN (virgül değil!)
4. NEGATİF marjları da hesapla (Harem ucuzsa marj eksi olur)

📐 ÖRNEK HESAPLAMA (Gram Altın):
- Harem Satış: 7.407,92 ₺ (HTML'deki virgülü noktaya çevir: 7407.92)
- API Satış: 7073.56 ₺
- Fark: 7407.92 - 7073.56 = 334.36 ₺
- TAM MARJ: (334.36 / 7073.56) × 100 = 4.73%
- ÇIKTI: 4.73

🎯 ÜRÜN EŞLEMELERİ:
GRA = "Gram Altın"
C22 = "Çeyrek Altın"
YAR = "Yarım Altın"
TAM = "Tam Altın"
ATA = "Ata Altın" (Atatürk DEĞİL!)
AG = "Gram Gümüş" veya "Gümüş"

🔥 ÖZEL UYARI - GÜMÜŞ (SATIŞ SÜTUNU!):
- HTML'de iki sütun var: ALIŞ ve SATIŞ
- SADECE SATIŞ SÜTUNUNU AL! (yüksek olanı)
- SATIŞ değeri 130-150 TL civarındadır
- Gümüş marjı %15-20 olmalıdır

📤 ÇIKTI FORMATI (SADECE BU):
MARJ_GRA: 4.73
MARJ_C22: 1.58
MARJ_YAR: 1.90
MARJ_TAM: -0.87
MARJ_ATA: 0.52
MARJ_AG: 16.00

HİÇBİR AÇIKLAMA YAPMA!
"""
        
        response = model.generate_content(prompt)
        result = response.text.strip()
        
        if not result or len(result) < 10:
            logger.error("❌ [GEMİNİ MARJ] Boş yanıt!")
            return None
        
        margins = {}
        for line in result.split('\n'):
            if 'MARJ_' in line:
                parts = line.split(':')
                if len(parts) == 2:
                    key = parts[0].replace('MARJ_', '').strip()
                    try:
                        value = float(parts[1].strip()) / 100
                        margins[key] = value
                    except ValueError:
                        continue
        
        if not margins:
            logger.error("❌ [GEMİNİ MARJ] Parse edilemedi!")
            return None
        
        logger.info(f"✅ [GEMİNİ] {len(margins)} ALTIN+GÜMÜŞ marjı hesaplandı")
        return margins
        
    except Exception as e:
        logger.error(f"❌ [GEMİNİ MARJ] Hata: {e}")
        return None


def calculate_currency_margins_with_gemini(html_data: str, api_prices: Dict) -> Optional[Dict]:
    """Gemini'ye Ziraat HTML'ini göndererek 11 MAJÖR DÖVİZ MARJINI hesaplat"""
    try:
        if not GEMINI_API_KEY:
            return None
        
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-3-flash-preview')
        
        major_currencies = ["USD", "EUR", "GBP", "CHF", "CAD", "AUD", "SEK", "NOK", "SAR", "DKK", "JPY"]
        api_str = "\n".join([
            f"- {k}: {api_prices.get(k, 0):.4f} ₺" 
            for k in major_currencies
            if k in api_prices
        ])
        
        prompt = f"""
SEN BİR FİNANS ANALİSTİSİN. Ziraat Bankası web sitesindeki BANKA SATIŞ fiyatlarını kullanarak döviz bürosu marjlarını hesapla.

📊 API'DEN GELEN HAM FİYATLAR (TCMB/Resmi Kur):
{api_str}

🌐 ZİRAAT BANKASI WEB SİTESİ HTML VERİSİ:
{html_data[:5000]}

🎯 GÖREV:
1. HTML'den "Banka Satış" veya ikinci fiyat sütununu çıkar
2. Her döviz için MARJ hesapla: ((Banka Satış - API) / API) × 100
3. ONDALIK NOKTA KULLAN (virgül değil!)

⚠️ ZİRAAT BANKASI ÖZEL UYARI:
- HTML'de iki sütun var: "Banka Alış" ve "Banka Satış"
- SADECE İKİNCİ SÜTUN (BANKA SATIŞ) AL!
- Örnek: "43,3205  44,1969" → 44,1969 al (yüksek olanı)
- Marj %1.0 - %1.5 arası olmalıdır

🎯 DÖVIZ EŞLEMELERİ:
USD = "Amerikan Doları"
EUR = "Euro"
GBP = "İngiliz Sterlini"
CHF = "İsviçre Frangı"
CAD = "Kanada Doları"
AUD = "Avustralya Doları"
SEK = "İsveç Kronu"
NOK = "Norveç Kronu"
SAR = "Suudi Arabistan Riyali"
DKK = "Danimarka Kronu"
JPY = "Japon Yeni" (100 JPY için)

📤 ÇIKTI FORMATI (SADECE BU):
MARJ_USD: 1.24
MARJ_EUR: 1.02
MARJ_GBP: 0.98
MARJ_CHF: 1.15
MARJ_CAD: 1.28
MARJ_AUD: 1.34
MARJ_SEK: 1.19
MARJ_NOK: 1.42
MARJ_SAR: 1.26
MARJ_DKK: 1.08
MARJ_JPY: 1.31

HİÇBİR AÇIKLAMA YAPMA!
"""
        
        response = model.generate_content(prompt)
        result = response.text.strip()
        
        if not result or len(result) < 10:
            logger.error("❌ [GEMİNİ DÖVİZ] Boş yanıt!")
            return None
        
        margins = {}
        for line in result.split('\n'):
            if 'MARJ_' in line:
                parts = line.split(':')
                if len(parts) == 2:
                    key = parts[0].replace('MARJ_', '').strip()
                    try:
                        value = float(parts[1].strip()) / 100
                        margins[key] = value
                    except ValueError:
                        continue
        
        if not margins:
            logger.error("❌ [GEMİNİ DÖVİZ] Parse edilemedi!")
            return None
        
        logger.info(f"✅ [GEMİNİ] {len(margins)} MAJÖR DÖVİZ marjı hesaplandı")
        return margins
        
    except Exception as e:
        logger.error(f"❌ [GEMİNİ DÖVİZ] Hata: {e}")
        return None


def update_dynamic_margins() -> bool:
    """HİBRİT MARJ SİSTEMİ - Dinamik (Harem + Ziraat) + Statik (Config)"""
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
            
            gold_api_prices = {
                'GRA': api_data['Rates'].get('GRA', {}).get('Selling', 0),
                'CEYREKALTIN': api_data['Rates'].get('CEYREKALTIN', {}).get('Selling', 0),
                'YARIMALTIN': api_data['Rates'].get('YARIMALTIN', {}).get('Selling', 0),
                'TAMALTIN': api_data['Rates'].get('TAMALTIN', {}).get('Selling', 0),
                'GUMUS': api_data['Rates'].get('GUMUS', {}).get('Selling', 0),
            }
            
            major_currencies = ["USD", "EUR", "GBP", "CHF", "CAD", "AUD", "SEK", "NOK", "SAR", "DKK", "JPY"]
            currency_api_prices = {
                code: api_data['Rates'].get(code, {}).get('Selling', 0)
                for code in major_currencies
            }
            
        except Exception as api_error:
            logger.error(f"❌ [HİBRİT MARJ] API çağrısı başarısız: {api_error}")
            return False
        
        gold_silver_margins = {}
        if harem_html:
            gold_silver_margins = calculate_full_margins_with_gemini(harem_html, gold_api_prices) or {}
        
        major_currency_margins = {}
        if ziraat_html:
            major_currency_margins = calculate_currency_margins_with_gemini(ziraat_html, currency_api_prices) or {}
        
        exotic_margins = getattr(Config, 'STATIC_EXOTIC_MARGINS', {})
        gold_static_margins = getattr(Config, 'STATIC_GOLD_MARGINS', {})
        
        all_new_margins = {**gold_silver_margins, **major_currency_margins, **exotic_margins, **gold_static_margins}
        
        if not all_new_margins:
            logger.warning("⚠️ [HİBRİT MARJ] Hiç marj hesaplanamadı!")
            return False
        
        logger.info(
            f"📊 [HİBRİT MARJ] Toplam: {len(all_new_margins)} marj "
            f"(ALTIN:{len(gold_silver_margins)} + DÖVİZ:{len(major_currency_margins)} + "
            f"EXOTIC:{len(exotic_margins)} + GOLD:{len(gold_static_margins)})"
        )
        
        old_margins = get_cache(Config.CACHE_KEYS.get('dynamic_margins', 'dynamic:margins')) or {}
        
        smooth_margins = {}
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
        
        margin_key = Config.CACHE_KEYS.get('dynamic_margins', 'dynamic:margins')
        set_cache(margin_key, smooth_margins, ttl=86400)
        
        update_key = Config.CACHE_KEYS.get('margin_last_update', 'margin:last_update')
        set_cache(update_key, {
            'timestamp': time.time(),
            'margins': smooth_margins
        }, ttl=0)
        
        logger.info(f"✅ [HİBRİT MARJ] Kaydedildi: {len(smooth_margins)} marj")
        return True
        
    except Exception as e:
        logger.error(f"❌ [HİBRİT MARJ] Hata: {e}")
        return False


def get_dynamic_margins() -> Dict[str, float]:
    """HİBRİT MARJLARI getir (Dinamik + Exotic + Gold)"""
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
    
    logger.critical("💣 [HİBRİT MARJ BOOTSTRAP] Başarısız! HAM FİYAT kullanılacak!")
    
    fallback_margins = {}
    
    for code in ["USD", "EUR", "GBP", "CHF", "CAD", "AUD", "RUB", "SAR", "AED", 
                 "KWD", "BHD", "OMR", "QAR", "CNY", "SEK", "NOK", "PLN", "RON", 
                 "CZK", "EGP", "RSD", "HUF", "BAM"]:
        fallback_margins[code] = 0.0
    
    for code in ["GRA", "C22", "YAR", "TAM", "CUM", "ATA", "HAS"]:
        fallback_margins[code] = 0.0
    
    fallback_margins["AG"] = 0.0
    fallback_margins["GUMUS"] = 0.0
    
    return fallback_margins


# ======================================
# 📅 VARDİYA PLANLAMA
# ======================================

def plan_shift_schedule(news_list: List[str], start_hour: int, end_hour: int) -> List[Dict]:
    """Haberleri saatlere eşit dağıt"""
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
            if end_hour == 24:
                end_time = current_time.replace(hour=23, minute=59)
            else:
                end_time = current_time.replace(hour=end_hour, minute=0)
        else:
            end_time = current_time + timedelta(minutes=duration_per_news)
        
        end_str = end_time.strftime("%H:%M")
        
        schedule.append({
            "start": start_str,
            "end": end_str,
            "text": news
        })
        
        current_time = end_time
    
    return schedule


def calculate_bayram_ttl() -> int:
    """Bayram mesajı için TTL hesapla (gece 03:00'e kadar)"""
    now = datetime.now()
    tomorrow_3am = (now + timedelta(days=1)).replace(hour=3, minute=0, second=0, microsecond=0)
    ttl = int((tomorrow_3am - now).total_seconds())
    return ttl


# ======================================
# 🔥 PREPARE & PUBLISH FONKSIYONLARI
# ======================================

def prepare_morning_news() -> bool:
    """SABAH HABERLERİNİ HAZIRLA (23:55'te çağrılır)"""
    try:
        logger.info("🌅 [SABAH HAZIRLIK] Haberler hazırlanıyor...")
        
        news_list = fetch_all_news()
        
        if not news_list:
            pending_key = Config.CACHE_KEYS.get('news_morning_pending', 'news:morning_pending')
            set_cache(pending_key, {'summaries': [], 'bayram': None}, ttl=600)
            return True
        
        fresh_news = filter_already_shown(news_list)
        
        if not fresh_news:
            pending_key = Config.CACHE_KEYS.get('news_morning_pending', 'news:morning_pending')
            set_cache(pending_key, {'summaries': [], 'bayram': None}, ttl=600)
            return True
        
        summaries, bayram_msg = summarize_news_batch(fresh_news)
        
        pending_key = Config.CACHE_KEYS.get('news_morning_pending', 'news:morning_pending')
        set_cache(pending_key, {
            'summaries': summaries,
            'bayram': bayram_msg
        }, ttl=600)
        
        logger.info(f"✅ [SABAH HAZIRLIK] {len(summaries)} haber hazırlandı")
        return True
        
    except Exception as e:
        logger.error(f"❌ [SABAH HAZIRLIK] Hata: {e}")
        return False


def publish_morning_news() -> bool:
    """SABAH HABERLERİNİ YAYINLA (00:00'da çağrılır)"""
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
            bayram_ttl = calculate_bayram_ttl()
            set_cache(bayram_key, bayram_msg, ttl=bayram_ttl)
        
        if summaries:
            schedule = plan_shift_schedule(summaries, start_hour=0, end_hour=12)
            cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
            set_cache(cache_key, schedule, ttl=43200)
            save_shown_news(summaries)
            logger.info(f"✅ [SABAH YAYINLA] {len(schedule)} haber yayınlandı")
        else:
            cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
            set_cache(cache_key, [], ttl=43200)
        
        delete_cache(pending_key)
        
        update_key = Config.CACHE_KEYS.get('news_last_update', 'news:last_update')
        set_cache(update_key, {
            'shift': 'morning',
            'timestamp': time.time(),
            'news_count': len(summaries),
            'bayram': bayram_msg if bayram_msg else 'yok'
        }, ttl=86400)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ [SABAH YAYINLA] Hata: {e}")
        return False


def prepare_evening_news() -> bool:
    """AKŞAM HABERLERİNİ HAZIRLA (11:55'te çağrılır)"""
    try:
        logger.info("🌆 [AKŞAM HAZIRLIK] Haberler hazırlanıyor...")
        
        news_list = fetch_all_news()
        
        if not news_list:
            pending_key = Config.CACHE_KEYS.get('news_evening_pending', 'news:evening_pending')
            set_cache(pending_key, {'summaries': [], 'bayram': None}, ttl=600)
            return True
        
        fresh_news = filter_already_shown(news_list)
        
        if not fresh_news:
            pending_key = Config.CACHE_KEYS.get('news_evening_pending', 'news:evening_pending')
            set_cache(pending_key, {'summaries': [], 'bayram': None}, ttl=600)
            return True
        
        summaries, bayram_msg = summarize_news_batch(fresh_news)
        
        pending_key = Config.CACHE_KEYS.get('news_evening_pending', 'news:evening_pending')
        set_cache(pending_key, {
            'summaries': summaries,
            'bayram': bayram_msg
        }, ttl=600)
        
        logger.info(f"✅ [AKŞAM HAZIRLIK] {len(summaries)} haber hazırlandı")
        return True
        
    except Exception as e:
        logger.error(f"❌ [AKŞAM HAZIRLIK] Hata: {e}")
        return False


def publish_evening_news() -> bool:
    """AKŞAM HABERLERİNİ YAYINLA (12:00'da çağrılır)"""
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
            bayram_ttl = calculate_bayram_ttl()
            set_cache(bayram_key, bayram_msg, ttl=bayram_ttl)
        
        if summaries:
            schedule = plan_shift_schedule(summaries, start_hour=12, end_hour=24)
            cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
            set_cache(cache_key, schedule, ttl=43200)
            save_shown_news(summaries)
            logger.info(f"✅ [AKŞAM YAYINLA] {len(schedule)} haber yayınlandı")
        else:
            cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
            set_cache(cache_key, [], ttl=43200)
        
        delete_cache(pending_key)
        
        update_key = Config.CACHE_KEYS.get('news_last_update', 'news:last_update')
        set_cache(update_key, {
            'shift': 'evening',
            'timestamp': time.time(),
            'news_count': len(summaries),
            'bayram': bayram_msg if bayram_msg else 'yok'
        }, ttl=86400)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ [AKŞAM YAYINLA] Hata: {e}")
        return False


# ======================================
# BOOTSTRAP & BANNER
# ======================================

def bootstrap_news_system() -> bool:
    """İlk çalıştırma bootstrap + COOLDOWN koruması"""
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
        
        # 🔥 COOLDOWN KONTROLÜ
        last_attempt = _bootstrap_last_attempt[shift_type]
        now = time.time()
        
        if last_attempt > 0 and (now - last_attempt) < _bootstrap_cooldown:
            remaining = int(_bootstrap_cooldown - (now - last_attempt))
            logger.debug(f"⏳ [BOOTSTRAP] {shift_name} cooldown: {remaining}s kaldı")
            return False
        
        with _bootstrap_lock:
            if _bootstrap_in_progress[shift_type]:
                return False
            
            existing_data = get_cache(cache_key)
            
            # 🔥 FİX: None ile boş liste ayrımı
            if existing_data is not None and len(existing_data) > 0:
                return False
            
            _bootstrap_in_progress[shift_type] = True
            logger.warning(f"⚠️ [BOOTSTRAP] {shift_name} vardiyası boş! Doldurma başlıyor...")
        
        try:
            if shift_type == 'morning':
                success = prepare_morning_news() and publish_morning_news()
            else:
                success = prepare_evening_news() and publish_evening_news()
            
            # 🔥 Başarılı veya başarısız, cooldown başlat
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
    """Şu anki saate uygun haber başlığını döndürür"""
    try:
        current_hour = datetime.now().hour
        current_time = datetime.now().strftime("%H:%M")
        
        if 0 <= current_hour < 12:
            cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
        else:
            cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
        
        schedule = get_cache(cache_key)
        
        # 🔥 FİX: None ile boş liste ayrımı
        if schedule is None:
            bootstrap_news_system()
            schedule = get_cache(cache_key)
        
        # Boş liste = haber yok (normal durum, log yok)
        if not schedule or len(schedule) == 0:
            return None
        
        for news_slot in schedule:
            start_time = news_slot['start']
            end_time = news_slot['end']
            
            if start_time <= current_time < end_time:
                return f"📰 {news_slot['text']}"
        
        if schedule:
            return f"📰 {schedule[0]['text']}"
        
        return None
        
    except Exception as e:
        logger.error(f"❌ [BANNER] Hata: {e}")
        return None


def test_news_manager():
    """Test fonksiyonu"""
    print("🧪 News Manager V4.3 - Temiz Versiyon\n")
    
    print("1️⃣ HABER TOPLAMA:")
    news_list = fetch_all_news()
    print(f"   ✅ {len(news_list)} haber toplandı\n")
    
    if news_list:
        print("   İlk 3 haber:")
        for i, news in enumerate(news_list[:3], 1):
            print(f"   {i}. {news[:120]}...")
        print()
    
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
