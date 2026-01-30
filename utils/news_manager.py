"""
News Manager - GÜNLÜK HABER SİSTEMİ V3.3 PROD-READY 📰🚀
=============================================
✅ ULTRA SIKI FİLTRE: Sadece kritik finansal olaylar
✅ DUYURU + SONUÇ: Hem "açıklanacak" hem "açıklandı" 
✅ GELIŞMIŞ DEDUP: Daha akıllı tekrar önleme
✅ GÜÇLÜ FALLBACK: Gemini patlarsa da sistem ayakta
✅ RATE-LIMIT KORUMA: Retry + exponential backoff
✅ BAYRAM MANTIKLI TTL: Gece 03:00'e kadar geçerli
"""

import os
import logging
import requests
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import google.generativeai as genai
from difflib import SequenceMatcher

from utils.cache import get_cache, set_cache
from config import Config

logger = logging.getLogger(__name__)

GNEWS_API_KEY = os.getenv('GNEWS_API_KEY')
NEWSDATA_API_KEY = os.getenv('NEWSDATA_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')


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


def fetch_gnews(max_results: int = 20) -> List[str]:
    """GNews API'den ekonomi haberleri çeker - RETRY KORUMASLI"""
    try:
        if not GNEWS_API_KEY:
            logger.warning("⚠️ GNEWS_API_KEY bulunamadı!")
            return []
        
        url = (
            f"https://gnews.io/api/v4/search"
            f"?q=(\"merkez bankası\" OR \"faiz kararı\" OR \"faiz\" OR \"enflasyon\" OR \"TCMB\" OR \"FED\" OR \"ECB\" OR \"büyüme\" OR \"GSYİH\")"
            f"&lang=tr"
            f"&country=tr"
            f"&sortby=publishedAt"
            f"&max=20"
            f"&apikey={GNEWS_API_KEY}"
        )
        
        logger.info("📡 [GNEWS] Haberler çekiliyor...")
        data = fetch_with_retry(url)
        
        if not data or data.get('totalArticles', 0) == 0:
            logger.warning("⚠️ [GNEWS] Haber bulunamadı")
            return []
        
        articles = data.get('articles', [])[:max_results]
        news_list = []
        
        for article in articles:
            title = article.get('title', '').strip()
            description = article.get('description', '').strip()
            full_text = f"{title}. {description}" if description else title
            
            if full_text and len(full_text) > 15:
                news_list.append(full_text)
        
        logger.info(f"✅ [GNEWS] {len(news_list)} haber alındı")
        return news_list
        
    except Exception as e:
        logger.error(f"❌ [GNEWS] Beklenmeyen hata: {e}")
        return []


def fetch_newsdata(max_results: int = 20) -> List[str]:
    """NewsData API'den ekonomi haberleri çeker - RETRY KORUMASLI"""
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
            title = article.get('title', '').strip()
            description = article.get('description', '').strip()
            full_text = f"{title}. {description}" if description else title
            
            if full_text and len(full_text) > 15:
                news_list.append(full_text)
        
        logger.info(f"✅ [NEWSDATA] {len(news_list)} haber alındı")
        return news_list
        
    except Exception as e:
        logger.error(f"❌ [NEWSDATA] Beklenmeyen hata: {e}")
        return []


def fetch_all_news() -> List[str]:
    """Her iki API'den haberleri çeker ve GELİŞMİŞ DEDUP ile birleştirir"""
    logger.info("📰 [NEWS] Tüm kaynaklardan haber toplama başlıyor...")
    
    gnews_list = fetch_gnews(max_results=20)
    newsdata_list = fetch_newsdata(max_results=20)
    
    all_news = gnews_list + newsdata_list
    
    # Gelişmiş dedup
    unique_news = deduplicate_news(all_news)
    
    logger.info(f"✅ [NEWS] Toplam {len(unique_news)} benzersiz haber toplandı")
    return unique_news[:30]


# ======================================
# 🛡️ GÜÇLÜ FALLBACK İLE GEMİNİ FİLTRE
# ======================================

def summarize_news_batch(news_list: List[str]) -> Tuple[List[str], Optional[str]]:
    """ULTRA SIKI FİLTRE - Gemini patlarsa da sistem ayakta kalır"""
    try:
        if not GEMINI_API_KEY:
            logger.warning("⚠️ GEMINI_API_KEY bulunamadı! Fallback modu...")
            return [], None
        
        if not news_list:
            logger.warning("⚠️ [GEMİNİ] Özetlenecek haber yok!")
            return [], None
        
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        numbered_news = '\n'.join([f"{i+1}. {news}" for i, news in enumerate(news_list)])
        today = datetime.now().strftime('%d %B %Y, %A')
        current_time = datetime.now().strftime('%H:%M')
        
        prompt = f"""
SEN BİR FİNANS EDİTÖRÜSÜN. Sadece PİYASAYI ETKİLEYEN kritik haberleri seç.

BUGÜN: {today}, SAAT: {current_time}

═══════════════════════════════════════════
GÖREV 1 - BAYRAM KONTROLÜ
═══════════════════════════════════════════
Bugün Türkiye'de resmi tatil/bayram var mı?
VARSA → "BAYRAM: [tam isim]" | YOKSA → "BAYRAM: YOK"

═══════════════════════════════════════════
GÖREV 2 - ULTRA SIKI FİLTRE
═══════════════════════════════════════════

✅ SADECE ŞU TİP HABERLERİ AL:

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

3. DÖVIZ REKORLARI (Sadece TARİHİ REKOR!):
   ✅ "Dolar TARİHİ REKOR kırdı: 45.50 TL"
   ✅ "Euro TÜM ZAMANLARIN REKORUNU KIRDI: 48 TL"
   ❌ "Dolar 43.5 TL seviyesinde" (rekor değilse ALMA!)

4. BORSA KRİTİK HAREKETLER:
   ✅ "BIST 100 %7 düşüşle 11.000'in altına indi"
   ✅ "BIST 100 TARİHİ REKOR: 12.500 puan"

5. GEOPOLİTİK ŞOKLAR:
   ✅ "ABD Çin'e yeni gümrük vergisi uygulamaya başladı"
   ✅ "OPEC petrol üretimini kısma kararı aldı"

❌ BUNLARI ASLA ALMA:
- Genel dolar/altın yorumları ("Uzmanlar dolar için ne diyor", "Altın yükselişini sürdürüyor")
- BES/emeklilik fon performansları
- Şirket kâr/zarar açıklamaları (bireysel şirketler)
- Banka kampanya/kredi haberleri
- Teknik analiz/tahmin haberleri
- "Altında yükseliş bekleniyor" gibi belirsiz ifadeler
- Suç/mahkeme/magazin

═══════════════════════════════════════════
HAM HABERLER ({len(news_list)} adet):
═══════════════════════════════════════════
{numbered_news}

═══════════════════════════════════════════
ÇIKTI FORMATI (SADECE BU!):
═══════════════════════════════════════════

BAYRAM: [VAR/YOK]
1. [Tam anlaşılır özet - Max 15 kelime - Kesme yok!]
2. [Tam anlaşılır özet - Max 15 kelime - Kesme yok!]

KURALLAR:
✅ Her özet TAM CÜMLE (max 15 kelime ama KESME YOK!)
✅ Duyuru haberlerinde SAAT belirt: "FED bugün 21:00'de faiz kararını açıklayacak"
✅ Sonuç haberlerinde RAKAM belirt: "FED faizi %4.5'te tuttu", "Enflasyon %64.77 açıklandı"
✅ Emoji YOK
✅ Kritik kelimeler: açıklayacak, açıkladı, karar, rekor, kırdı, arttı, düştü (+ sayı/saat)

❌ Finansal olmayan haberi ATLA
❌ Önemsiz/genel haberi ATLA  
❌ HİÇBİR kritik haber yoksa: "HABER: YOK"

BAŞKA AÇIKLAMA YAPMA!
"""
        
        logger.info(f"🤖 [GEMİNİ] {len(news_list)} haber filtreleniyor...")
        
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
        
        logger.info(f"✅ [GEMİNİ] {len(summaries)} kritik haber filtrelendi")
        
        if not summaries:
            logger.warning("⚠️ [GEMİNİ] Bugün kritik haber yok")
            return [], bayram_msg
        
        return summaries, bayram_msg
        
    except Exception as e:
        logger.error(f"❌ [GEMİNİ] Beklenmeyen hata: {e}")
        return [], None


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
    """İlk çalıştırma bootstrap"""
    try:
        current_hour = datetime.now().hour
        
        if 0 <= current_hour < 12:
            cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
            shift_name = "SABAH"
            prepare_func = prepare_morning_shift
        else:
            cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
            shift_name = "AKŞAM"
            prepare_func = prepare_evening_shift
        
        existing_data = get_cache(cache_key)
        
        if existing_data:
            logger.info(f"✅ [BOOTSTRAP] {shift_name} vardiyası hazır")
            return False
        
        logger.warning(f"⚠️ [BOOTSTRAP] {shift_name} vardiyası boş! Doldurma başlıyor...")
        
        success = prepare_func()
        
        if success:
            logger.info(f"🚀 [BOOTSTRAP] {shift_name} vardiyası dolduruldu!")
            return True
        else:
            logger.error(f"❌ [BOOTSTRAP] {shift_name} vardiyası doldurulamadı!")
            return False
        
    except Exception as e:
        logger.error(f"❌ [BOOTSTRAP] Hata: {e}")
        return False


def prepare_morning_shift() -> bool:
    """SABAH VARDİYASI (00:00 - 12:00)"""
    try:
        logger.info("🌅 [SABAH VARDİYASI] Hazırlık başlıyor...")
        
        news_list = fetch_all_news()
        
        if not news_list:
            logger.warning("⚠️ [SABAH VARDİYASI] Haber bulunamadı!")
            cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
            set_cache(cache_key, [], ttl=43200)
            return True
        
        summaries, bayram_msg = summarize_news_batch(news_list)
        
        if not summaries:
            logger.warning("⚠️ [SABAH VARDİYASI] Kritik haber yok")
            cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
            set_cache(cache_key, [], ttl=43200)
            return True
        
        if bayram_msg:
            bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
            bayram_ttl = calculate_bayram_ttl()
            set_cache(bayram_key, bayram_msg, ttl=bayram_ttl)
            logger.info(f"🏦 [SABAH VARDİYASI] Bayram kaydedildi: {bayram_msg}")
        
        schedule = plan_shift_schedule(summaries, start_hour=0, end_hour=12)
        
        cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
        set_cache(cache_key, schedule, ttl=43200)
        
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
    """AKŞAM VARDİYASI (12:00 - 00:00)"""
    try:
        logger.info("🌆 [AKŞAM VARDİYASI] Hazırlık başlıyor...")
        
        news_list = fetch_all_news()
        
        if not news_list:
            logger.warning("⚠️ [AKŞAM VARDİYASI] Haber bulunamadı!")
            cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
            set_cache(cache_key, [], ttl=43200)
            return True
        
        summaries, bayram_msg = summarize_news_batch(news_list)
        
        if not summaries:
            logger.warning("⚠️ [AKŞAM VARDİYASI] Kritik haber yok")
            cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
            set_cache(cache_key, [], ttl=43200)
            return True
        
        if bayram_msg:
            bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
            bayram_ttl = calculate_bayram_ttl()
            set_cache(bayram_key, bayram_msg, ttl=bayram_ttl)
            logger.info(f"🏦 [AKŞAM VARDİYASI] Bayram kaydedildi: {bayram_msg}")
        
        schedule = plan_shift_schedule(summaries, start_hour=12, end_hour=24)
        
        cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
        set_cache(cache_key, schedule, ttl=43200)
        
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
    print("🧪 News Manager V3.3 PROD-READY - Test\n")
    
    print("1️⃣ HABER TOPLAMA:")
    news_list = fetch_all_news()
    print(f"   ✅ {len(news_list)} haber toplandı\n")
    
    if news_list:
        print("   İlk 3 haber:")
        for i, news in enumerate(news_list[:3], 1):
            print(f"   {i}. {news[:100]}...")
        print()
    
    if news_list:
        print("2️⃣ ULTRA SIKI FİLTRE:")
        summaries, bayram_msg = summarize_news_batch(news_list)
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
    
    if summaries:
        print("3️⃣ PLANLAMA:")
        schedule = plan_shift_schedule(summaries, start_hour=0, end_hour=12)
        print(f"   ✅ {len(schedule)} slot\n")
        
        for slot in schedule[:3]:
            print(f"   {slot['start']}-{slot['end']}: {slot['text']}")
        print()
    
    print("4️⃣ BOOTSTRAP:")
    bootstrap_success = bootstrap_news_system()
    print(f"   {'✅ Başarılı' if bootstrap_success else 'ℹ️ Gerek yok'}\n")
    
    print("5️⃣ BANNER:")
    banner = get_current_news_banner()
    if banner:
        print(f"   ✅ {banner}\n")
    else:
        print("   ℹ️ Bugün kritik haber yok\n")


if __name__ == "__main__":
    test_news_manager()
