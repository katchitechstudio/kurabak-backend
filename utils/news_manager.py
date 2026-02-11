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

V4.3 Değişiklikler (HİBRİT MARJ SİSTEMİ):
- 🔥 ALTIN + GÜMÜŞ: Harem + Gemini (6 varlık - dinamik)
- 🔥 MAJÖR DÖVİZLER: Ziraat Bankası + Gemini (11 döviz - dinamik)
- 🔥 EXOTIC DÖVİZLER: Config sabit marjlar (12 döviz - statik)
- 🔥 TAM MARJ: Kuyumcu gerçeğini yansıtır
- 🔥 SMOOTH GEÇİŞ: Marj değişimi kademeli
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

# 🔥 MARGIN ASYNC BOOTSTRAP LOCK
_margin_bootstrap_lock = threading.Lock()
_margin_bootstrap_in_progress = False


# ======================================
# 🔧 GELIŞMIŞ DEDUP - SIMILARITY KONTROLÜ
# ======================================

def is_similar(text1: str, text2: str, threshold: float = 0.7) -> bool:
    """
    İki haberin benzerlik oranını hesaplar
    threshold: 0.7 = %70 benzer ise aynı haber kabul edilir
    """
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio() > threshold


def deduplicate_news(news_list: List[str]) -> List[str]:
    """
    Gelişmiş deduplication - Benzer haberleri temizler
    """
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
    """
    Son 24 saatte gösterilen haberleri getir
    """
    history_key = "news:shown_history"
    history = get_cache(history_key) or []
    return history


def save_shown_news(news_list: List[str]):
    """
    Gösterilen haberleri kaydet (24 saat TTL)
    """
    history_key = "news:shown_history"
    
    # Mevcut geçmişi al
    existing = get_cache(history_key) or []
    
    # Yeni haberleri ekle
    updated = existing + news_list
    
    # Dedup yap (tam eşleşme)
    unique = list(set(updated))
    
    # 24 saat sakla
    set_cache(history_key, unique, ttl=86400)
    logger.info(f"💾 [HISTORY] {len(unique)} haber geçmişte (son 24 saat)")


def filter_already_shown(news_list: List[str]) -> List[str]:
    """
    Daha önce gösterilenleri filtrele
    """
    shown_before = get_previously_shown_news()
    
    if not shown_before:
        logger.info("📝 [VARDIYA DEDUP] İlk vardiya, tüm haberler yeni")
        return news_list
    
    filtered = []
    skipped_count = 0
    
    for news in news_list:
        # Benzerlik kontrolü (yüksek threshold - çok benzer olmalı)
        is_duplicate = False
        for old_news in shown_before:
            if is_similar(news, old_news, threshold=0.8):
                is_duplicate = True
                skipped_count += 1
                logger.debug(f"🚫 [VARDIYA DEDUP] Atlandı: {news[:60]}...")
                break
        
        if not is_duplicate:
            filtered.append(news)
    
    logger.info(f"🧹 [VARDIYA DEDUP] {len(news_list)} → {len(filtered)} yeni haber ({skipped_count} tekrar atlandı)")
    return filtered


# ======================================
# 🛡️ RATE-LIMIT KORUMALI API ÇAĞRILARI
# ======================================

def fetch_with_retry(url: str, max_retries: int = 3, timeout: int = 10) -> Optional[Dict]:
    """
    Retry + exponential backoff ile güvenli API çağrısı
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()  # 4xx/5xx hatalarını yakala
            return response.json()
            
        except requests.exceptions.RequestException as e:
            wait_time = 2 ** attempt  # 2, 4, 8 saniye
            logger.warning(f"⚠️ [RETRY] Deneme {attempt + 1}/{max_retries} başarısız. {wait_time}s bekleniyor... Hata: {e}")
            
            if attempt < max_retries - 1:
                time.sleep(wait_time)
            else:
                logger.error(f"❌ [FETCH] Tüm denemeler başarısız: {e}")
                return None
    
    return None


def fetch_gnews(max_results: int = 30) -> List[str]:
    """
    GNews API'den ekonomi haberleri çeker - SON 3 GÜN + TARİH ETİKETLİ
    """
    try:
        if not GNEWS_API_KEY:
            logger.warning("⚠️ GNEWS_API_KEY bulunamadı!")
            return []
        
        # SON 3 GÜN
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
        
        logger.info("📡 [GNEWS] Haberler çekiliyor (son 3 gün)...")
        data = fetch_with_retry(url)
        
        if not data or data.get('totalArticles', 0) == 0:
            logger.warning("⚠️ [GNEWS] Haber bulunamadı")
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
        logger.error(f"❌ [GNEWS] Beklenmeyen hata: {e}")
        return []


def fetch_newsdata(max_results: int = 40) -> List[str]:
    """
    NewsData API'den ekonomi haberleri çeker
    """
    try:
        if not NEWSDATA_API_KEY:
            logger.warning("⚠️ NEWSDATA_API_KEY bulunamadı!")
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
            logger.warning("⚠️ [NEWSDATA] Hata veya haber bulunamadı")
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
        logger.error(f"❌ [NEWSDATA] Beklenmeyen hata: {e}")
        return []


def fetch_all_news() -> List[str]:
    """
    Tüm kaynaklardan haberleri çeker ve dedup yapar
    """
    logger.info("📰 [NEWS] Tüm kaynaklardan haber toplama başlıyor...")
    
    # İki kaynaktan da topla
    gnews_list = fetch_gnews(max_results=Config.NEWS_MAX_RESULTS_PER_SOURCE)
    newsdata_list = fetch_newsdata(max_results=Config.NEWS_MAX_RESULTS_PER_SOURCE)
    
    # Birleştir
    all_news = gnews_list + newsdata_list
    
    # Gelişmiş dedup
    unique_news = deduplicate_news(all_news)
    
    logger.info(f"✅ [NEWS] Toplam {len(unique_news)} benzersiz haber toplandı")
    return unique_news


# ======================================
# 🛡️ GÜÇLÜ FALLBACK İLE GEMİNİ FİLTRE
# ======================================

def summarize_news_batch(news_list: List[str]) -> Tuple[List[str], Optional[str]]:
    """
    ULTRA SIKI FİLTRE + TARİH FİLTRESİ
    """
    try:
        if not GEMINI_API_KEY:
            logger.warning("⚠️ GEMINI_API_KEY bulunamadı!")
            return [], None
        
        if not news_list:
            logger.warning("⚠️ [GEMİNİ] Özetlenecek haber yok!")
            return [], None
        
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-3-flash-preview')  # 🔥 V5.5: Gemini 3 Flash
        
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
✅ Duyuru haberlerinde SAAT belirt
✅ Sonuç haberlerinde RAKAM belirt
✅ Rekor haberlerinde RAKAM belirt
✅ Emoji YOK
✅ [Tarih: ...] etiketini gösterme
❌ HİÇBİR kritik haber yoksa: "HABER: YOK"
"""
        
        logger.info(f"🤖 [GEMİNİ 3 FLASH] {len(news_list)} haber filtreleniyor...")
        
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
                logger.info(f"🏦 [GEMİNİ] Bayram: {bayram_text}")
            lines = lines[1:]
        
        # Filtrelenmiş haberler
        summaries = []
        for line in lines:
            clean_line = line.strip()
            
            if not clean_line:
                continue
            
            if "HABER:" in clean_line.upper() and "YOK" in clean_line.upper():
                logger.warning("⚠️ [GEMİNİ] Kritik haber bulunamadı!")
                break
            
            # Numarayı kaldır
            if '. ' in clean_line:
                parts = clean_line.split('. ', 1)
                if len(parts) > 1:
                    clean_line = parts[1]
            
            if clean_line and len(clean_line) > 10:
                summaries.append(clean_line)
        
        logger.info(f"✅ [GEMİNİ 3 FLASH] {len(summaries)} kritik haber filtrelendi")
        
        if not summaries:
            logger.warning("⚠️ [GEMİNİ] Bugün kritik haber yok")
            return [], bayram_msg
        
        return summaries, bayram_msg
        
    except Exception as e:
        logger.error(f"❌ [GEMİNİ] Beklenmeyen hata: {e}")
        return [], None


# ======================================
# 🔥 DİNAMİK TAM MARJ SİSTEMİ V4.3 (HİBRİT)
# ======================================

def fetch_harem_html() -> Optional[str]:
    """
    Harem sayfasının HTML'ini çeker (Altın + Gümüş)
    """
    try:
        url = Config.HAREM_PRICE_URL
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        logger.info(f"🕷️ [HAREM HTML] Çekiliyor: {url}")
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
    """
    🔥 V4.3: Ziraat Bankası döviz kurları HTML'ini çeker (Majör dövizler)
    """
    try:
        url = Config.ZIRAAT_CURRENCY_URL
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        logger.info(f"🕷️ [ZİRAAT HTML] Çekiliyor: {url}")
        response = requests.get(url, headers=headers, timeout=Config.ZIRAAT_FETCH_TIMEOUT)
        response.raise_for_status()
        
        html_text = response.text[:10000]  # İlk 10k karakter yeterli
        logger.info(f"✅ [ZİRAAT HTML] {len(html_text)} karakter alındı")
        return html_text
        
    except Exception as e:
        logger.error(f"❌ [ZİRAAT HTML] Hata: {e}")
        return None


# 🔥 ASYNC MARGIN BOOTSTRAP
def async_margin_bootstrap():
    """
    🔥 KOMBO TAKTİK: Arka planda marj güncelle (non-blocking)
    
    ÇALIŞMA PRENSİBİ:
    - Worker devam eder (hızlı!)
    - Arka planda thread başlar
    - 3-5 saniye sonra marjlar hazır
    - Bir sonraki worker taze marjları kullanır!
    """
    global _margin_bootstrap_in_progress
    
    try:
        logger.info("🔄 [ASYNC MARJ] Arka planda başlatıldı...")
        success = update_dynamic_margins()
        
        if success:
            logger.info("✅ [ASYNC MARJ] Tamamlandı! Taze marjlar hazır!")
        else:
            logger.warning("⚠️ [ASYNC MARJ] Güncelleme başarısız, eski marjlar kullanılacak")
    except Exception as e:
        logger.error(f"❌ [ASYNC MARJ] Hata: {e}")
    finally:
        with _margin_bootstrap_lock:
            _margin_bootstrap_in_progress = False


def calculate_full_margins_with_gemini(html_data: str, api_prices: Dict) -> Optional[Dict]:
    """
    🔥 V4.3: Gemini'ye HTML verisini göndererek TAM MARJLARI hesaplat
    
    ALTINLAR + GÜMÜŞ için (Harem HTML)
    """
    try:
        if not GEMINI_API_KEY:
            logger.warning("⚠️ GEMINI_API_KEY bulunamadı!")
            return None
        
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-3-flash-preview')  # 🔥 Gemini 3 Flash (AYNI!)
        
        # API fiyatlarını formatla
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

📐 NEGATİF MARJ ÖRNEĞİ:
- Harem Satış: 48.080,00 ₺
- API Satış: 48.500,00 ₺  
- Fark: 48080 - 48500 = -420 ₺
- TAM MARJ: (-420 / 48500) × 100 = -0.87%
- ÇIKTI: -0.87

⚠️ FORMAT DİKKAT:
- HTML'de binlik ayraç NOKTA: 7.267,68
- HTML'de ondalık ayraç VİRGÜL: 7267,68
- Çıktıda NOKTA kullan: 4.73 (4,73 değil!)
- SATIŞ sütunundaki değeri al (ALIŞ değil!)
- NEGATİF marjları eksi işaretiyle yaz: -0.87

🎯 ÜRÜN EŞLEMELERİ - HTML'DEKİ TAM İSİMLER:
GRA = HTML'de "Gram Altın" diye geçiyor
C22 = HTML'de "Çeyrek Altın" diye geçiyor
YAR = HTML'de "Yarım Altın" diye geçiyor
TAM = HTML'de "Tam Altın" diye geçiyor
ATA = HTML'de "Ata Altın" diye geçiyor (Atatürk DEĞİL!)
AG = HTML'de "Gram Gümüş" veya "Gümüş" diye geçiyor

🔥 ÖZEL UYARI - ATA ALTIN:
- HTML'de "Ata Altın" diye geçiyor (Atatürk altını değil!)
- "Ata Altın" satırını bul
- SATIŞ sütunundaki değeri al
- Tam Altın ile yakın fiyatlıdır
- NEGATİF marj çıkabilir, bu normal!
- Eksi değeri olduğu gibi yaz

🔥 ÖZEL UYARI - TAM ALTIN:
- HTML'de "Tam Altın" diye geçiyor
- Harem bazen API'den ucuz olabilir
- NEGATİF marj çıkabilir, bu normal!
- Eksi değeri olduğu gibi yaz

🔥 ÖZEL UYARI - GÜMÜŞ:
- HTML'de "Gram Gümüş" veya sadece "Gümüş" diye geçiyor
- SATIŞ değeri 120-150 TL civarındadır
- Gümüş marjı %15-20 olmalıdır
- Eğer %10'dan düşük hesapladıysan HATALI hesaplamışsındır
- SATIŞ sütununu çok dikkatli oku!
- Örnek: API=117.43, Harem=139.49 → Marj=%18.8

🔍 ARAMA TALİMATI:
- Önce ürün ismini TAM OLARAK HTML'de bul
- Sonra o satırdaki SATIŞ değerini al
- Örnek: "Gram Altın" satırını bul → SATIŞ sütunu → değeri al

📤 ÇIKTI FORMATI (SADECE BU - noktalı sayılar, negatif dahil!):
MARJ_GRA: 4.73
MARJ_C22: 1.58
MARJ_YAR: 1.90
MARJ_TAM: -0.87
MARJ_ATA: 0.52
MARJ_AG: 18.80

HİÇBİR AÇIKLAMA YAPMA!
"""
        
        logger.info("🤖 [GEMİNİ 3 FLASH MARJ] TAM MARJ (ALTIN + GÜMÜŞ) hesaplama başlıyor...")
        
        response = model.generate_content(prompt)
        result = response.text.strip()
        
        if not result or len(result) < 10:
            logger.error("❌ [GEMİNİ MARJ] Boş yanıt!")
            return None
        
        # Parse et
        margins = {}
        for line in result.split('\n'):
            if 'MARJ_' in line:
                parts = line.split(':')
                if len(parts) == 2:
                    key = parts[0].replace('MARJ_', '').strip()
                    try:
                        value = float(parts[1].strip()) / 100  # %4.73 → 0.0473
                        margins[key] = value
                    except ValueError:
                        logger.warning(f"⚠️ [MARJ PARSE] Geçersiz değer: {line}")
                        continue
        
        if not margins:
            logger.error("❌ [GEMİNİ MARJ] Parse edilemedi!")
            return None
        
        logger.info(f"✅ [GEMİNİ 3 FLASH] {len(margins)} TAM MARJ (ALTIN+GÜMÜŞ) hesaplandı: {margins}")
        return margins
        
    except Exception as e:
        logger.error(f"❌ [GEMİNİ MARJ] Hata: {e}")
        return None


def calculate_currency_margins_with_gemini(html_data: str, api_prices: Dict) -> Optional[Dict]:
    """
    🔥 V4.3 YENİ: Gemini'ye Ziraat HTML'ini göndererek 11 MAJÖR DÖVİZ MARJINI hesaplat
    """
    try:
        if not GEMINI_API_KEY:
            logger.warning("⚠️ GEMINI_API_KEY bulunamadı!")
            return None
        
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-3-flash-preview')  # 🔥 Gemini 3 Flash (AYNI!)
        
        # API fiyatlarını formatla (sadece 11 majör döviz)
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

📐 ÖRNEK HESAPLAMA (Dolar):
- Ziraat Banka Satış: 44.9334 ₺
- API (TCMB): 43.6389 ₺
- Fark: 44.9334 - 43.6389 = 1.2945 ₺
- MARJ: (1.2945 / 43.6389) × 100 = 2.97%
- ÇIKTI: 2.97

⚠️ DİKKAT:
- HTML'de "Banka Satış" veya "Satış" değerini bul
- "Banka Alış" değerini ALMA (o farklı!)
- Marj genellikle %1.0 - %2.5 arası olmalıdır
- %5'ten yüksek çıkarsa HATALI!

🎯 DÖVIZ EŞLEMELERİ - HTML'DEKİ İSİMLER:
USD = "Amerikan Doları" veya "Dolar"
EUR = "Euro"
GBP = "İngiliz Sterlini" veya "Sterlin"
CHF = "İsviçre Frangı"
CAD = "Kanada Doları"
AUD = "Avustralya Doları"
SEK = "İsveç Kronu"
NOK = "Norveç Kronu"
SAR = "Suudi Arabistan Riyali"
DKK = "Danimarka Kronu"
JPY = "Japon Yeni" (100 JPY için fiyat verilir!)

🔥 ÖZEL UYARI - JAPON YENİ:
- HTML'de "Japon Yeni" 100 JPY başına fiyat verilir
- API'den gelen de 100 JPY fiyatıdır
- Direkt karşılaştır, çarpma/bölme yapma!

📤 ÇIKTI FORMATI (SADECE BU - noktalı sayılar!):
MARJ_USD: 2.97
MARJ_EUR: 2.65
MARJ_GBP: 2.89
MARJ_CHF: 2.74
MARJ_CAD: 2.85
MARJ_AUD: 3.12
MARJ_SEK: 2.93
MARJ_NOK: 3.05
MARJ_SAR: 2.51
MARJ_DKK: 2.78
MARJ_JPY: 2.88

HİÇBİR AÇIKLAMA YAPMA!
"""
        
        logger.info("🤖 [GEMİNİ 3 FLASH DÖVİZ] 11 MAJÖR DÖVİZ MARJI hesaplama başlıyor...")
        
        response = model.generate_content(prompt)
        result = response.text.strip()
        
        if not result or len(result) < 10:
            logger.error("❌ [GEMİNİ DÖVİZ] Boş yanıt!")
            return None
        
        # Parse et
        margins = {}
        for line in result.split('\n'):
            if 'MARJ_' in line:
                parts = line.split(':')
                if len(parts) == 2:
                    key = parts[0].replace('MARJ_', '').strip()
                    try:
                        value = float(parts[1].strip()) / 100  # %2.97 → 0.0297
                        margins[key] = value
                    except ValueError:
                        logger.warning(f"⚠️ [DÖVİZ MARJ PARSE] Geçersiz değer: {line}")
                        continue
        
        if not margins:
            logger.error("❌ [GEMİNİ DÖVİZ] Parse edilemedi!")
            return None
        
        logger.info(f"✅ [GEMİNİ 3 FLASH] {len(margins)} MAJÖR DÖVİZ MARJI hesaplandı: {margins}")
        return margins
        
    except Exception as e:
        logger.error(f"❌ [GEMİNİ DÖVİZ] Hata: {e}")
        return None


def update_dynamic_margins() -> bool:
    """
    🔥 V4.3: HİBRİT MARJ SİSTEMİ - Dinamik (Harem + Ziraat) + Statik (Config)
    
    ZAMANLAMA: Gece 00:05 (snapshot'tan sonra, haberlerden önce)
    
    MARJ KAYNAKLARI:
    1. DİNAMİK (Gemini hesaplar):
       - ALTIN + GÜMÜŞ: Harem (6 varlık)
       - MAJÖR DÖVİZLER: Ziraat (11 döviz)
    2. STATİK (Config'den):
       - EXOTIC DÖVİZLER: Manuel (12 döviz)
    
    ÖZELLİKLER:
    - TAM MARJ hesaplama
    - SMOOTH GEÇİŞ (sadece dinamik marjlar için)
    - NEGATİF MARJ desteği
    - Jeweler cache rebuild
    - Jeweler snapshot güncelleme
    """
    try:
        logger.info("💰 [HİBRİT MARJ] Güncelleme başlıyor...")
        logger.info("📍 [HİBRİT MARJ] ALTIN+GÜMÜŞ (Harem) + 11 DÖVİZ (Ziraat) + 12 EXOTIC (Config)")
        
        # 1. HTML'leri çek
        harem_html = fetch_harem_html()
        ziraat_html = fetch_ziraat_html()
        
        # 2. API fiyatlarını al
        try:
            from services.financial_service import fetch_from_v5
            api_data = fetch_from_v5()
            
            if not api_data or 'Rates' not in api_data:
                logger.error("❌ [HİBRİT MARJ] API verisi alınamadı!")
                return False
            
            # ALTIN + GÜMÜŞ için API fiyatları
            gold_api_prices = {
                'GRA': api_data['Rates'].get('GRA', {}).get('Selling', 0),
                'CEYREKALTIN': api_data['Rates'].get('CEYREKALTIN', {}).get('Selling', 0),
                'YARIMALTIN': api_data['Rates'].get('YARIMALTIN', {}).get('Selling', 0),
                'TAMALTIN': api_data['Rates'].get('TAMALTIN', {}).get('Selling', 0),
                'GUMUS': api_data['Rates'].get('GUMUS', {}).get('Selling', 0),
            }
            
            # DÖVİZLER için API fiyatları (11 majör)
            major_currencies = ["USD", "EUR", "GBP", "CHF", "CAD", "AUD", "SEK", "NOK", "SAR", "DKK", "JPY"]
            currency_api_prices = {
                code: api_data['Rates'].get(code, {}).get('Selling', 0)
                for code in major_currencies
            }
            
            logger.info(f"✅ [HİBRİT MARJ] API fiyatları alındı")
            
        except Exception as api_error:
            logger.error(f"❌ [HİBRİT MARJ] API çağrısı başarısız: {api_error}")
            return False
        
        # 3. Gemini ile ALTIN + GÜMÜŞ marjlarını hesapla
        gold_silver_margins = {}
        if harem_html:
            gold_silver_margins = calculate_full_margins_with_gemini(harem_html, gold_api_prices) or {}
        else:
            logger.warning("⚠️ [HİBRİT MARJ] Harem HTML yok, altın/gümüş marjları atlandı")
        
        # 4. 🔥 YENİ: Gemini ile MAJÖR DÖVİZ marjlarını hesapla
        major_currency_margins = {}
        if ziraat_html:
            major_currency_margins = calculate_currency_margins_with_gemini(ziraat_html, currency_api_prices) or {}
        else:
            logger.warning("⚠️ [HİBRİT MARJ] Ziraat HTML yok, döviz marjları atlandı")
        
        # 5. 🔥 YENİ: Config'den EXOTIC DÖVİZ marjlarını al
        exotic_margins = getattr(Config, 'STATIC_EXOTIC_MARGINS', {})
        
        # 6. HEPSİNİ BİRLEŞTİR
        all_new_margins = {**gold_silver_margins, **major_currency_margins, **exotic_margins}
        
        if not all_new_margins:
            logger.warning("⚠️ [HİBRİT MARJ] Hiç marj hesaplanamadı!")
            return False
        
        logger.info(f"📊 [HİBRİT MARJ] Toplam: {len(all_new_margins)} marj (ALTIN:{len(gold_silver_margins)} + MAJÖR:{len(major_currency_margins)} + EXOTIC:{len(exotic_margins)})")
        
        # 7. 🔥 SMOOTH GEÇİŞ - Sadece dinamik marjlar için (exotic marjlar statik, smooth yok!)
        old_margins = get_cache(Config.CACHE_KEYS.get('dynamic_margins', 'dynamic:margins')) or {}
        
        smooth_margins = {}
        threshold = Config.MARGIN_SMOOTH_THRESHOLD  # 0.015 (%1.5)
        
        for key, new_val in all_new_margins.items():
            # 🔥 Exotic marjlar için smooth yok (zaten statik)
            if key in exotic_margins:
                smooth_margins[key] = new_val
                continue
            
            # Dinamik marjlar için smooth geçiş
            old_val = old_margins.get(key, new_val)
            diff = abs(new_val - old_val)
            
            if diff > threshold and Config.MARGIN_SMOOTH_TRANSITION:
                # Fark %1.5'ten büyük → Ortalama al (kademeli geçiş)
                smooth_margins[key] = round((old_val + new_val) / 2, 4)
                logger.warning(
                    f"📊 [SMOOTH GEÇİŞ] {key}: {old_val:.4f} → {new_val:.4f} "
                    f"(Fark: {diff:.4f}) → SMOOTH: {smooth_margins[key]:.4f}"
                )
            else:
                # Fark küçük → Direkt uygula
                smooth_margins[key] = new_val
        
        # 8. Redis'e kaydet (24 saat TTL - bugünkü marjlar)
        margin_key = Config.CACHE_KEYS.get('dynamic_margins', 'dynamic:margins')
        set_cache(margin_key, smooth_margins, ttl=86400)
        
        # 9. 🔥 KALICI BACKUP (TTL=0, süresiz!)
        update_key = Config.CACHE_KEYS.get('margin_last_update', 'margin:last_update')
        set_cache(update_key, {
            'timestamp': time.time(),
            'margins': smooth_margins
        }, ttl=0)
        
        logger.info(f"✅ [HİBRİT MARJ] Kaydedildi: {len(smooth_margins)} marj")
        logger.info(f"💾 [HİBRİT MARJ] KALICI BACKUP kaydedildi (TTL=0)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ [HİBRİT MARJ] Beklenmeyen hata: {e}")
        return False


def get_dynamic_margins() -> Dict[str, float]:
    """
    🔥 V4.3: HİBRİT MARJLARI getir (Dinamik + Exotic)
    
    FALLBACK SIRASI:
    1. Redis (bugünkü marjlar: dinamik + exotic birleşmiş) → En taze!
    2. margin_last_update (en son başarılı: dinamik + exotic) → Fallback
       → 🔥 1 günden eskiyse ASYNC bootstrap tetikle!
    3. BOOTSTRAP (ilk kurulum) → İlk çalışma
    """
    global _margin_bootstrap_in_progress
    
    # 1️⃣ BUGÜNKÜ MARJLARI DENE
    dynamic_margins = get_cache(Config.CACHE_KEYS.get('dynamic_margins', 'dynamic:margins'))
    
    if dynamic_margins and isinstance(dynamic_margins, dict):
        logger.debug(f"✅ [HİBRİT MARJ] Bugünkü marjlar: {len(dynamic_margins)} marj")
        return dynamic_margins
    
    # 2️⃣ EN SON BAŞARILI MARJLARI AL
    last_successful_key = Config.CACHE_KEYS.get('margin_last_update', 'margin:last_update')
    last_successful = get_cache(last_successful_key)
    
    if last_successful and isinstance(last_successful, dict):
        margins = last_successful.get('margins')
        timestamp = last_successful.get('timestamp', 0)
        
        if margins and isinstance(margins, dict):
            days_ago = (time.time() - timestamp) / 86400
            
            # 🔥 KOMBO TAKTİK: 1 GÜNDEN ESKİYSE ASYNC BOOTSTRAP TETİKLE!
            if days_ago > 1.0:
                with _margin_bootstrap_lock:
                    if not _margin_bootstrap_in_progress:
                        _margin_bootstrap_in_progress = True
                        logger.warning(
                            f"⚠️ [HİBRİT MARJ] En son marj {days_ago:.1f} gün önce! "
                            f"ASYNC Bootstrap başlatılıyor..."
                        )
                        
                        # 🔥 Arka planda thread başlat (non-blocking!)
                        thread = threading.Thread(target=async_margin_bootstrap, daemon=True)
                        thread.start()
                        
                        logger.info("🚀 [ASYNC MARJ] Thread başlatıldı, worker devam ediyor...")
            
            logger.warning(
                f"⚠️ [HİBRİT MARJ] Fallback kullanıldı (margin_last_update) - "
                f"{days_ago:.1f} gün önce"
            )
            
            return margins
    
    # 3️⃣ BOOTSTRAP (İLK KURULUM) - İlk çalışmada kaçınılmaz
    logger.error("🔴 [HİBRİT MARJ BOOTSTRAP] Marj yok! Gemini çağrılıyor...")
    
    bootstrap_success = update_dynamic_margins()
    
    if bootstrap_success:
        fresh_margins = get_cache(Config.CACHE_KEYS.get('dynamic_margins', 'dynamic:margins'))
        
        if fresh_margins:
            logger.info("✅ [HİBRİT MARJ BOOTSTRAP] Gemini başarılı!")
            return fresh_margins
    
    # BOOTSTRAP BAŞARISIZ → Varsayılan 0.0
    logger.critical("💣 [HİBRİT MARJ BOOTSTRAP] Gemini başarısız! HAM FİYAT kullanılacak!")
    
    fallback_margins = {}
    
    # Dövizler (23 adet)
    for code in ["USD", "EUR", "GBP", "CHF", "CAD", "AUD", "RUB", "SAR", "AED", 
                 "KWD", "BHD", "OMR", "QAR", "CNY", "SEK", "NOK", "PLN", "RON", 
                 "CZK", "EGP", "RSD", "HUF", "BAM"]:
        fallback_margins[code] = 0.0
    
    # Altınlar
    for code in ["GRA", "C22", "YAR", "TAM", "CUM", "ATA", "HAS"]:
        fallback_margins[code] = 0.0
    
    # Gümüş
    fallback_margins["AG"] = 0.0
    fallback_margins["GUMUS"] = 0.0
    
    logger.warning(f"⚠️ [FALLBACK] {len(fallback_margins)} marj (0.0)")
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
    
    logger.info(f"📅 [PLAN] {news_count} haber, {start_hour}:00 - {end_hour}:00 arası dağıtılıyor")
    
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
    """
    Bayram mesajı için TTL hesapla (gece 03:00'e kadar)
    """
    now = datetime.now()
    tomorrow_3am = (now + timedelta(days=1)).replace(hour=3, minute=0, second=0, microsecond=0)
    ttl = int((tomorrow_3am - now).total_seconds())
    
    logger.debug(f"🕐 [BAYRAM TTL] {ttl} saniye (yarın 03:00'e kadar)")
    return ttl


# ======================================
# 🔥 PREPARE FONKSIYONLARI (YENİ! V4.0)
# ======================================

def prepare_morning_news() -> bool:
    """
    🔥 V4.3: SABAH HABERLERİNİ HAZIRLA (23:55'te çağrılır)
    """
    try:
        logger.info("🌅 [SABAH HAZIRLIK] Haberler hazırlanıyor (Gemini çağrısı)...")
        
        news_list = fetch_all_news()
        
        logger.info(f"🔍 [DEBUG] Toplanan haber sayısı: {len(news_list)}")
        
        if not news_list:
            logger.warning("⚠️ [SABAH HAZIRLIK] Haber bulunamadı!")
            pending_key = Config.CACHE_KEYS.get('news_morning_pending', 'news:morning_pending')
            set_cache(pending_key, {'summaries': [], 'bayram': None}, ttl=600)
            return True
        
        fresh_news = filter_already_shown(news_list)
        
        logger.info(f"🔍 [DEBUG] Dedup sonrası: {len(fresh_news)} yeni haber")
        
        if not fresh_news:
            logger.warning("⚠️ [SABAH HAZIRLIK] Tüm haberler daha önce gösterilmiş!")
            pending_key = Config.CACHE_KEYS.get('news_morning_pending', 'news:morning_pending')
            set_cache(pending_key, {'summaries': [], 'bayram': None}, ttl=600)
            return True
        
        summaries, bayram_msg = summarize_news_batch(fresh_news)
        
        logger.info(f"🔍 [DEBUG] Gemini sonrası: {len(summaries)} kritik haber")
        logger.info(f"🔍 [DEBUG] Bayram: {bayram_msg}")
        
        pending_key = Config.CACHE_KEYS.get('news_morning_pending', 'news:morning_pending')
        set_cache(pending_key, {
            'summaries': summaries,
            'bayram': bayram_msg
        }, ttl=600)
        
        logger.info(f"🔍 [DEBUG] PENDING cache'e kaydedildi: {pending_key}")
        logger.info(f"✅ [SABAH HAZIRLIK] {len(summaries)} haber hazırlandı (PENDING)")
        if bayram_msg:
            logger.info(f"🏦 [SABAH HAZIRLIK] Bayram: {bayram_msg}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ [SABAH HAZIRLIK] Hata: {e}")
        return False


def publish_morning_news() -> bool:
    """
    🔥 V4.3: SABAH HABERLERİNİ YAYINLA (00:00'da çağrılır)
    """
    try:
        logger.info("🌅 [SABAH YAYINLA] Hazır haberler yayınlanıyor...")
        
        pending_key = Config.CACHE_KEYS.get('news_morning_pending', 'news:morning_pending')
        pending_data = get_cache(pending_key)
        
        if not pending_data:
            logger.error("❌ [SABAH YAYINLA] PENDING verisi yok! (23:55'te hazırlanmalıydı)")
            return False
        
        summaries = pending_data.get('summaries', [])
        bayram_msg = pending_data.get('bayram')
        
        if bayram_msg:
            bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
            bayram_ttl = calculate_bayram_ttl()
            set_cache(bayram_key, bayram_msg, ttl=bayram_ttl)
            logger.info(f"🏦 [SABAH YAYINLA] Bayram kaydedildi: {bayram_msg}")
        
        if summaries:
            schedule = plan_shift_schedule(summaries, start_hour=0, end_hour=12)
            
            cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
            set_cache(cache_key, schedule, ttl=43200)
            
            save_shown_news(summaries)
            
            logger.info(f"✅ [SABAH YAYINLA] {len(schedule)} haber yayınlandı!")
        else:
            cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
            set_cache(cache_key, [], ttl=43200)
            logger.warning("⚠️ [SABAH YAYINLA] Kritik haber yok")
        
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
    """
    🔥 V4.3: AKŞAM HABERLERİNİ HAZIRLA (11:55'te çağrılır)
    """
    try:
        logger.info("🌆 [AKŞAM HAZIRLIK] Haberler hazırlanıyor (Gemini çağrısı)...")
        
        news_list = fetch_all_news()
        
        if not news_list:
            logger.warning("⚠️ [AKŞAM HAZIRLIK] Haber bulunamadı!")
            pending_key = Config.CACHE_KEYS.get('news_evening_pending', 'news:evening_pending')
            set_cache(pending_key, {'summaries': [], 'bayram': None}, ttl=600)
            return True
        
        fresh_news = filter_already_shown(news_list)
        
        if not fresh_news:
            logger.warning("⚠️ [AKŞAM HAZIRLIK] Tüm haberler daha önce gösterilmiş!")
            pending_key = Config.CACHE_KEYS.get('news_evening_pending', 'news:evening_pending')
            set_cache(pending_key, {'summaries': [], 'bayram': None}, ttl=600)
            return True
        
        summaries, bayram_msg = summarize_news_batch(fresh_news)
        
        pending_key = Config.CACHE_KEYS.get('news_evening_pending', 'news:evening_pending')
        set_cache(pending_key, {
            'summaries': summaries,
            'bayram': bayram_msg
        }, ttl=600)
        
        logger.info(f"✅ [AKŞAM HAZIRLIK] {len(summaries)} haber hazırlandı (PENDING)")
        if bayram_msg:
            logger.info(f"🏦 [AKŞAM HAZIRLIK] Bayram: {bayram_msg}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ [AKŞAM HAZIRLIK] Hata: {e}")
        return False


def publish_evening_news() -> bool:
    """
    🔥 V4.3: AKŞAM HABERLERİNİ YAYINLA (12:00'da çağrılır)
    """
    try:
        logger.info("🌆 [AKŞAM YAYINLA] Hazır haberler yayınlanıyor...")
        
        pending_key = Config.CACHE_KEYS.get('news_evening_pending', 'news:evening_pending')
        pending_data = get_cache(pending_key)
        
        if not pending_data:
            logger.error("❌ [AKŞAM YAYINLA] PENDING verisi yok! (11:55'te hazırlanmalıydı)")
            return False
        
        summaries = pending_data.get('summaries', [])
        bayram_msg = pending_data.get('bayram')
        
        if bayram_msg:
            bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
            bayram_ttl = calculate_bayram_ttl()
            set_cache(bayram_key, bayram_msg, ttl=bayram_ttl)
            logger.info(f"🏦 [AKŞAM YAYINLA] Bayram kaydedildi: {bayram_msg}")
        
        if summaries:
            schedule = plan_shift_schedule(summaries, start_hour=12, end_hour=24)
            
            cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
            set_cache(cache_key, schedule, ttl=43200)
            
            save_shown_news(summaries)
            
            logger.info(f"✅ [AKŞAM YAYINLA] {len(schedule)} haber yayınlandı!")
        else:
            cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
            set_cache(cache_key, [], ttl=43200)
            logger.warning("⚠️ [AKŞAM YAYINLA] Kritik haber yok")
        
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
    """
    İlk çalıştırma bootstrap
    """
    try:
        current_hour = datetime.now().hour
        
        logger.info(f"🔍 [DEBUG BOOTSTRAP] Saat: {current_hour}")
        
        if 0 <= current_hour < 12:
            cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
            shift_name = "SABAH"
            shift_type = "morning"
        else:
            cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
            shift_name = "AKŞAM"
            shift_type = "evening"
        
        with _bootstrap_lock:
            if _bootstrap_in_progress[shift_type]:
                logger.info(f"ℹ️ [BOOTSTRAP] {shift_name} vardiyası zaten hazırlanıyor...")
                return False
            
            existing_data = get_cache(cache_key)
            
            logger.info(f"🔍 [DEBUG BOOTSTRAP] Cache key: {cache_key}")
            logger.info(f"🔍 [DEBUG BOOTSTRAP] Mevcut veri: {existing_data is not None}")
            logger.info(f"🔍 [DEBUG BOOTSTRAP] Veri içeriği: {existing_data}")
            
            if existing_data is not None and len(existing_data) > 0:
                logger.info(f"✅ [BOOTSTRAP] {shift_name} vardiyası hazır ({len(existing_data)} haber)")
                return False
            
            _bootstrap_in_progress[shift_type] = True
            logger.warning(f"⚠️ [BOOTSTRAP] {shift_name} vardiyası boş! Doldurma başlıyor...")
        
        try:
            if shift_type == 'morning':
                success = prepare_morning_news() and publish_morning_news()
            else:
                success = prepare_evening_news() and publish_evening_news()
            
            logger.info(f"🔍 [DEBUG BOOTSTRAP] Başarı durumu: {success}")
            
            if success:
                logger.info(f"🚀 [BOOTSTRAP] {shift_name} vardiyası dolduruldu!")
                return True
            else:
                logger.error(f"❌ [BOOTSTRAP] {shift_name} vardiyası doldurulamadı!")
                return False
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
            shift_name = "SABAH"
        else:
            cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
            shift_name = "AKŞAM"
        
        schedule = get_cache(cache_key)
        
        if not schedule:
            logger.warning(f"⚠️ [BANNER] {shift_name} vardiyası yok! Bootstrap...")
            bootstrap_success = bootstrap_news_system()
            
            if bootstrap_success:
                schedule = get_cache(cache_key)
                if not schedule:
                    return None
            else:
                return None
        
        if len(schedule) == 0:
            logger.info(f"ℹ️ [BANNER] {shift_name}: Bugün kritik haber yok")
            return None
        
        for news_slot in schedule:
            start_time = news_slot['start']
            end_time = news_slot['end']
            
            if start_time <= current_time < end_time:
                logger.debug(f"📰 [BANNER] {shift_name}: {news_slot['text']}")
                return f"📰 {news_slot['text']}"
        
        if schedule:
            return f"📰 {schedule[0]['text']}"
        
        return None
        
    except Exception as e:
        logger.error(f"❌ [BANNER] Hata: {e}")
        return None


def test_news_manager():
    """Test fonksiyonu"""
    print("🧪 News Manager V4.3 - HİBRİT MARJ SİSTEMİ\n")
    
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
    print(f"   {'✅ Başarılı' if bootstrap_success else 'ℹ️ Gerek yok'}\n")
    
    print("6️⃣ BANNER:")
    banner = get_current_news_banner()
    if banner:
        print(f"   ✅ {banner}\n")
    else:
        print("   ℹ️ Bugün kritik haber yok\n")


if __name__ == "__main__":
    test_news_manager()
