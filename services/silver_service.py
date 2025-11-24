import requests
import logging
from models.db import get_db, put_db
from config import Config

logger = logging.getLogger(__name__)

def fetch_silvers():
    conn = None
    cur = None
    
    try:
        logger.info("🥈 Gümüş çekiliyor...")
        
        headers = {'authorization': f'apikey {Config.COLLECTAPI_TOKEN}'}
        url = "https://api.collectapi.com/economy/silverPrice"
        
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        if not data.get("success"):
            logger.error("Gümüş API hatası.")
            return False
        
        item = data["result"]  # ✅ Dict
        name = "Gümüş"
        buying = float(item["buying"])
        selling = float(item["selling"])
        
        # 🔥 NEGATİF/SIFIR KONTROLÜ
        if buying <= 0 or selling <= 0:
            logger.warning(f"⚠️ {name} buying={buying}, selling={selling} (negatif/sıfır), atlanıyor")
            return False
        
        rate = buying
        
        conn = get_db()
        cur = conn.cursor()
        
        # Değişim yüzdesini hesapla
        cur.execute("SELECT rate FROM silvers WHERE name = %s", (name,))
        old_data = cur.fetchone()
        
        if old_data and old_data[0]:
            old_rate = float(old_data[0])
            if old_rate > 0:
                change_percent = ((rate - old_rate) / old_rate) * 100
            else:
                change_percent = 0.0
        else:
            change_percent = 0.0  # İlk kayıt
        
        # Veritabanına kaydet
        cur.execute("""
            INSERT INTO silvers (name, buying, selling, rate, change_percent, updated_at)
            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (name) DO UPDATE SET
                buying=EXCLUDED.buying,
                selling=EXCLUDED.selling,
                rate=EXCLUDED.rate,
                change_percent=EXCLUDED.change_percent,
                updated_at=CURRENT_TIMESTAMP
        """, (name, buying, selling, rate, change_percent))
        
        cur.execute("INSERT INTO silver_history (name, rate) VALUES (%s, %s)", 
                    (name, rate))
        
        conn.commit()
        
        # Cache'i temizle
        try:
            from utils.cache import clear_cache
            clear_cache()
        except Exception as e:
            logger.warning(f"Cache temizleme hatası: {e}")
        
        logger.info("✅ 1 gümüş güncellendi")
        return True
        
    except Exception as e:
        logger.error(f"Gümüş çekme hatası: {e}")
        if conn:
            conn.rollback()
        return False
        
    finally:
        if cur:
            cur.close()
        if conn:
            put_db(conn)
