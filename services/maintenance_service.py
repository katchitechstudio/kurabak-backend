"""
Maintenance Service - Redis Only
Periyodik olarak API'den veri çeker ve Redis'e yazar
2 DAKIKADA BİR GÜNCELLEME (V4 API dakikalık güncelleniyor)
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from services.currency_service import fetch_currencies_to_cache
from services.gold_service import fetch_golds_to_cache
from services.silver_service import fetch_silvers_to_cache

logger = logging.getLogger(__name__)

# Scheduler instance
scheduler = BackgroundScheduler()


def fetch_all_data():
    """
    Tüm verileri API'den çek ve Redis'e yaz
    2 dakikada bir çalışır (V4 API dakikalık güncelleniyor)
    """
    logger.info("🔄 Periyodik veri güncelleme başlıyor...")
    
    success_count = 0
    total_count = 3
    
    # 1. Dövizleri çek
    try:
        if fetch_currencies_to_cache():
            success_count += 1
            logger.info("✅ Dövizler güncellendi")
        else:
            logger.warning("⚠️ Döviz güncelleme başarısız")
    except Exception as e:
        logger.error(f"❌ Döviz çekme hatası: {e}")
    
    # 2. Altınları çek
    try:
        if fetch_golds_to_cache():
            success_count += 1
            logger.info("✅ Altınlar güncellendi")
        else:
            logger.warning("⚠️ Altın güncelleme başarısız")
    except Exception as e:
        logger.error(f"❌ Altın çekme hatası: {e}")
    
    # 3. Gümüşü çek
    try:
        if fetch_silvers_to_cache():
            success_count += 1
            logger.info("✅ Gümüş güncellendi")
        else:
            logger.warning("⚠️ Gümüş güncelleme başarısız")
    except Exception as e:
        logger.error(f"❌ Gümüş çekme hatası: {e}")
    
    # Sonuç raporu
    if success_count == total_count:
        logger.info(f"🎉 Tüm veriler başarıyla güncellendi ({success_count}/{total_count})")
    elif success_count > 0:
        logger.warning(f"⚠️ Kısmi güncelleme: {success_count}/{total_count} başarılı")
    else:
        logger.error(f"❌ Hiçbir veri güncellenemedi!")
    
    return success_count > 0


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
            replace_existing=True
        )
        
        scheduler.start()
        logger.info("✅ Scheduler başlatıldı (2 dakikada bir çalışacak)")
        
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
    except Exception as e:
        logger.error(f"❌ Cache temizleme hatası: {e}")
    
    logger.info("✅ Haftalık bakım tamamlandı")
    return True
