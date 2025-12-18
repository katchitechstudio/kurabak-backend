import requests
import logging
from models.db import get_db, put_db

logger = logging.getLogger(__name__)

def get_safe_float(value):
    """
    V4 API'de değerler string olarak geliyor ve virgül kullanılıyor.
    Change değerleri '%0,03' formatında geliyor.
    """
    try:
        if isinstance(value, (int, float)):
            return float(value)
        value_str = str(value).replace(",", ".").replace("%", "").strip()
        # V4'te bazen "$4.330,99" gibi dolar işareti olabiliyor
        value_str = value_str.replace("$", "").replace(" ", "")
        return float(value_str)
    except:
        return 0.0

def fetch_currencies():
    conn = None
    cur = None
    
    try:
        # V4 API endpoint
        url = "https://finans.truncgil.com/v4/today.json"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        }
        
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        
        currency_codes = [
            "USD", "EUR", "GBP", "JPY", "CHF",
            "CNY", "CAD", "AUD", "DKK", "SEK",
            "NOK", "SAR", "QAR", "KWD", "AED"
        ]
        
        conn = get_db()
        cur = conn.cursor()
        
        for code in currency_codes:
            if code not in data:
                continue
            
            item = data[code]
            
            # V4'te Type kontrolü yapıyoruz (Currency olmalı)
            if item.get("Type") != "Currency":
                continue
            
            # V4'te alan isimleri büyük harfle başlıyor (V3'le aynı)
            name = item.get("Name", code)
            selling = get_safe_float(item.get("Selling", 0))
            buying = get_safe_float(item.get("Buying", 0))
            change_percent = get_safe_float(item.get("Change", 0))
            
            # V4'te JPY zaten 100 yen için hazır geliyor
            # Ek işlem yapılmayacak
            
            if selling <= 0:
                continue
            
            # Fiyatları yuvarla - büyük değerler için 2, küçükler için 4 hane
            if selling >= 10:
                selling = round(selling, 2)  # 42.7352 -> 42.73
            else:
                selling = round(selling, 4)  # 0.5355 -> 0.5355
            
            # Değişim oranını 2 hane yap
            change_percent = round(change_percent, 2)  # 0.03 -> 0.03
            
            cur.execute("""
                INSERT INTO currencies (code, name, rate, change_percent, updated_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (code) DO UPDATE SET
                    name=EXCLUDED.name,
                    rate=EXCLUDED.rate,
                    change_percent=EXCLUDED.change_percent,
                    updated_at=CURRENT_TIMESTAMP
            """, (code, name, selling, change_percent))
        
        conn.commit()
        
        try:
            from utils.cache import clear_cache
            clear_cache()
        except:
            pass
        
        logger.info("✅ Döviz verileri güncellendi (V4 API)")
        return True
        
    except Exception as e:
        logger.error(f"❌ fetch_currencies hatası: {e}")
        if conn:
            conn.rollback()
        return False
        
    finally:
        if cur:
            cur.close()
        if conn:
            put_db(conn)

def cleanup_database():
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute("VACUUM ANALYZE currencies")
        cur.execute("VACUUM ANALYZE golds")
        cur.execute("VACUUM ANALYZE silvers")
        
        logger.info("🧹 Veritabanı optimize edildi (VACUUM ANALYZE)")
        
    except Exception as e:
        logger.error(f"❌ Temizlik hatası: {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            put_db(conn)
