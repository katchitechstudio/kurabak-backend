import requests
import logging
from models.db import get_db, put_db

logger = logging.getLogger(__name__)

def get_safe_float(value):
    try:
        if isinstance(value, (int, float)): 
            return float(value)
        return float(str(value).replace(",", "."))
    except: 
        return 0.0

def fetch_currencies():
    conn = None
    cur = None
    
    try:
        logger.info("🌍 Dövizler Truncgil API üzerinden çekiliyor...")
        
        url = "https://finans.truncgil.com/v4/today.json"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        }
        
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        
        # Uygulamadaki 15 popüler döviz
        currency_codes = [
            "USD", "EUR", "GBP", "JPY", "CHF",
            "CNY", "CAD", "AUD", "DKK", "SEK",
            "NOK", "SAR", "QAR", "KWD", "AED"
        ]
        
        conn = get_db()
        cur = conn.cursor()
        added = 0
        
        for code in currency_codes:
            if code in data and data[code].get("Type") == "Currency":
                item = data[code]
                
                name = item.get("Name", code)
                selling = get_safe_float(item.get("Selling", 0))
                change_absolute = get_safe_float(item.get("Change", 0))
                
                # 🔥 JAPON YENİ DÜZELTMESİ
                # Truncgil API, JPY'yi 100 yen birimi olarak veriyor
                # Bizim uygulama 1 yen göstermeli
                if code == "JPY":
                    selling = selling * 100
                    change_absolute = change_absolute * 100
                    logger.info(f"🇯🇵 JPY düzeltildi: {selling} (x100)")
                
                if selling <= 0: 
                    logger.warning(f"⚠️ {code}: Geçersiz selling değeri: {selling}")
                    continue
                
                # 🔥 YÜZDE DEĞİŞİM HESAPLAMA
                # Change = Bugünkü Fiyat - Dünkü Fiyat
                # Dünkü Fiyat = Bugünkü Fiyat - Change
                # Yüzde = (Change / Dünkü Fiyat) * 100
                
                previous_price = 0.0  # ← HER DÖVİZ İÇİN SIFIRDAN BAŞLA
                change_percent = 0.0
                
                if abs(change_absolute) > 0.0001:  # Sıfır kontrolü
                    previous_price = selling - change_absolute
                    if previous_price > 0:
                        change_percent = (change_absolute / previous_price) * 100
                    else:
                        change_percent = 0.0
                else:
                    previous_price = selling  # Change yoksa previous = current
                    change_percent = 0.0
                
                rate = selling
                
                # 🔍 DEBUG LOG (Japon Yeni için özel)
                if code == "JPY":
                    logger.info(f"📊 JPY Debug:")
                    logger.info(f"  - Selling: {selling}")
                    logger.info(f"  - Change (absolute): {change_absolute}")
                    logger.info(f"  - Previous Price: {selling - change_absolute}")
                    logger.info(f"  - Change Percent: {change_percent:.2f}%")
                
                cur.execute("""
                    INSERT INTO currencies (code, name, rate, change_percent, updated_at)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (code) DO UPDATE SET
                        name=EXCLUDED.name,
                        rate=EXCLUDED.rate,
                        change_percent=EXCLUDED.change_percent,
                        updated_at=CURRENT_TIMESTAMP
                """, (code, name, rate, change_percent))
                
                cur.execute("INSERT INTO currency_history (code, rate) VALUES (%s, %s)", (code, rate))
                added += 1
        
        conn.commit()
        
        try: 
            from utils.cache import clear_cache
            clear_cache()
        except: 
            pass
            
        logger.info(f"✅ Truncgil: {added} döviz güncellendi.")
        return True
        
    except requests.exceptions.RequestException as req_e:
        logger.error(f"❌ Truncgil Döviz Hatası (Request): {req_e}")
        if conn: conn.rollback()
        return False
    except Exception as e:
        logger.error(f"❌ Truncgil Döviz Hatası (Genel): {e}")
        if conn: conn.rollback()
        return False
        
    finally:
        if cur: cur.close()
        if conn: 
            from models.db import put_db
            put_db(conn)
