def summarize_news_batch(news_list: List[str]) -> tuple[List[str], Optional[str]]:
    """
    GEMİNİ ile toplu haber özetleme + BAYRAM KONTROLÜ
    
    Returns:
        tuple: (özetler, bayram_mesajı)
        Örnek: (["Dolar yükseldi", ...], "🏦 Ramazan Bayramı")
    """
    try:
        if not GEMINI_API_KEY:
            logger.warning("⚠️ GEMINI_API_KEY bulunamadı!")
            return [' '.join(news.split()[:10]) for news in news_list], None
        
        if not news_list:
            return [], None
        
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Haberleri numaralandır
        numbered_news = '\n'.join([f"{i+1}. {news}" for i, news in enumerate(news_list)])
        
        # Bugünün tarihi
        today = datetime.now().strftime('%d %B %Y, %A')  # "29 Ocak 2026, Çarşamba"
        
        # TEK PROMPT: Bayram + Özetler
        prompt = f"""
Bugün {today} tarihinde Türkiye'de resmi tatil veya önemli bayram var mı?

Kontrol et:
- Resmi tatiller (Ramazan, Kurban Bayramı, 23 Nisan, 19 Mayıs, 30 Ağustos, 29 Ekim, 1 Ocak)
- Arefe günleri (yarım gün tatil)

VARSA:
"BAYRAM: [tam isim]" yaz
Örnek: "BAYRAM: Ramazan Bayramı 1. Gün"
Örnek: "BAYRAM: Kurban Bayramı Arefe"

YOKSA:
"BAYRAM: YOK" yaz

SONRA aşağıdaki {len(news_list)} ekonomi haberini özetle (her biri max 10 kelime):

{numbered_news}

FORMAT:
BAYRAM: [VAR/YOK]
1. [10 kelimelik özet]
2. [10 kelimelik özet]
...

Başka açıklama yapma!
"""
        
        logger.info(f"🤖 [GEMİNİ] {len(news_list)} haber özetleniyor + bayram kontrolü...")
        
        response = model.generate_content(prompt)
        result = response.text.strip()
        
        # Satırlara böl
        lines = result.split('\n')
        
        # İlk satır: BAYRAM kontrolü
        bayram_msg = None
        first_line = lines[0].strip()
        
        if first_line.startswith("BAYRAM:"):
            bayram_text = first_line.replace("BAYRAM:", "").strip()
            if bayram_text != "YOK" and bayram_text.upper() != "YOK":
                bayram_msg = f"🏦 Resmî tatil: {bayram_text}"
                logger.info(f"🏦 [GEMİNİ] Bayram tespit edildi: {bayram_text}")
            lines = lines[1:]  # Bayram satırını çıkar
        
        # Kalan satırlar: Özetler
        summaries = []
        for line in lines:
            clean_line = line.strip()
            if clean_line:
                # Numarayı kaldır
                if '. ' in clean_line:
                    clean_line = clean_line.split('. ', 1)[1]
                
                if clean_line:
                    summaries.append(clean_line)
        
        logger.info(f"✅ [GEMİNİ] {len(summaries)} özet + bayram kontrolü tamamlandı")
        
        # Eksik özetleri tamamla
        while len(summaries) < len(news_list):
            idx = len(summaries)
            summaries.append(' '.join(news_list[idx].split()[:10]))
        
        return summaries[:len(news_list)], bayram_msg
        
    except Exception as e:
        logger.error(f"❌ [GEMİNİ] Özet hatası: {e}")
        return [' '.join(news.split()[:10]) for news in news_list], None


def prepare_morning_shift() -> bool:
    """SABAH VARDİYASI + BAYRAM KONTROLÜ"""
    try:
        logger.info("🌅 [SABAH VARDİYASI] Hazırlık başlıyor...")
        
        news_list = fetch_all_news()
        if not news_list:
            return False
        
        # Gemini: Özetler + Bayram kontrolü
        summaries, bayram_msg = summarize_news_batch(news_list)
        
        # Bayram varsa Redis'e kaydet
        if bayram_msg:
            from utils.cache import set_cache
            from config import Config
            bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
            set_cache(bayram_key, bayram_msg, ttl=43200)  # 12 saat
            logger.info(f"🏦 [BAYRAM] Redis'e kaydedildi: {bayram_msg}")
        
        # Sabah için planla
        schedule = plan_shift_schedule(summaries, start_hour=0, end_hour=12)
        
        cache_key = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
        set_cache(cache_key, schedule, ttl=43200)
        
        logger.info(f"✅ [SABAH VARDİYASI] {len(schedule)} haber hazırlandı!")
        return True
        
    except Exception as e:
        logger.error(f"❌ [SABAH VARDİYASI] Hata: {e}")
        return False


def prepare_evening_shift() -> bool:
    """AKŞAM VARDİYASI + BAYRAM KONTROLÜ"""
    try:
        logger.info("🌆 [AKŞAM VARDİYASI] Hazırlık başlıyor...")
        
        news_list = fetch_all_news()
        if not news_list:
            return False
        
        # Gemini: Özetler + Bayram kontrolü
        summaries, bayram_msg = summarize_news_batch(news_list)
        
        # Bayram varsa Redis'e kaydet
        if bayram_msg:
            from utils.cache import set_cache
            from config import Config
            bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
            set_cache(bayram_key, bayram_msg, ttl=43200)
            logger.info(f"🏦 [BAYRAM] Redis'e kaydedildi: {bayram_msg}")
        
        # Akşam için planla
        schedule = plan_shift_schedule(summaries, start_hour=12, end_hour=24)
        
        cache_key = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
        set_cache(cache_key, schedule, ttl=43200)
        
        logger.info(f"✅ [AKŞAM VARDİYASI] {len(schedule)} haber hazırlandı!")
        return True
        
    except Exception as e:
        logger.error(f"❌ [AKŞAM VARDİYASI] Hata: {e}")
        return False
