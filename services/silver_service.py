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
        
        value_str = str(value).strip()
        
        # V4'te "89,85" formatı var
        if '.' in value_str and ',' in value_str:
            value_str = value_str.replace(".", "").replace(",", ".")
        else:
            value_str = value_str.replace(",", ".")
        
        # % işaretini temizle (V4'te "%-1,61" formatı var)
        value_str = value_str.replace("%", "")
        
        return float(value_str)
    except:
        return 0.0

def fetch_silvers():
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
        
        # V4'te gümüş kodu "GUMUS" (BÜYÜK HARF - V3 ile aynı)
        if "GUMUS" in data and data["GUMUS"].get("Type") == "Gold":
            item = data["GUMUS"]
            
            selling = get_safe_float(item.get("Selling", 0))
            change_percent = get_safe_float(item.get("Change", 0))
            
            if selling > 0:
                name = "Gümüş"
                
                # Fiyatı yuvarla - gümüş için 2 hane yeterli
                rate = round(selling, 2)
                
                # Değişim oranını yuvarla
                change_percent = round(change_percent, 2)
                
                conn = get_db()
                cur = conn.cursor()
                
                cur.execute("""
                    INSERT INTO silvers (name, buying, selling, rate, change_percent, updated_at)
                    VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (name) DO UPDATE SET
                        rate=EXCLUDED.rate,
                        change_percent=EXCLUDED.change_percent,
                        updated_at=CURRENT_TIMESTAMP
                """, (name, 0, 0, rate, change_percent))
                
                conn.commit()
                
                try:
                    from utils.cache import clear_cache
                    clear_cache()
                except:
                    pass
                
                logger.info("✅ Gümüş fiyatı güncellendi (V4 API)")
                return True
            else:
                return False
        else:
            return False
            
    except Exception as e:
        logger.error(f"❌ Gümüş çekme hatası: {e}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
        return False
        
    finally:
        if cur:
            try:
                cur.close()
            except:
                pass
        if conn:
            try:
                put_db(conn)
            except:
                pass
