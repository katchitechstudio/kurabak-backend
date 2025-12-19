import logging
import psycopg2
from datetime import datetime, timedelta
from config import Config
from models.db import get_db, put_db

logger = logging.getLogger(__name__)

def cleanup_old_data():
    """
    30 günden eski verileri temizle
    Sadece en son kayıtları tut, eski verileri sil
    """
    conn = None
    cur = None
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # 30 gün öncesi
        cutoff_date = datetime.now() - timedelta(days=30)
        
        # Her tablodan eski kayıtları sil
        tables = ['currencies', 'golds', 'silvers']
        total_deleted = 0
        
        for table in tables:
            cur.execute(f"""
                DELETE FROM {table} 
                WHERE updated_at < %s
            """, (cutoff_date,))
            
            deleted = cur.rowcount
            total_deleted += deleted
            
            if deleted > 0:
                logger.info(f"🗑️ {table}: {deleted} eski kayıt silindi")
        
        conn.commit()
        
        if total_deleted > 0:
            logger.info(f"✅ Toplam {total_deleted} eski kayıt temizlendi (30+ gün öncesi)")
        else:
            logger.info("✅ Temizlenecek eski kayıt yok")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Veri temizleme hatası: {e}")
        if conn:
            conn.rollback()
        return False
        
    finally:
        if cur:
            cur.close()
        if conn:
            put_db(conn)

def optimize_database():
    """
    Veritabanını optimize et - VACUUM ANALYZE
    AUTOCOMMIT mode ile çalışır (transaction dışında)
    """
    conn = None
    cur = None
    
    try:
        # VACUUM için AUTOCOMMIT mode gerekli
        conn = psycopg2.connect(Config.DATABASE_URL)
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        
        tables = ['currencies', 'golds', 'silvers']
        
        for table in tables:
            cur.execute(f"VACUUM ANALYZE {table}")
            logger.info(f"🧹 {table} tablosu optimize edildi")
        
        logger.info("✅ Veritabanı optimizasyonu tamamlandı (VACUUM ANALYZE)")
        return True
        
    except Exception as e:
        logger.error(f"❌ Veritabanı optimizasyonu hatası: {e}")
        return False
        
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

def weekly_maintenance():
    """
    Haftalık bakım - Eski verileri temizle ve veritabanını optimize et
    Her Pazar sabahı 04:00'te çalışır
    """
    logger.info("🔧 Haftalık bakım başlıyor...")
    
    # 1. Önce eski verileri temizle
    cleanup_success = cleanup_old_data()
    
    # 2. Sonra veritabanını optimize et
    optimize_success = optimize_database()
    
    if cleanup_success and optimize_success:
        logger.info("✅ Haftalık bakım başarıyla tamamlandı")
    else:
        logger.warning("⚠️ Haftalık bakım kısmen tamamlandı (bazı işlemler başarısız)")
    
    # Cache'i temizle
    try:
        from utils.cache import clear_cache
        clear_cache()
        logger.info("🗑️ Redis cache temizlendi")
    except:
        pass
    
    return True
