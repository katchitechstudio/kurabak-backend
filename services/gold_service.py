import requests
import logging
from models.db import get_db_cursor

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
        
        # V4'te "5.953,42" formatı var
        if '.' in value_str and ',' in value_str:
            value_str = value_str.replace(".", "").replace(",", ".")
        else:
            value_str = value_str.replace(",", ".")
        
        # % işaretini temizle (V4'te "%0,03" formatı var)
        value_str = value_str.replace("%", "")
        
        return float(value_str)
    except:
        return 0.0

def fetch_golds():
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
        
        # DEBUG: API'den gelen TÜM anahtarları logla
        logger.info(f"🔍 API'den toplam {len(data)} anahtar geldi")
        gold_keys = [k for k in data.keys() if data[k].get("Type") == "Gold"]
        logger.info(f"🔍 Type='Gold' olan anahtarlar: {gold_keys[:10]}")  # İlk 10 tanesini göster
        
        # V4'te altın kodları tire ile ayrılmış küçük harf
        gold_mapping = {✅ {key} bulundu - Type: {data[key].get('Type')}")
            else:
                logger.warning(f"  ❌ {key} bulunamadı")
        
        # V4'te altın kodları tire ile ayrılmış küçük harf
        gold_mapping = {
            "gram-altin": "Gram Altın",
            "ceyrek-altin": "Çeyrek Altın",
            "yarim-altin": "Yarım Altın",
            "tam-altin": "Tam Altın",
            "cumhuriyet-altini": "Cumhuriyet Altını"
        }
        
        with get_db_cursor() as (conn, cur):
            added = 0
            
            for api_code, db_name in gold_mapping.items():
                if api_code not in data or data[api_code].get("Type") != "Gold":
                    continue
                
                item = data[api_code]
                selling = get_safe_float(item.get("Selling", 0))
                
                if selling <= 0:
                    continue
                
                # Fiyatları yuvarla - altın için 2 hane yeterli
                rate = round(selling, 2)
                
                # Değişim oranını yuvarla
                change_percent = round(get_safe_float(item.get("Change", 0)), 2)
                
                cur.execute("""
                    INSERT INTO golds (name, buying, selling, rate, change_percent, updated_at)
                    VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (name) DO UPDATE SET
                        rate=EXCLUDED.rate,
                        change_percent=EXCLUDED.change_percent,
                        updated_at=CURRENT_TIMESTAMP
                """, (db_name, 0, 0, rate, change_percent))
                
                added += 1
            
            conn.commit()
        
        logger.info(f"✅ {added} altın fiyatı güncellendi (V4 API)")
        
        try:
            from utils.cache import clear_cache
            clear_cache()
        except:
            pass
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Altın çekme hatası: {e}")
        return False
