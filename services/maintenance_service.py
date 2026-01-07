"""
Maintenance Service - Redis Only (İyileştirilmiş)
Periyodik olarak API'den veri çeker ve Redis'e yazar
2 DAKIKADA BİR GÜNCELLEME (V4 API dakikalık güncelleniyor)

İyileştirmeler:
- Retry mekanizması eklendi
- Timeout ayarları iyileştirildi
- Daha detaylı hata yönetimi
- Başarısız API'ler için akıllı bekleme
"""
import logging
import time
from apscheduler.schedulers.background import BackgroundScheduler
from services.currency_service import fetch_currencies_to_cache
from services.gold_service import fetch_golds_to_cache
from services.silver_service import fetch_silvers_to_cache

logger = logging.getLogger(__name__)

# Scheduler instance
scheduler = BackgroundScheduler()

# Circuit breaker için basit sayaçlar
failure_counts = {
    'currency': 0,
    'gold': 0,
    'silver': 0
}
MAX_FAILURES = 5  # 5 başarısızlıktan sonra geçici olarak atla


def retry_with_backoff(func, name, max_retries=3):
    """
    Exponential backoff ile retry mekanizması
    
    Args:
        func: Çalıştırılacak fonksiyon
        name: Servis adı (loglama için)
        max_retries: Maksimum deneme sayısı
        
    Returns:
        bool: Başarılı ise True
    """
    for attempt in range(max_retries):
        try:
            # Circuit breaker kontrolü
            if failure_counts.get(name.lower(), 0) >= MAX_FAILURES:
                logger.warning(f"⚠️ {name} geçici olarak devre dışı (çok fazla hata)")
                return False
            
            # Fonksiyonu çalıştır
            result = func()
            
            if result:
                # Başarılı - failure count'u sıfırla
                failure_counts[name.lower()] = 0
                return True
            else:
                raise Exception(f"{name} servisi False döndü")
                
        except Exception as e:
            attempt_num = attempt + 1
            
            if attempt_num < max_retries:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                logger.warning(
                    f"⚠️ {name} hatası (deneme {attempt_num}/{max_retries}): {str(e)[:100]}"
                )
                logger.info(f"⏳ {wait_time}s bekleyip tekrar denenecek...")
                time.sleep(wait_time)
            else:
                # Son deneme de başarısız
                failure_counts[name.lower()] = failure_counts.get(name.lower(), 0) + 1
                logger.error(
                    f"❌ {name} başarısız ({max_retries} deneme): {str(e)[:100]}"
                )
                logger.error(f"📊 Toplam başarısızlık: {failure_counts[name.lower()]}/{MAX_FAILURES}")
                return False
    
    return False


def fetch_all_data():
    """
    Tüm verileri API'den çek ve Redis'e yaz
    2 dakikada bir çalışır (V4 API dakikalık güncelleniyor)
    """
    logger.info("🔄 Periyodik veri güncelleme başlıyor...")
    
    success_count = 0
    total_count = 3
    results = {}
    
    # 1. Dövizleri çek (retry ile)
    if retry_with_backoff(fetch_currencies_to_cache, "Döviz", max_retries=3):
        success_count += 1
        results['currency'] = True
        logger.info("✅ Dövizler güncellendi")
    else:
        results['currency'] = False
        logger.warning("⚠️ Döviz güncelleme başarısız")
    
    # 2. Altınları çek (retry ile)
    if retry_with_backoff(fetch_golds_to_cache, "Altın", max_retries=3):
        success_count += 1
        results['gold'] = True
        logger.info("✅ Altınlar güncellendi")
    else:
        results['gold'] = False
        logger.warning("⚠️ Altın güncelleme başarısız")
    
    # 3. Gümüşü çek (retry ile)
    if retry_with_backoff(fetch_silvers_to_cache, "Gümüş", max_retries=3):
        success_count += 1
        results['silver'] = True
        logger.info("✅ Gümüş güncellendi")
    else:
        results['silver'] = False
        logger.warning("⚠️ Gümüş güncelleme başarısız")
    
    # Sonuç raporu
    if success_count == total_count:
        logger.info(f"🎉 Tüm veriler başarıyla güncellendi ({success_count}/{total_count})")
        # Başarılı güncelleme - circuit breaker'ları sıfırla
        reset_circuit_breakers()
    elif success_count > 0:
        logger.warning(f"⚠️ Kısmi güncelleme: {success_count}/{total_count} başarılı")
        logger.info(f"📊 Detay: {results}")
    else:
        logger.error(f"❌ Hiçbir veri güncellenemedi!")
        logger.error(f"📊 Circuit breaker durumu: {failure_counts}")
    
    return success_count > 0


def reset_circuit_breakers():
    """
    Tüm circuit breaker'ları sıfırla
    Başarılı tam güncelleme sonrası çağrılır
    """
    global failure_counts
    old_counts = failure_counts.copy()
    failure_counts = {
        'currency': 0,
        'gold': 0,
        'silver': 0
    }
    if any(old_counts.values()):
        logger.info(f"🔄 Circuit breaker'lar sıfırlandı (önceki: {old_counts})")


def start_scheduler():
    """
    Scheduler'ı başlat
    2 dakikada bir fetch_all_data() çalıştırır
    """
    if scheduler.running:
        logger.warning("⚠️ Scheduler zaten çalışıyor")
        return
    
    try:
        # İlk çalıştırmayı hemen yap
        logger.info("🚀 İlk veri çekme başlıyor...")
        fetch_all_data()
        
        # 2 dakikada bir tekrarla (120 saniye)
        scheduler.add_job(
            fetch_all_data,
            'interval',
            seconds=120,  # 2 dakika
            id='fetch_all_data',
            name='API Veri Güncelleme',
            replace_existing=True,
            max_instances=1  # Aynı anda sadece 1 instance çalışsın
        )
        
        scheduler.start()
        logger.info("✅ Scheduler başlatıldı (2 dakikada bir çalışacak)")
        logger.info(f"⚙️ Retry ayarları: Max 3 deneme, exponential backoff")
        logger.info(f"⚙️ Circuit breaker: {MAX_FAILURES} başarısızlıktan sonra devre dışı")
        
    except Exception as e:
        logger.error(f"❌ Scheduler başlatma hatası: {e}")
        raise


def stop_scheduler():
    """
    Scheduler'ı durdur
    """
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
            logger.info("🛑 Scheduler durduruldu")
        else:
            logger.info("ℹ️ Scheduler zaten durmuş")
    except Exception as e:
        logger.error(f"❌ Scheduler durdurma hatası: {e}")


# Geriye uyumluluk için (eski kodlar çağırabilir)
def cleanup_old_data():
    """Artık kullanılmıyor - PostgreSQL yok"""
    logger.info("ℹ️ cleanup_old_data çağrıldı ama PostgreSQL kullanılmıyor")
    return True


def optimize_database():
    """Artık kullanılmıyor - PostgreSQL yok"""
    logger.info("ℹ️ optimize_database çağrıldı ama PostgreSQL kullanılmıyor")
    return True


def weekly_maintenance():
    """
    Haftalık bakım - Sadece cache temizleme
    Redis'te veri birikmediği için çok basit
    """
    logger.info("🔧 Haftalık bakım başlıyor...")
    
    try:
        from utils.cache import clear_cache
        clear_cache()
        logger.info("🗑️ Redis cache temizlendi")
        
        # Circuit breaker'ları da sıfırla
        reset_circuit_breakers()
        logger.info("🔄 Circuit breaker'lar sıfırlandı")
        
    except Exception as e:
        logger.error(f"❌ Cache temizleme hatası: {e}")
    
    logger.info("✅ Haftalık bakım tamamlandı")
    return True
