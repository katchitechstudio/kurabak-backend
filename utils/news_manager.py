"""
News Manager - GÜNLÜK HABER SİSTEMİ V3.0 📰🚀🏦
=============================================
✅ 2 KAYNAK: GNews + NewsData API
✅ TOPLU GEMİNİ 3.0: Tek çağrıda FİLTRELEME + ÖZET + BAYRAM KONTROLÜ
✅ VARDİYA SİSTEMİ: Sabah (00:00-12:00) + Akşam (12:00-00:00)
✅ DİNAMİK SÜRE: Haber sayısına göre otomatik dağıtım
✅ REDIS ENTEGRASYONU: Cache + Backup
✅ HATA TOLERANSI: Bir API çökse diğeri devreye girer
✅ ÖNCELIK: Priority 75 (TCMB ve Enflasyon'un altında)
✅ 🚀 AKILLI BOOTSTRAP: İlk çalıştırmada otomatik doldurma
✅ 🏦 BAYRAM KONTROLÜ: Her vardiya hazırlığında Gemini'ye sorar
✅ 🎯 AKILLI FİLTRE: Suç/magazin haberleri otomatik elenir
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

def fetch_gnews(max_results: int = 10) -> List[str]:
    """
    GNews API'den ekonomi haberleri çeker
    
    Args:
        max_results: Maksimum haber sayısı
        
    Returns:
        List[str]: Haber başlıkları listesi
    """
    try:
        if not GNEWS_API_KEY:
            logger.warning("⚠️ GNEWS_API_KEY bulunamadı!")
            return []
        
        # API URL (Ekonomi, Dolar, Altın, Borsa filtreli)
        url = (
            f"https://gnews.io/api/v4/search"
            f"?q=dolar OR altın OR borsa OR faiz"
            f"&lang=tr"
            f"&country=tr"
            f"&sortby=publishedAt"
            f"&apikey={GNEWS_API_KEY}"
        )
        
        logger.info("📡 [GNEWS] Haberler çekiliyor...")
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get('totalArticles', 0) == 0:
            logger.warning("⚠️ [GNEWS] Haber bulunamadı")
            return []
        
        # Başlıkları al
        articles = data.get('articles', [])[:max_results]
        news_list = []
        
        for article in articles:
            title = article.get('title', '').strip()
            description = article.get('description', '').strip()
            
            # Başlık çok kısa/genel ise description'dan al
            if len(title) < 20 and description:
                text = description.split('.')[0]  # İlk cümle
            else:
                text = title
            
            if text and len(text) > 10:
                news_list.append(text)
        
        logger.info(f"✅ [GNEWS] {len(news_list)} haber alındı")
        return news_list
        
    except Exception as e:
        logger.error(f"❌ [GNEWS] Hata: {e}")
        return []


def fetch_newsdata(max_results: int = 10) -> List[str]:
    """
    NewsData API'den ekonomi haberleri çeker
    
    Args:
        max_results: Maksimum haber sayısı
        
    Returns:
        List[str]: Haber başlıkları listesi
    """
    try:
        if not NEWSDATA_API_KEY:
            logger.warning("⚠️ NEWSDATA_API_KEY bulunamadı!")
            return []
        
        # API URL (Business kategorisi, Türkiye, Türkçe)
        url = (
            f"https://newsdata.io/api/1/news"
            f"?apikey={NEWSDATA_API_KEY}"
            f"&country=tr"
            f"&language=tr"
            f"&category=business"
            f"&q=ekonomi OR borsa OR altın OR döviz"
        )
        
        logger.info("📡 [NEWSDATA] Haberler çekiliyor...")
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get('status') != 'success':
            logger.warning(f"⚠️ [NEWSDATA] Hata: {data.get('status')}")
            return []
        
        # Başlıkları al
        results = data.get('results', [])[:max_results]
        news_list = []
        
        for article in results:
            title = article.get('title', '').strip()
            description = article.get('description', '').strip()
            
            # Başlık çok kısa/genel ise description'dan al
            if len(title) < 20 and description:
                text = description.split('.')[0]  # İlk cümle
            else:
                text = title
            
            if text and len(text) > 10:
                news_list.append(text)
        
        logger.info(f"✅ [NEWSDATA] {len(news_list)} haber alındı")
        return news_list
        
    except Exception as e:
        logger.error(f"❌ [NEWSDATA] Hata: {e}")
        return []


def fetch_all_news() -> List[str]:
    """
    Her iki API'den haberleri çeker ve birleştirir
    
    Returns:
        List[str]: Tüm haber başlıkları (max 20 adet)
    """
    logger.info("📰 [NEWS] Tüm kaynaklardan haber toplama başlıyor...")
    
    # Her iki kaynaktan çek
    gnews_list = fetch_gnews(max_results=10)
    newsdata_list = fetch_newsdata(max_results=10)
    
    # Birleştir
    all_news = gnews_list + newsdata_list
    
    # Tekrar edenleri temizle (benzer başlıkları kaldır)
    unique_news = []
    seen_keywords = set()
    
    for news in all_news:
        # İlk 5 kelimeyi anahtar olarak kullan
        keywords = ' '.join(news.split()[:5]).lower()
        
        if keywords not in seen_keywords:
            unique_news.append(news)
            seen_keywords.add(keywords)
    
    logger.info(f"✅ [NEWS] Toplam {len(unique_news)} benzersiz haber toplandı")
    
    # Maksimum 20 haber
    return unique_news[:20]


# ======================================
# 🏦 GEMİNİ 3.0 - FİLTRELEME + ÖZET + BAYRAM
# ======================================

def summarize_news_batch(news_list: List[str]) -> Tuple[List[str], Optional[str]]:
    """
    GEMİNİ 3.0 ile AKILLI FİLTRELEME + ÖZET + BAYRAM KONTROLÜ (TEK ÇAĞRI!)
    
    Args:
        news_list: Ham haber başlıkları
        
    Returns:
        Tuple[List[str], Optional[str]]: (filtrelenmiş_özetler, bayram_mesajı)
        Örnek: (["Dolar 43.5 TL'ye yükseldi", ...], "🏦 Ramazan Bayramı 1. Gün")
    """
    try:
        if not GEMINI_API_KEY:
            logger.warning("⚠️ GEMINI_API_KEY bulunamadı! Haberler olduğu gibi kullanılacak.")
            # Fallback: Haberleri kısalt (ilk 10 kelime)
            return [' '.join(news.split()[:10]) for news in news_list], None
        
        if not news_list:
            logger.warning("⚠️ [GEMİNİ] Özetlenecek haber yok!")
            return [], None
        
        # Gemini 3.0'ı yapılandır
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-3-flash-preview')
        
        # Haberleri numaralandır
        numbered_news = '\n'.join([f"{i+1}. {news}" for i, news in enumerate(news_list)])
        
        # Bugünün tarihi
        today = datetime.now().strftime('%d %B %Y, %A')  # "30 Ocak 2026, Perşembe"
        
        # 🎯 YENİ PROMPT: FİLTRE + ÖZET + BAYRAM
        prompt = f"""
SEN BİR FİNANS HABER EDİTÖRÜSÜN. İŞLEV: Profesyonel döviz takip uygulaması için haber seçimi.

GÖREV 1 - BAYRAM KONTROLÜ:
Bugün {today} tarihinde Türkiye'de resmi tatil veya bayram var mı?

Kontrol et:
- Resmi tatiller (Ramazan, Kurban Bayramı, 23 Nisan, 19 Mayıs, 30 Ağustos, 29 Ekim, 1 Ocak)
- Arefe günleri
- Dini bayramlar

VARSA → "BAYRAM: [tam isim]" yaz (örn: "BAYRAM: Ramazan Bayramı 1. Gün")
YOKSA → "BAYRAM: YOK" yaz

---

GÖREV 2 - HABER FİLTRELEME + ÖZET:

Aşağıdaki {len(news_list)} haberden sadece FİNANSAL DEĞERİ olanları seç ve özetle.

❌ ŞUNLARI ASLA ALMA:
- Suç haberleri (hırsızlık, dolandırıcılık, sahte para/altın, kuyumcu soygunu)
- Yerel polis olayları
- Trafik kazaları
- Mahkeme kararları
- Magazin/şov haberleri
- Spor haberleri

✅ SADECE BUNLARI AL:
- Merkez Bankası kararları (TCMB, FED, ECB, BoE vb.)
- Döviz kuru hareketleri (dolar/euro/sterlin yükseldi/düştü/rekor kırdı)
- Altın/gümüş FİYAT hareketleri (gram altın, ons altın)
- Faiz, enflasyon, büyüme rakamları
- Borsa endeksleri (BIST 100, S&P 500 vb.)
- Ekonomik büyüme/daralma verileri
- Ticaret savaşları, ambargolar, uluslararası anlaşmalar
- Petrol/doğalgaz fiyat hareketleri

HAM HABERLER:
{numbered_news}

FORMAT:
BAYRAM: [VAR/YOK veya isim]
1. [Max 10 kelime finansal özet]
2. [Max 10 kelime finansal özet]
...

KURALLAR:
- Her özet MAX 10 kelime
- Emoji YOK
- Sadece sayı varsa birim ekle (örn: "Dolar 43.5 TL'ye yükseldi")
- Finansal olmayan haberi ATLA, numarasını yazmadan geç
- Eğer hiçbir finansal haber yoksa sadece "HABER: YOK" yaz

BAŞKA AÇIKLAMA YAPMA, SADECE BU FORMATI KULLAN!
"""
        
        logger.info(f"🤖 [GEMİNİ 3.0] {len(news_list)} haber filtreleniyor + bayram kontrolü...")
        
        # Gemini'ye gönder
        response = model.generate_content(prompt)
        result = response.text.strip()
        
        # Satırlara böl
        lines = result.split('\n')
        
        # İlk satır: BAYRAM kontrolü
        bayram_msg = None
        first_line = lines[0].strip()
        
        if first_line.startswith("BAYRAM:"):
            bayram_text = first_line.replace("BAYRAM:", "").strip()
            if bayram_text and bayram_text.upper() != "YOK":
                bayram_msg = f"🏦 {bayram_text}"
                logger.info(f"🏦 [GEMİNİ] Bayram tespit edildi: {bayram_text}")
            else:
                logger.info(f"🏦 [GEMİNİ] Bugün bayram yok")
            lines = lines[1:]  # Bayram satırını çıkar
        
        # Kalan satırlar: Filtrelenmiş özetler
        summaries = []
        for line in lines:
            clean_line = line.strip()
            
            # Boş satırları atla
            if not clean_line:
                continue
            
            # "HABER: YOK" kontrolü
            if "HABER:" in clean_line.upper() and "YOK" in clean_line.upper():
                logger.warning("⚠️ [GEMİNİ] Finansal haber bulunamadı!")
                break
            
            # Numarayı kaldır
            if '. ' in clean_line:
                clean_line = clean_line.split('. ', 1)[1]
            
            if clean_line and len(clean_line) > 5:
                summaries.append(clean_line)
        
        logger.info(f"✅ [GEMİNİ 3.0] {len(summaries)} finansal haber filtrelendi + özetlendi")
        
        # Eğer hiç haber kalmadıysa fallback
        if not summaries:
            logger.warning("⚠️ [GEMİNİ] Filtreleme sonrası haber kalmadı! Fallback devrede...")
            summaries = [' '.join(news.split()[:10]) for news in news_list[:3]]
        
        return summaries, bayram_msg
        
    except Exception as e:
        logger.error(f"❌ [GEMİNİ 3.0] Hata: {e}")
        # Fallback: Haberleri kısalt
        return [' '.join(news.split()[:10]) for news in news_list[:5]], None


# ======================================
# VARDİYA PLANLAMA FONKSİYONU
# ======================================

def plan_shift_schedule(news_list: List[str], start_hour: int, end_hour: int) -> List[Dict]:
    """
    Haberleri belirlenen saatlere eşit olarak dağıtır (DİNAMİK!)
    
    Args:
        news_list: Haber listesi
        start_hour: Başlangıç saati (örn: 0)
        end_hour: Bitiş saati (örn: 12)
        
    Returns:
        List[Dict]: [{"start": "00:00", "end": "02:00", "text": "..."}]
    """
    if not news_list:
        logger.warning("⚠️ [PLAN] Planlanacak haber yok!")
        return []
    
    # Toplam süre (dakika cinsinden)
    total_duration_minutes = (end_hour - start_hour) * 60
    
    # Haber başına süre (DİNAMİK!)
    news_count = len(news_list)
    duration_per_news = total_duration_minutes // news_count
    
    schedule = []
    current_time = datetime.now().replace(hour=start_hour, minute=0, second=0, microsecond=0)
    
    # Eğer gece yarısı için planlama yapılıyorsa, tarihi bir gün ileri al
    if start_hour == 0 and datetime.now().hour >= 12:
        current_time += timedelta(days=1)
    
    logger.info(f"📅 [PLAN] {news_count} haber, {start_hour}:00 - {end_hour if end_hour < 24 else '23:59'} arası dağıtılıyor")
    logger.info(f"   Her haber ~{duration_per_news} dakika ekranda kalacak")
    
    for i, news in enumerate(news_list):
        start_str = current_time.strftime("%H:%M")
        
        # Son haberde bitiş saatini tam end_hour'a getir
        if i == news_count - 1:
            if end_hour == 24:
                end_time = current_time.replace(hour=23, minute=59, second=59)
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
# 🚀 AKILLI BOOTSTRAP SİSTEMİ
# ======================================

def bootstrap_news_system() -> bool:
    """
    🚀 İLK ÇALIŞTIRMA - AKILLI BOOTSTRAP
    
    Eğer vardiya verileri Redis'te yoksa, HEMEN doldurur.
    
    Returns:
        bool: Bootstrap yapıldı mı?
    """
    try:
        current_hour = datetime.now().hour
        
        # Hangi vardiya verisine ihtiyacımız var?
        if 0 <= current_hour < 12:
            cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
            shift_name = "SABAH"
            prepare_func = prepare_morning_shift
        else:
            cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
            shift_name = "AKŞAM"
            prepare_func = prepare_evening_shift
        
        # Vardiya verisi var mı?
        existing_data = get_cache(cache_key)
        
        if existing_data:
            logger.info(f"✅ [BOOTSTRAP] {shift_name} vardiyası zaten hazır")
            return False
        
        # VERİ YOK! Hemen doldur
        logger.warning(f"⚠️ [BOOTSTRAP] {shift_name} vardiyası boş! Acil doldurma başlıyor...")
        
        success = prepare_func()
        
        if success:
            logger.info(f"🚀 [BOOTSTRAP] {shift_name} vardiyası başarıyla dolduruldu!")
            return True
        else:
            logger.error(f"❌ [BOOTSTRAP] {shift_name} vardiyası doldurulamadı!")
            return False
        
    except Exception as e:
        logger.error(f"❌ [BOOTSTRAP] Hata: {e}")
        return False


# ======================================
# ANA VARDİYA FONKSİYONLARI
# ======================================

def prepare_morning_shift() -> bool:
    """
    SABAH VARDİYASI (00:00 - 12:00)
    Gece yarısı çalışır, sabah için haberleri hazırlar
    """
    try:
        logger.info("🌅 [SABAH VARDİYASI] Hazırlık başlıyor...")
        
        # 1. Haberleri topla
        news_list = fetch_all_news()
        
        if not news_list:
            logger.warning("⚠️ [SABAH VARDİYASI] Haber bulunamadı!")
            return False
        
        # 2. Gemini 3.0 ile filtrele + özetle + bayram kontrolü
        summaries, bayram_msg = summarize_news_batch(news_list)
        
        # 3. Bayram varsa Redis'e kaydet
        if bayram_msg:
            bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
            set_cache(bayram_key, bayram_msg, ttl=54000)  # 15 saat
            logger.info(f"🏦 [SABAH VARDİYASI] Bayram kaydedildi: {bayram_msg}")
        
        # 4. Sabah için planla (00:00 - 12:00)
        schedule = plan_shift_schedule(summaries, start_hour=0, end_hour=12)
        
        # 5. Redis'e kaydet
        cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
        set_cache(cache_key, schedule, ttl=43200)  # 12 saat
        
        # Son güncelleme
        update_key = Config.CACHE_KEYS.get('news_last_update', 'news:last_update')
        set_cache(update_key, {
            'shift': 'morning',
            'timestamp': time.time(),
            'news_count': len(schedule),
            'bayram': bayram_msg if bayram_msg else 'yok'
        }, ttl=86400)
        
        logger.info(f"✅ [SABAH VARDİYASI] {len(schedule)} haber hazırlandı!")
        return True
        
    except Exception as e:
        logger.error(f"❌ [SABAH VARDİYASI] Hata: {e}")
        return False


def prepare_evening_shift() -> bool:
    """
    AKŞAM VARDİYASI (12:00 - 00:00)
    Öğlen çalışır, akşam için haberleri hazırlar
    """
    try:
        logger.info("🌆 [AKŞAM VARDİYASI] Hazırlık başlıyor...")
        
        # 1. Haberleri topla
        news_list = fetch_all_news()
        
        if not news_list:
            logger.warning("⚠️ [AKŞAM VARDİYASI] Haber bulunamadı!")
            return False
        
        # 2. Gemini 3.0 ile filtrele + özetle + bayram kontrolü
        summaries, bayram_msg = summarize_news_batch(news_list)
        
        # 3. Bayram varsa Redis'e kaydet
        if bayram_msg:
            bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
            set_cache(bayram_key, bayram_msg, ttl=10800)  # 3 saat (15:00'a kadar)
            logger.info(f"🏦 [AKŞAM VARDİYASI] Bayram kaydedildi: {bayram_msg}")
        
        # 4. Akşam için planla (12:00 - 00:00)
        schedule = plan_shift_schedule(summaries, start_hour=12, end_hour=24)
        
        # 5. Redis'e kaydet
        cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
        set_cache(cache_key, schedule, ttl=43200)  # 12 saat
        
        # Son güncelleme
        update_key = Config.CACHE_KEYS.get('news_last_update', 'news:last_update')
        set_cache(update_key, {
            'shift': 'evening',
            'timestamp': time.time(),
            'news_count': len(schedule),
            'bayram': bayram_msg if bayram_msg else 'yok'
        }, ttl=86400)
        
        logger.info(f"✅ [AKŞAM VARDİYASI] {len(schedule)} haber hazırlandı!")
        return True
        
    except Exception as e:
        logger.error(f"❌ [AKŞAM VARDİYASI] Hata: {e}")
        return False


# ======================================
# KULLANICI İÇİN HABER GETIRME
# ======================================

def get_current_news_banner() -> Optional[str]:
    """
    Şu anki saate uygun haber başlığını döndürür
    
    🚀 İlk çağrıda bootstrap otomatik devreye girer!
    
    Returns:
        str: Haber başlığı veya None
    """
    try:
        current_hour = datetime.now().hour
        current_time = datetime.now().strftime("%H:%M")
        
        # Hangi vardiya?
        if 0 <= current_hour < 12:
            cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
            shift_name = "SABAH"
        else:
            cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
            shift_name = "AKŞAM"
        
        # Vardiya verilerini al
        schedule = get_cache(cache_key)
        
        if not schedule:
            logger.warning(f"⚠️ [BANNER] {shift_name} vardiyası yok! Bootstrap tetikleniyor...")
            
            # 🚀 AKILLI BOOTSTRAP
            bootstrap_success = bootstrap_news_system()
            
            if bootstrap_success:
                schedule = get_cache(cache_key)
                if not schedule:
                    logger.error(f"❌ [BANNER] Bootstrap sonrası hala veri yok!")
                    return None
            else:
                logger.error(f"❌ [BANNER] Bootstrap başarısız!")
                return None
        
        # Şu anki saate uygun haberi bul
        for news_slot in schedule:
            start_time = news_slot['start']
            end_time = news_slot['end']
            
            if start_time <= current_time < end_time:
                logger.debug(f"📰 [BANNER] {shift_name}: {news_slot['text'][:50]}...")
                return f"📰 {news_slot['text']}"
        
        # Slot bulunamazsa ilk haberi göster
        if schedule:
            return f"📰 {schedule[0]['text']}"
        
        return None
        
    except Exception as e:
        logger.error(f"❌ [BANNER] Hata: {e}")
        return None


# ======================================
# TEST FONKSİYONU
# ======================================

def test_news_manager():
    """
    Test: python -c "from utils.news_manager import test_news_manager; test_news_manager()"
    """
    print("🧪 News Manager V3.0 🎯 (FİLTRELİ) Test...\n")
    
    # 1. Haber toplama
    print("1️⃣ HABER TOPLAMA:")
    news_list = fetch_all_news()
    print(f"   ✅ {len(news_list)} haber toplandı\n")
    
    if news_list:
        print("   İlk 3 haber:")
        for i, news in enumerate(news_list[:3], 1):
            print(f"   {i}. {news[:80]}...")
        print()
    
    # 2. Gemini 3.0 filtre + özet + bayram
    if news_list:
        print("2️⃣ GEMİNİ 3.0 FİLTRE + ÖZET + BAYRAM:")
        summaries, bayram_msg = summarize_news_batch(news_list[:5])
        print(f"   ✅ {len(summaries)} finansal haber filtrelendi\n")
        
        if bayram_msg:
            print(f"   🏦 BAYRAM: {bayram_msg}\n")
        else:
            print("   🏦 BAYRAM: Yok\n")
        
        print("   Filtrelenmiş özetler:")
        for i, summary in enumerate(summaries, 1):
            print(f"   {i}. {summary}")
        print()
    
    # 3. Planlama
    if summaries:
        print("3️⃣ VARDİYA PLANLAMA:")
        schedule = plan_shift_schedule(summaries, start_hour=0, end_hour=12)
        print(f"   ✅ {len(schedule)} slot\n")
        
        print("   İlk 3 slot:")
        for slot in schedule[:3]:
            print(f"   {slot['start']}-{slot['end']}: {slot['text']}")
        print()
    
    # 4. Bootstrap
    print("4️⃣ BOOTSTRAP:")
    bootstrap_success = bootstrap_news_system()
    print(f"   {'✅ Başarılı' if bootstrap_success else 'ℹ️ Gerek yok'}\n")
    
    # 5. Banner
    print("5️⃣ BANNER:")
    banner = get_current_news_banner()
    if banner:
        print(f"   ✅ {banner}\n")
    else:
        print("   ℹ️ Bulunamadı\n")


if __name__ == "__main__":
    test_news_manager()
