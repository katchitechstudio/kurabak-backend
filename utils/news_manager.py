"""
News Manager - GÜNLÜK HABER SİSTEMİ V3.9.3 ULTIMATE + SMART MARGIN FALLBACK 📰🚀💰
===================================================================================
✅ ULTRA SIKI FİLTRE: Sadece kritik finansal olaylar
✅ DUYURU + SONUÇ: Hem "açıklanacak" hem "açıklandı" 
✅ GELİŞMİŞ DEDUP: Benzerlik + Vardiyalar arası
✅ GÜÇLÜ FALLBACK: Gemini patlarsa da sistem ayakta
✅ RATE-LIMIT KORUMA: Retry + exponential backoff
✅ BAYRAM MANTIKLI TTL: Gece 03:00'e kadar geçerli
✅ GEMİNİ 3 FLASH: Yeni model desteği 🔥
✅ RACE CONDITION FIX: Bootstrap lock mekanizması
✅ ÇİFT KAYNAK: GNews + NewsData (V3.8)
✅ 3 GÜN GERİYE + 48 SAAT FİLTRE: Optimal zaman aralığı (V3.8)
✅ VARDİYALAR ARASI DEDUP: Aynı haber 2. kez gösterilmez (V3.8)
✅ 🔥 DİNAMİK YARIM MARJ: Günde 1 kere Harem'den otomatik marj hesaplama (V3.9)
✅ 🐛 BOOTSTRAP BOŞ LİSTE FIX: [] kontrolü düzeltildi (V3.9.1)
✅ 🔥 MARJ BAĞIMSIZLIĞI: Dinamik marj ayrı job'da çalışıyor (V3.9.2)
✅ 🔥 SMART MARGIN FALLBACK: Config kullanmıyor, en son başarılı marjları kullanıyor (V3.9.3)
✅ 🔥 MARGIN BOOTSTRAP: İlk kurulumda otomatik Gemini çağrısı (V3.9.3)

V3.9.3 Değişiklikler:
- 🔥 AKILLI FALLBACK: Gemini çökerse Config yerine en son başarılı marjları kullan
- 🔥 BOOTSTRAP: margin_last_update yoksa HEMEN Gemini çağır
- 🔥 CONFIG MARJ KALDIRILDI: Smooth geçiş için sadece geçmiş marjlar kullanılıyor
- 🔥 KALICI BACKUP: margin_last_update TTL=0 (süresiz, her zaman hazır)
- ⚡ ANI FİYAT DEĞİŞİMİ ÖNLENDİ: Kullanıcı deneyimi korundu
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

from utils.cache import get_cache, set_cache
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
    🔥 V3.8: 3 gün geriye (12 saat gecikme + buffer)
    """
    try:
        if not GNEWS_API_KEY:
            logger.warning("⚠️ GNEWS_API_KEY bulunamadı!")
            return []
        
        # 🔥 SON 3 GÜN - GNews'un 12 saat gecikmesini tolere et
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
            
            # 🔥 Tarihi ekle (Gemini görsün)
            if full_text and len(full_text) > 15:
                news_list.append(f"{full_text} [Tarih: {pub_date}]")
        
        logger.info(f"✅ [GNEWS] {len(news_list)} haber alındı")
        return news_list
        
    except Exception as e:
        logger.error(f"❌ [GNEWS] Beklenmeyen hata: {e}")
        return []


def fetch_newsdata(max_results: int = 40) -> List[str]:
    """
    NewsData API'den ekonomi haberleri çeker - TARİH FİLTRESİ YOK + TARİH ETİKETLİ
    🔥 V3.8: Tarih filtresi desteklenmiyor, Gemini filtreleyecek
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
        
        logger.info("📡 [NEWSDATA] Haberler çekiliyor (tarih filtresi yok)...")
        data = fetch_with_retry(url)
        
        if not data or data.get('status') != 'success':
            logger.warning("⚠️ [NEWSDATA] Hata veya haber bulunamadı")
            return []
        
        results = data.get('results', [])[:max_results]
        news_list = []
        
        for article in results:
            # 🔥 NULL SAFETY
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
            
            # 🔥 Tarihi ekle
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
    🔥 V3.8: GNews (3 gün) + NewsData (tarih yok)
    """
    logger.info("📰 [NEWS] Tüm kaynaklardan haber toplama başlıyor...")
    
    # İki kaynaktan da topla
    gnews_list = fetch_gnews(max_results=30)
    newsdata_list = fetch_newsdata(max_results=40)
    
    # Birleştir
    all_news = gnews_list + newsdata_list
    
    # Gelişmiş dedup (aynı request içinde)
    unique_news = deduplicate_news(all_news)
    
    logger.info(f"✅ [NEWS] Toplam {len(unique_news)} benzersiz haber toplandı")
    return unique_news


# ======================================
# 🛡️ GÜÇLÜ FALLBACK İLE GEMİNİ FİLTRE
# ======================================

def summarize_news_batch(news_list: List[str]) -> Tuple[List[str], Optional[str]]:
    """
    ULTRA SIKI FİLTRE + TARİH FİLTRESİ - Gemini patlarsa da sistem ayakta kalır
    🔥 V3.9: GEMİNİ 3 FLASH + Son 48 saat içindeki kritik haberleri seçer
    """
    try:
        if not GEMINI_API_KEY:
            logger.warning("⚠️ GEMINI_API_KEY bulunamadı! Fallback modu...")
            return [], None
        
        if not news_list:
            logger.warning("⚠️ [GEMİNİ] Özetlenecek haber yok!")
            return [], None
        
        genai.configure(api_key=GEMINI_API_KEY)
        
        # 🔥 YENİ MODEL: GEMINI 3 FLASH
        model = genai.GenerativeModel('gemini-3-flash-preview')
        
        numbered_news = '\n'.join([f"{i+1}. {news}" for i, news in enumerate(news_list)])
        today = datetime.now().strftime('%d %B %Y, %A')
        current_time = datetime.now().strftime('%H:%M')
        
        # 🔥 Tarih aralığı hesapla (son 48 saat)
        two_days_ago = (datetime.now() - timedelta(days=2)).strftime('%d %B %Y')
        
        prompt = f"""
SEN BİR FİNANS EDİTÖRÜSÜN. Sadece PİYASAYI ETKİLEYEN kritik haberleri seç.

BUGÜN: {today}, SAAT: {current_time}

⚠️ ÖNEMLİ TARİH FİLTRESİ:
- Haberlerin sonunda [Tarih: ...] etiketi var
- SADECE SON 48 SAAT İÇİNDEKİ ({two_days_ago} - {today}) HABERLERİ AL
- 2025 yılından haberler → KESINLIKLE ATLA
- 3+ gün önceki haberler → ATLA
- Eski tarihli haberler finansal durumu yansıtmaz!

═══════════════════════════════════════════
GÖREV 1 - BAYRAM KONTROLÜ
═══════════════════════════════════════════
Bugün Türkiye'de resmi tatil/bayram var mı?
VARSA → "BAYRAM: [tam isim]" | YOKSA → "BAYRAM: YOK"

═══════════════════════════════════════════
GÖREV 2 - ULTRA SIKI FİLTRE + TARİH KONTROLÜ
═══════════════════════════════════════════

✅ SADECE ŞU TİP HABERLERİ AL (VE GÜNCEL OLANLARI):

1. MERKEZ BANKASI KARARLARI (Hem duyuru hem sonuç!):
   📅 DUYURU: "FED bugün saat 21:00'de faiz kararını açıklayacak"
   ✅ SONUÇ: "FED faizi %4.5'te sabit tuttu" veya "FED faizi %0.25 indirdi"
   📅 DUYURU: "TCMB yarın PPK toplantısı yapacak"
   ✅ SONUÇ: "TCMB faizi %50'de sabit bıraktı" veya "TCMB %2.5 puan artırdı"
   - ECB, BoE, BoJ kararları (hem duyuru hem sonuç)

2. KRİTİK EKONOMİK VERİ AÇIKLAMALARI:
   📅 DUYURU: "Enflasyon rakamları bugün saat 10:00'da açıklanacak"
   ✅ SONUÇ: "Ocak enflasyonu %64.77 açıklandı" (tam rakam önemli!)
   📅 DUYURU: "4. çeyrek büyüme verileri yarın açıklanacak"
   ✅ SONUÇ: "Türkiye ekonomisi 3. çeyrekte %3.2 büyüdü"
   - İşsizlik oranı (duyuru + sonuç)
   - Dış ticaret açığı (duyuru + sonuç)
   - GSYİH büyüme (duyuru + sonuç)

3. DÖVIZ/ALTIN REKORLARI (Sadece TARİHİ REKOR!):
   ✅ "Dolar TARİHİ REKOR kırdı: 45.50 TL"
   ✅ "Euro TÜM ZAMANLARIN REKORUNU KIRDI: 48 TL"
   ✅ "Altın gram fiyatı REKOR kırdı: 3.500 TL"
   ❌ "Dolar 43.5 TL seviyesinde" (rekor değilse ALMA!)

4. BORSA KRİTİK HAREKETLER:
   ✅ "BIST 100 %5+ düşüşle 10.000'in altına indi"
   ✅ "BIST 100 TARİHİ REKOR: 12.500 puan"
   ❌ Normal günlük dalgalanmalar (ALMA!)

5. GEOPOLİTİK ŞOKLAR:
   ✅ "ABD Çin'e yeni gümrük vergisi uygulamaya başladı"
   ✅ "OPEC petrol üretimini kısma kararı aldı"
   ✅ "Rusya doğalgaz akışını durdurdu"

6. YASAL DEĞİŞİKLİKLER:
   ✅ "Yeni asgari ücret 20.000 TL olarak açıklandı"
   ✅ "Vergi indirimi yasası meclisten geçti"

❌ BUNLARI ASLA ALMA:
- Genel yorumlar ("Uzmanlar dolar için ne diyor", "Altın yükselişini sürdürüyor")
- BES/emeklilik fon performansları
- Şirket kâr/zarar açıklamaları (bireysel şirketler - Tesla, Apple vs.)
- Banka kampanya/kredi haberleri
- Teknik analiz/tahmin haberleri ("Dolar 50 TL'ye çıkabilir")
- "Altında yükseliş bekleniyor" gibi belirsiz ifadeler
- Suç/mahkeme/magazin
- ESKİ TARİHLİ HABERLER (2025 veya 48 saatten eski)
- Kripto para haberleri (Bitcoin, Ethereum - finansal regülasyon değilse)

═══════════════════════════════════════════
HAM HABERLER ({len(news_list)} adet):
═══════════════════════════════════════════
{numbered_news}

═══════════════════════════════════════════
ÇIKTI FORMATI (SADECE BU!):
═══════════════════════════════════════════

BAYRAM: [VAR/YOK veya isim]
1. [Tam anlaşılır özet - Max 15 kelime - Kesme yok!]
2. [Tam anlaşılır özet - Max 15 kelime - Kesme yok!]

KURALLAR:
✅ Her özet TAM CÜMLE (max 15 kelime ama KESME YOK!)
✅ Duyuru haberlerinde SAAT belirt: "FED bugün 21:00'de faiz kararını açıklayacak"
✅ Sonuç haberlerinde RAKAM belirt: "FED faizi %4.5'te tuttu", "Enflasyon %64.77 açıklandı"
✅ Rekor haberlerinde RAKAM belirt: "Dolar rekor kırdı: 45.50 TL"
✅ Emoji YOK
✅ [Tarih: ...] etiketini ÇIKTI'da gösterme (sadece filtreleme için kullan)
✅ Kritik kelimeler: açıklayacak, açıkladı, karar, rekor, kırdı, arttı, düştü (+ sayı/saat)

❌ Finansal olmayan haberi ATLA
❌ Önemsiz/genel haberi ATLA
❌ ESKİ TARİHLİ haberi ATLA (48 saatten eski)
❌ HİÇBİR kritik haber yoksa: "HABER: YOK"

BAŞKA AÇIKLAMA YAPMA!
"""
        
        logger.info(f"🤖 [GEMİNİ 3 FLASH] {len(news_list)} haber filtreleniyor...")
        
        # 🛡️ GEMİNİ ÇAĞRISI + FALLBACK
        try:
            response = model.generate_content(prompt)
            result = response.text.strip()
            
            # Boş yanıt kontrolü
            if not result or len(result) < 10:
                logger.error("❌ [GEMİNİ] Boş yanıt döndü! Fallback...")
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
            
            # Tam metni al
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
# 🔥 DİNAMİK YARIM MARJ SİSTEMİ (V3.9.3)
# ======================================

def fetch_harem_html() -> Optional[str]:
    """
    Harem sayfasının HTML'ini çeker
    🔥 V3.9: BeautifulSoup ile table parse
    """
    try:
        url = Config.HAREM_PRICE_URL
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        logger.info(f"🕷️ [HAREM HTML] Çekiliyor: {url}")
        response = requests.get(url, headers=headers, timeout=Config.HAREM_FETCH_TIMEOUT)
        response.raise_for_status()
        
        # BeautifulSoup ile parse et
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Tablo kısmını bul
        table = soup.find('table')
        if not table:
            # Alternatif: div class'ları
            table = soup.find_all('div', class_='data')
        
        if table:
            # İlk 5000 karakter (token tasarrufu)
            html_text = str(table)[:5000]
            logger.info(f"✅ [HAREM HTML] {len(html_text)} karakter alındı")
            return html_text
        else:
            logger.error("❌ [HAREM HTML] Tablo bulunamadı!")
            return None
        
    except Exception as e:
        logger.error(f"❌ [HAREM HTML] Hata: {e}")
        return None


def calculate_half_margins_with_gemini(html_data: str, api_prices: Dict) -> Optional[Dict]:
    """
    Gemini'ye HTML verisini göndererek YARIM MARJLARI hesaplat
    🔥 V3.9: GEMİNİ 3 FLASH + Veri besleme + Yarım marj + Gümüş özel
    """
    try:
        if not GEMINI_API_KEY:
            logger.warning("⚠️ GEMINI_API_KEY bulunamadı!")
            return None
        
        genai.configure(api_key=GEMINI_API_KEY)
        
        # 🔥 YENİ MODEL: GEMINI 3 FLASH
        model = genai.GenerativeModel('gemini-3-flash-preview')
        
        prompt = f"""
SEN BİR FİNANS ANALİSTİSİN.

Aşağıda Harem Altın'ın SATIŞ fiyatlarını içeren HTML tablosu var.

HAM VERİ (HTML):
{html_data}

API'den gelen HAM fiyatlar:
- Gram Altın: {api_prices.get('GRA', 0)} ₺
- Çeyrek Altın: {api_prices.get('CEYREKALTIN', 0)} ₺
- Yarım Altın: {api_prices.get('YARIMALTIN', 0)} ₺
- Tam Altın: {api_prices.get('TAMALTIN', 0)} ₺
- Gram Gümüş: {api_prices.get('GUMUS', 0)} ₺

GÖREV:
1. HTML tablosundan Harem SATIŞ fiyatlarını bul
2. Her ürün için MARJ oranını hesapla: (Harem - API) / API × 100
3. HESAPLANAN MARJIN YARISINI AL

ÖZEL KURAL - GÜMÜŞ:
- Gümüş için marjın %75'ini kullan (%100 yerine %75)
- Örnek: Gerçek marj %20 ise → %15 kullan

ÇIKTI FORMATI (sadece bu):
MARJ_GRA: 2.6
MARJ_C22: 0.1
MARJ_YAR: 0.05
MARJ_TAM: 0.0
MARJ_AG: 15.0

HİÇBİR AÇIKLAMA YAPMA, SADECE YUKARI FORMATTA VER!
"""
        
        logger.info("🤖 [GEMİNİ 3 FLASH MARJ] Hesaplama başlıyor...")
        
        response = model.generate_content(prompt)
        result = response.text.strip()
        
        if not result or len(result) < 10:
            logger.error("❌ [GEMİNİ MARJ] Boş yanıt döndü!")
            return None
        
        # Parse et
        margins = {}
        for line in result.split('\n'):
            if 'MARJ_' in line:
                parts = line.split(':')
                if len(parts) == 2:
                    key = parts[0].replace('MARJ_', '').strip()
                    try:
                        value = float(parts[1].strip()) / 100  # %2.6 → 0.026
                        margins[key] = value
                    except ValueError:
                        logger.warning(f"⚠️ [MARJ PARSE] Geçersiz değer: {line}")
                        continue
        
        if not margins:
            logger.error("❌ [GEMİNİ MARJ] Parse edilemedi!")
            return None
        
        logger.info(f"✅ [GEMİNİ 3 FLASH MARJ] {len(margins)} marj hesaplandı: {margins}")
        return margins
        
    except Exception as e:
        logger.error(f"❌ [GEMİNİ MARJ] Hata: {e}")
        return None


def update_dynamic_margins() -> bool:
    """
    Dinamik marjları güncelle (Ayrı job'da çalışır - 00:01)
    🔥 V3.9.3: KALICI BACKUP - margin_last_update TTL=0 (süresiz!)
    """
    try:
        logger.info("💰 [DİNAMİK MARJ] Güncelleme başlıyor...")
        
        # 1. HTML'i çek
        html_data = fetch_harem_html()
        
        if not html_data:
            logger.warning("⚠️ [DİNAMİK MARJ] HTML çekilemedi, eski marjlar kullanılacak")
            return False
        
        # 2. API fiyatlarını al
        try:
            from services.financial_service import fetch_from_v5
            api_data = fetch_from_v5()
            
            if not api_data or 'Rates' not in api_data:
                logger.error("❌ [DİNAMİK MARJ] API verisi alınamadı!")
                return False
            
            api_prices = {
                'GRA': api_data['Rates'].get('GRA', {}).get('Selling', 0),
                'CEYREKALTIN': api_data['Rates'].get('CEYREKALTIN', {}).get('Selling', 0),
                'YARIMALTIN': api_data['Rates'].get('YARIMALTIN', {}).get('Selling', 0),
                'TAMALTIN': api_data['Rates'].get('TAMALTIN', {}).get('Selling', 0),
                'GUMUS': api_data['Rates'].get('GUMUS', {}).get('Selling', 0),
            }
            
            logger.info(f"✅ [DİNAMİK MARJ] API fiyatları: GRA={api_prices['GRA']}, AG={api_prices['GUMUS']}")
            
        except Exception as api_error:
            logger.error(f"❌ [DİNAMİK MARJ] API çağrısı başarısız: {api_error}")
            return False
        
        # 3. Gemini ile marjları hesapla
        margins = calculate_half_margins_with_gemini(html_data, api_prices)
        
        if not margins:
            logger.warning("⚠️ [DİNAMİK MARJ] Gemini hesaplayamadı, eski marjlar kullanılacak")
            return False
        
        # 4. Redis'e kaydet (24 saat TTL - bugünkü marjlar)
        margin_key = Config.CACHE_KEYS.get('dynamic_half_margins', 'dynamic:half_margins')
        set_cache(margin_key, margins, ttl=86400)
        
        # 5. 🔥 KALICI BACKUP (TTL=0, süresiz!) - En son başarılı marjlar
        update_key = Config.CACHE_KEYS.get('margin_last_update', 'margin:last_update')
        set_cache(update_key, {
            'timestamp': time.time(),
            'margins': margins
        }, ttl=0)  # ✅ SÜRESIZ! Fallback için her zaman hazır!
        
        logger.info(f"✅ [DİNAMİK MARJ] Kaydedildi: {margins}")
        logger.info(f"💾 [DİNAMİK MARJ] KALICI BACKUP kaydedildi (TTL=0)")
        return True
        
    except Exception as e:
        logger.error(f"❌ [DİNAMİK MARJ] Beklenmeyen hata: {e}")
        return False


def get_dynamic_margins() -> Dict[str, float]:
    """
    🔥 V3.9.3: AKILLI FALLBACK + BOOTSTRAP
    
    ÖNCEKİ SORUN (V3.9.2):
    - Gemini çökerse → Config'deki sabit marjlar kullanılıyordu
    - Ani fiyat değişimi → Alarmlar patlar, kullanıcılar şaşırır!
    
    YENİ ÇÖZÜM (V3.9.3):
    - Gemini çökerse → En son başarılı marjları kullan (smooth geçiş)
    - İlk kurulumda → HEMEN Gemini'yi çağır (BOOTSTRAP)
    
    FALLBACK SIRASI:
    1. Redis (bugünkü Gemini marjları) → EN GÜNCEL ✅
    2. margin_last_update (en son başarılı) → SMOOTH FALLBACK ✅
    3. BOOTSTRAP (ilk kurulum) → HEMEN GEMİNİ ÇAĞIR! ✅
    
    Returns:
        Dict: {"GRA": 0.026, "C22": 0.001, ...}
    """
    # 1️⃣ BUGÜNKÜ GEMİNİ MARJLARINI DENE
    dynamic_margins = get_cache(Config.CACHE_KEYS.get('dynamic_half_margins', 'dynamic:half_margins'))
    
    if dynamic_margins and isinstance(dynamic_margins, dict):
        logger.debug(f"✅ [DİNAMİK MARJ] Bugünkü Gemini marjları: {len(dynamic_margins)} marj")
        return dynamic_margins
    
    # 2️⃣ EN SON BAŞARILI MARJLARI AL
    last_successful_key = Config.CACHE_KEYS.get('margin_last_update', 'margin:last_update')
    last_successful = get_cache(last_successful_key)
    
    if last_successful and isinstance(last_successful, dict):
        margins = last_successful.get('margins')
        timestamp = last_successful.get('timestamp', 0)
        
        if margins and isinstance(margins, dict):
            # Kaç gün önce başarılıydı?
            days_ago = (time.time() - timestamp) / 86400
            
            logger.warning(
                f"⚠️ [DİNAMİK MARJ FALLBACK] Gemini çalışmıyor! "
                f"En son başarılı marjlar kullanılıyor ({days_ago:.1f} gün önce)"
            )
            
            return margins  # ✅ SMOOTH FALLBACK!
    
    # 3️⃣ 🔥 HİÇBİR ŞEY YOK → BOOTSTRAP (İLK KURULUM!)
    logger.error(
        "🔴 [DİNAMİK MARJ BOOTSTRAP] Marj yok! "
        "HEMEN Gemini çağrılıyor..."
    )
    
    # 🔥 HEMEN Gemini'yi çağır ve marjları çek!
    bootstrap_success = update_dynamic_margins()
    
    if bootstrap_success:
        # Başarılı olduysa, yeni marjları al
        fresh_margins = get_cache(Config.CACHE_KEYS.get('dynamic_half_margins', 'dynamic:half_margins'))
        
        if fresh_margins:
            logger.info("✅ [DİNAMİK MARJ BOOTSTRAP] Gemini başarılı! Marjlar hazır!")
            return fresh_margins
    
    # 🔥 BOOTSTRAP BAŞARISIZ → VARSAYILAN MARJ (0.0)
    logger.critical(
        "💣 [DİNAMİK MARJ BOOTSTRAP] Gemini başarısız! "
        "Varsayılan marj (0.0) kullanılıyor - FİYATLAR HAM!"
    )
    
    # 🔥 Tüm varlıklar için 0.0 marj döndür (Ham fiyat gibi)
    fallback_margins = {}
    
    # Dövizler
    currencies = [
        "USD", "EUR", "GBP", "CHF", "CAD", "AUD", "RUB",
        "SAR", "AED", "KWD", "BHD", "OMR", "QAR",
        "CNY", "SEK", "NOK", "PLN", "RON", "CZK",
        "EGP", "RSD", "HUF", "BAM"
    ]
    for code in currencies:
        fallback_margins[code] = 0.0
    
    # Altınlar
    for code in ["GRA", "C22", "YAR", "TAM", "CUM", "ATA", "HAS"]:
        fallback_margins[code] = 0.0
    
    # Gümüş
    fallback_margins["AG"] = 0.0
    fallback_margins["GUMUS"] = 0.0
    
    logger.warning(f"⚠️ [DİNAMİK MARJ BOOTSTRAP] Fallback: {len(fallback_margins)} marj (0.0)")
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


# ======================================
# 🕐 BAYRAM TTL - Gece 03:00'e kadar
# ======================================

def calculate_bayram_ttl() -> int:
    """
    Bayram mesajı için TTL hesapla
    Gece 03:00'e kadar geçerli (vardiya değişiminden sonra temizlensin)
    """
    now = datetime.now()
    
    # Yarın saat 03:00
    tomorrow_3am = (now + timedelta(days=1)).replace(hour=3, minute=0, second=0, microsecond=0)
    
    # Şu andan yarın 03:00'e kadar kalan saniye
    ttl = int((tomorrow_3am - now).total_seconds())
    
    logger.debug(f"🕐 [BAYRAM TTL] {ttl} saniye (yarın 03:00'e kadar)")
    return ttl


def bootstrap_news_system() -> bool:
    """
    İlk çalıştırma bootstrap
    🔒 RACE CONDITION FIX: Lock mekanizması ile aynı anda sadece 1 bootstrap
    🐛 V3.9.1 FIX: Boş liste kontrolü düzeltildi
    💰 V3.9.2 FIX: Bootstrap dinamik marj güncellemez (sadece haberler)
    """
    try:
        current_hour = datetime.now().hour
        
        if 0 <= current_hour < 12:
            cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
            shift_name = "SABAH"
            shift_type = "morning"
            prepare_func = prepare_morning_shift
        else:
            cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
            shift_name = "AKŞAM"
            shift_type = "evening"
            prepare_func = prepare_evening_shift
        
        # 🔒 LOCK: Aynı vardiya için eş zamanlı bootstrap engelle
        with _bootstrap_lock:
            # Başka thread bootstrap yapıyor mu?
            if _bootstrap_in_progress[shift_type]:
                logger.info(f"ℹ️ [BOOTSTRAP] {shift_name} vardiyası zaten hazırlanıyor (başka thread), atlanıyor...")
                return False
            
            # Cache'de veri var mı?
            existing_data = get_cache(cache_key)
            if existing_data is not None:
                logger.info(f"✅ [BOOTSTRAP] {shift_name} vardiyası hazır")
                return False
            
            # Bootstrap başlıyor
            _bootstrap_in_progress[shift_type] = True
            logger.warning(f"⚠️ [BOOTSTRAP] {shift_name} vardiyası boş! Doldurma başlıyor...")
        
        # 🔓 Lock dışında prepare yap
        try:
            success = prepare_func()
            
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


def prepare_morning_shift() -> bool:
    """
    SABAH VARDİYASI (00:00 - 12:00)
    🔥 V3.9.2: Dinamik marj güncelleme KALDIRILDI (ayrı job'da yapılıyor - 00:01)
    """
    try:
        logger.info("🌅 [SABAH VARDİYASI] Hazırlık başlıyor...")
        
        # 💰 MARJ GÜNCELLEME KALDIRILDI - Artık ayrı job'da (00:01)
        
        # 1. Haberleri topla
        news_list = fetch_all_news()
        
        if not news_list:
            logger.warning("⚠️ [SABAH VARDİYASI] Haber bulunamadı!")
            cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
            set_cache(cache_key, [], ttl=43200)
            
            # Son güncelleme kaydı
            update_key = Config.CACHE_KEYS.get('news_last_update', 'news:last_update')
            set_cache(update_key, {
                'shift': 'morning',
                'timestamp': time.time(),
                'news_count': 0,
                'bayram': 'yok'
            }, ttl=86400)
            
            return True
        
        # 2. 🔥 Vardiyalar arası dedup - Daha önce gösterilenleri filtrele
        fresh_news = filter_already_shown(news_list)
        
        if not fresh_news:
            logger.warning("⚠️ [SABAH VARDİYASI] Tüm haberler daha önce gösterilmiş!")
            cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
            set_cache(cache_key, [], ttl=43200)
            
            # Son güncelleme kaydı
            update_key = Config.CACHE_KEYS.get('news_last_update', 'news:last_update')
            set_cache(update_key, {
                'shift': 'morning',
                'timestamp': time.time(),
                'news_count': 0,
                'bayram': 'yok'
            }, ttl=86400)
            
            return True
        
        # 3. Gemini filtrele
        summaries, bayram_msg = summarize_news_batch(fresh_news)
        
        if not summaries:
            logger.warning("⚠️ [SABAH VARDİYASI] Kritik haber yok")
            cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
            set_cache(cache_key, [], ttl=43200)
            
            # 🔥 Bayram kaydet (varsa)
            if bayram_msg:
                bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
                bayram_ttl = calculate_bayram_ttl()
                set_cache(bayram_key, bayram_msg, ttl=bayram_ttl)
                logger.info(f"🏦 [SABAH VARDİYASI] Bayram kaydedildi: {bayram_msg}")
            
            # Son güncelleme kaydı
            update_key = Config.CACHE_KEYS.get('news_last_update', 'news:last_update')
            set_cache(update_key, {
                'shift': 'morning',
                'timestamp': time.time(),
                'news_count': 0,
                'bayram': bayram_msg if bayram_msg else 'yok'
            }, ttl=86400)
            
            return True
        
        # 4. Bayram kaydet
        if bayram_msg:
            bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
            bayram_ttl = calculate_bayram_ttl()
            set_cache(bayram_key, bayram_msg, ttl=bayram_ttl)
            logger.info(f"🏦 [SABAH VARDİYASI] Bayram kaydedildi: {bayram_msg}")
        
        # 5. Planla
        schedule = plan_shift_schedule(summaries, start_hour=0, end_hour=12)
        
        # 6. Cache'e kaydet
        cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
        set_cache(cache_key, schedule, ttl=43200)
        
        # 7. 🔥 Gösterilen haberleri geçmişe kaydet
        save_shown_news(summaries)
        
        # 8. Son güncelleme kaydı
        update_key = Config.CACHE_KEYS.get('news_last_update', 'news:last_update')
        set_cache(update_key, {
            'shift': 'morning',
            'timestamp': time.time(),
            'news_count': len(schedule),
            'bayram': bayram_msg if bayram_msg else 'yok'
        }, ttl=86400)
        
        logger.info(f"✅ [SABAH VARDİYASI] {len(schedule)} kritik haber hazır!")
        return True
        
    except Exception as e:
        logger.error(f"❌ [SABAH VARDİYASI] Hata: {e}")
        return False


def prepare_evening_shift() -> bool:
    """
    AKŞAM VARDİYASI (12:00 - 00:00)
    🔥 V3.9: Vardiyalar arası dedup (Marj güncellemesi YOK)
    """
    try:
        logger.info("🌆 [AKŞAM VARDİYASI] Hazırlık başlıyor...")
        
        # 1. Haberleri topla
        news_list = fetch_all_news()
        
        if not news_list:
            logger.warning("⚠️ [AKŞAM VARDİYASI] Haber bulunamadı!")
            cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
            set_cache(cache_key, [], ttl=43200)
            return True
        
        # 2. 🔥 Vardiyalar arası dedup - Daha önce gösterilenleri filtrele
        fresh_news = filter_already_shown(news_list)
        
        if not fresh_news:
            logger.warning("⚠️ [AKŞAM VARDİYASI] Tüm haberler daha önce gösterilmiş!")
            cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
            set_cache(cache_key, [], ttl=43200)
            return True
        
        # 3. Gemini filtrele
        summaries, bayram_msg = summarize_news_batch(fresh_news)
        
        if not summaries:
            logger.warning("⚠️ [AKŞAM VARDİYASI] Kritik haber yok")
            cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
            set_cache(cache_key, [], ttl=43200)
            return True
        
        # 4. Bayram kaydet
        if bayram_msg:
            bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
            bayram_ttl = calculate_bayram_ttl()
            set_cache(bayram_key, bayram_msg, ttl=bayram_ttl)
            logger.info(f"🏦 [AKŞAM VARDİYASI] Bayram kaydedildi: {bayram_msg}")
        
        # 5. Planla
        schedule = plan_shift_schedule(summaries, start_hour=12, end_hour=24)
        
        # 6. Cache'e kaydet
        cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
        set_cache(cache_key, schedule, ttl=43200)
        
        # 7. 🔥 Gösterilen haberleri geçmişe kaydet
        save_shown_news(summaries)
        
        # 8. Son güncelleme kaydı
        update_key = Config.CACHE_KEYS.get('news_last_update', 'news:last_update')
        set_cache(update_key, {
            'shift': 'evening',
            'timestamp': time.time(),
            'news_count': len(schedule),
            'bayram': bayram_msg if bayram_msg else 'yok'
        }, ttl=86400)
        
        logger.info(f"✅ [AKŞAM VARDİYASI] {len(schedule)} kritik haber hazır!")
        return True
        
    except Exception as e:
        logger.error(f"❌ [AKŞAM VARDİYASI] Hata: {e}")
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
    print("🧪 News Manager V3.9.3 ULTIMATE + SMART MARGIN FALLBACK - GEMINI 3 FLASH - Test\n")
    
    print("1️⃣ HABER TOPLAMA (GNews 3 gün + NewsData):")
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
        print(f"   ✅ {len(fresh_news)} yeni haber (tekrar filtrelendi)\n")
    
    if fresh_news:
        print("3️⃣ ULTRA SIKI FİLTRE + 48 SAAT (GEMINI 3 FLASH):")
        summaries, bayram_msg = summarize_news_batch(fresh_news)
        print(f"   ✅ {len(summaries)} KRİTİK haber filtrelendi\n")
        
        if bayram_msg:
            print(f"   🏦 BAYRAM: {bayram_msg}\n")
        
        if summaries:
            print("   Kritik haberler:")
            for i, summary in enumerate(summaries, 1):
                print(f"   {i}. {summary}")
        else:
            print("   ℹ️ Bugün kritik haber yok")
        print()
    
    print("4️⃣ DİNAMİK MARJ SİSTEMİ (SMART FALLBACK + BOOTSTRAP):")
    margins = get_dynamic_margins()
    print(f"   ✅ {len(margins)} marj alındı!\n")
    if margins:
        print(f"   İlk 5 marj: {dict(list(margins.items())[:5])}\n")
    
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
