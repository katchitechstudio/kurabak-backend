"""
News Manager - GÜNLÜK HABER SİSTEMİ V3.1 📰🚀🏦
=============================================
✅ ULTRA SIKI FİLTRE: Sadece piyasa hareketlendiren haberler
✅ KESME SORUNU: Tam metin garantisi
"""

import os
import logging
import requests
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import google.generativeai as genai

from utils.cache import get_cache, set_cache
from config import Config

logger = logging.getLogger(__name__)

# ======================================
# API ANAHTARLARI
# ======================================

GNEWS_API_KEY = os.getenv('GNEWS_API_KEY')
NEWSDATA_API_KEY = os.getenv('NEWSDATA_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# ======================================
# HABER TOPLAMA FONKSİYONLARI
# ======================================

def fetch_gnews(max_results: int = 15) -> List[str]:
    """GNews API'den ekonomi haberleri çeker"""
    try:
        if not GNEWS_API_KEY:
            logger.warning("⚠️ GNEWS_API_KEY bulunamadı!")
            return []
        
        # Daha spesifik arama terimleri
        url = (
            f"https://gnews.io/api/v4/search"
            f"?q=(\"merkez bankası\" OR \"faiz kararı\" OR \"dolar\" OR \"borsa\" OR \"enflasyon\" OR \"TCMB\" OR \"FED\")"
            f"&lang=tr"
            f"&country=tr"
            f"&sortby=publishedAt"
            f"&max=15"
            f"&apikey={GNEWS_API_KEY}"
        )
        
        logger.info("📡 [GNEWS] Haberler çekiliyor...")
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get('totalArticles', 0) == 0:
            logger.warning("⚠️ [GNEWS] Haber bulunamadı")
            return []
        
        articles = data.get('articles', [])[:max_results]
        news_list = []
        
        for article in articles:
            title = article.get('title', '').strip()
            description = article.get('description', '').strip()
            
            # Tam metni al (title + description birleştir)
            full_text = f"{title}. {description}" if description else title
            
            if full_text and len(full_text) > 15:
                news_list.append(full_text)
        
        logger.info(f"✅ [GNEWS] {len(news_list)} haber alındı")
        return news_list
        
    except Exception as e:
        logger.error(f"❌ [GNEWS] Hata: {e}")
        return []


def fetch_newsdata(max_results: int = 15) -> List[str]:
    """NewsData API'den ekonomi haberleri çeker"""
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
            f"&q=(merkez AND bankası) OR (faiz AND kararı) OR TCMB OR FED OR enflasyon"
        )
        
        logger.info("📡 [NEWSDATA] Haberler çekiliyor...")
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get('status') != 'success':
            logger.warning(f"⚠️ [NEWSDATA] Hata: {data.get('status')}")
            return []
        
        results = data.get('results', [])[:max_results]
        news_list = []
        
        for article in results:
            title = article.get('title', '').strip()
            description = article.get('description', '').strip()
            
            # Tam metni al
            full_text = f"{title}. {description}" if description else title
            
            if full_text and len(full_text) > 15:
                news_list.append(full_text)
        
        logger.info(f"✅ [NEWSDATA] {len(news_list)} haber alındı")
        return news_list
        
    except Exception as e:
        logger.error(f"❌ [NEWSDATA] Hata: {e}")
        return []


def fetch_all_news() -> List[str]:
    """Her iki API'den haberleri çeker ve birleştirir"""
    logger.info("📰 [NEWS] Tüm kaynaklardan haber toplama başlıyor...")
    
    gnews_list = fetch_gnews(max_results=15)
    newsdata_list = fetch_newsdata(max_results=15)
    
    all_news = gnews_list + newsdata_list
    
    # Tekrar edenleri temizle
    unique_news = []
    seen_keywords = set()
    
    for news in all_news:
        keywords = ' '.join(news.split()[:7]).lower()
        
        if keywords not in seen_keywords:
            unique_news.append(news)
            seen_keywords.add(keywords)
    
    logger.info(f"✅ [NEWS] Toplam {len(unique_news)} benzersiz haber toplandı")
    return unique_news[:25]  # Daha fazla haber


# ======================================
# 🔥 YENİ ULTRA SIKI FİLTRE
# ======================================

def summarize_news_batch(news_list: List[str]) -> Tuple[List[str], Optional[str]]:
    """
    ULTRA SIKI FİLTRE - Sadece piyasa hareketlendiren kritik haberler
    """
    try:
        if not GEMINI_API_KEY:
            logger.warning("⚠️ GEMINI_API_KEY bulunamadı!")
            return [], None
        
        if not news_list:
            logger.warning("⚠️ [GEMİNİ] Özetlenecek haber yok!")
            return [], None
        
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        numbered_news = '\n'.join([f"{i+1}. {news}" for i, news in enumerate(news_list)])
        today = datetime.now().strftime('%d %B %Y, %A')
        
        # 🔥 YENİ ULTRA SIKI PROMPT
        prompt = f"""
SEN BİR FİNANS EDİTÖRÜSÜN. GÖREV: Sadece PİYASAYI ETKİLEYECEK kritik haberleri seç.

BUGÜN: {today}

═══════════════════════════════════════════
GÖREV 1 - BAYRAM KONTROLÜ
═══════════════════════════════════════════
Bugün Türkiye'de resmi tatil/bayram var mı?
- VARSA → "BAYRAM: [tam isim]" 
- YOKSA → "BAYRAM: YOK"

═══════════════════════════════════════════
GÖREV 2 - ULTRA SIKI FİLTRE (SADECE BUNLAR!)
═══════════════════════════════════════════

✅ SADECE ŞUNLARI AL (PİYASAYI ETKİLEYEN):

1. MERKEZ BANKASI KARARLARI:
   - FED faiz kararı (kesildi/artırıldı/sabit kaldı)
   - TCMB faiz kararı ve PPK toplantısı
   - ECB, BoE, BoJ kararları
   
2. KRİTİK EKONOMİK VERİLER:
   - Enflasyon rakamları (TÜFE, ÜFE açıklandı)
   - Büyüme rakamları (GSYİH, büyüme hızı)
   - İşsizlik oranı
   - Dış ticaret açığı/fazlası
   
3. DÖVIZ REKORLARI (Sadece rekor kırarsa!):
   - Dolar TARİHİ REKOR kırdı (örn: "45 TL'yi aştı")
   - Euro REKOR seviyede
   
4. BORSA KRİTİK HAREKETLER:
   - BIST 100 %5+ düşüş/yükseliş
   - BIST rekor kırdı
   
5. GEOPOLİTİK ŞOKLAR:
   - Savaş başladı/bitti
   - Ambargo ilan edildi
   - Ticaret anlaşması imzalandı

❌ BUNLARI ASLA ALMA:

- Genel dolar/altın haberleri ("Dolar yükselişte", "Altın fiyatları arttı")
- BES/emeklilik fon haberleri
- Şirket performansları ("X şirketi kâr açıkladı")
- Analist yorumları ("Uzmanlar dolar için ne diyor")
- Banka kampanyaları
- Teknik analiz haberleri
- Genel tavsiye haberleri
- Suç/mahkeme haberleri
- Magazin/spor

═══════════════════════════════════════════
HAM HABERLER ({len(news_list)} adet):
═══════════════════════════════════════════
{numbered_news}

═══════════════════════════════════════════
FORMAT (SADECE BU FORMATI KULLAN!):
═══════════════════════════════════════════

BAYRAM: [VAR/YOK]
1. [Kısa ama anlaşılır özet - Max 12 kelime]
2. [Kısa ama anlaşılır özet - Max 12 kelime]

KURALLAR:
✅ Her özet max 12 kelime (kesme yok!)
✅ Tam cümle olsun (anlaşılır)
✅ Emoji YOK
✅ Sayı varsa birim ekle ("FED faizi %4.5'te sabit tuttu")
✅ Kritik kelimeler: karar, açıklandı, rekor, kırdı, arttı/düştü (+ rakam)

❌ Finansal olmayan haberi ATLA
❌ Genel/önemsiz haberi ATLA
❌ Eğer HİÇBİR kritik haber yoksa: "HABER: YOK"

BAŞKA AÇIKLAMA YAPMA!
"""
        
        logger.info(f"🤖 [GEMİNİ] {len(news_list)} haber ULTRA SIKI filtreleniyor...")
        
        response = model.generate_content(prompt)
        result = response.text.strip()
        
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
                clean_line = clean_line.split('. ', 1)[1]
            
            # Tam metni al (kesme yok!)
            if clean_line and len(clean_line) > 10:
                summaries.append(clean_line)
        
        logger.info(f"✅ [GEMİNİ] {len(summaries)} kritik haber filtrelendi")
        
        # Fallback: Eğer hiç haber yoksa, boş döndür
        if not summaries:
            logger.warning("⚠️ [GEMİNİ] Bugün kritik haber yok")
            return [], bayram_msg
        
        return summaries, bayram_msg
        
    except Exception as e:
        logger.error(f"❌ [GEMİNİ] Hata: {e}")
        return [], None


# ======================================
# VARDİYA PLANLAMA (Aynı)
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
            "text": news  # TAM METİN (kesme yok!)
        })
        
        current_time = end_time
    
    return schedule


# ======================================
# BOOTSTRAP VE VARDİYA FONKSİYONLARI (Aynı)
# ======================================

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
            return False
        
        summaries, bayram_msg = summarize_news_batch(news_list)
        
        # Eğer kritik haber yoksa, vardiya oluşturma
        if not summaries:
            logger.warning("⚠️ [SABAH VARDİYASI] Kritik haber yok, vardiya oluşturulmadı")
            # Boş vardiya kaydet (yokluk göstergesi)
            cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
            set_cache(cache_key, [], ttl=43200)
            return True
        
        if bayram_msg:
            bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
            set_cache(bayram_key, bayram_msg, ttl=54000)
            logger.info(f"🏦 [SABAH VARDİYASI] Bayram: {bayram_msg}")
        
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
            return False
        
        summaries, bayram_msg = summarize_news_batch(news_list)
        
        if not summaries:
            logger.warning("⚠️ [AKŞAM VARDİYASI] Kritik haber yok, vardiya oluşturulmadı")
            cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
            set_cache(cache_key, [], ttl=43200)
            return True
        
        if bayram_msg:
            bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
            set_cache(bayram_key, bayram_msg, ttl=10800)
            logger.info(f"🏦 [AKŞAM VARDİYASI] Bayram: {bayram_msg}")
        
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
        
        # Boş vardiya kontrolü (kritik haber yok demek)
        if len(schedule) == 0:
            logger.info(f"ℹ️ [BANNER] {shift_name}: Bugün kritik haber yok")
            return None
        
        # Şu anki saate uygun haber
        for news_slot in schedule:
            start_time = news_slot['start']
            end_time = news_slot['end']
            
            if start_time <= current_time < end_time:
                logger.debug(f"📰 [BANNER] {shift_name}: {news_slot['text']}")
                return f"📰 {news_slot['text']}"
        
        # Slot bulunamazsa ilk haberi göster
        if schedule:
            return f"📰 {schedule[0]['text']}"
        
        return None
        
    except Exception as e:
        logger.error(f"❌ [BANNER] Hata: {e}")
        return None


def test_news_manager():
    """Test fonksiyonu"""
    print("🧪 News Manager V3.1 - ULTRA SIKI FİLTRE Test\n")
    
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
