import requests
import logging
from models.db import get_db, put_db

logger = logging.getLogger(__name__)

def get_safe_float(item, keys):
    """Veriyi esnek şekilde (büyük/küçük harf, virgül/nokta fark etmeksizin) float'a çevirir."""
    for key in keys:
        if key in item:
            try:
                # Virgülü ondalık ayracı yap ve float'a çevir
                val = str(item[key]).replace(",", ".")
                return float(val)
            except:
                continue
    return 0.0

def fetch_currencies():
    conn = None
    cur = None
    
    try:
        logger.info("💱 Dövizler Truncgil API üzerinden çekiliyor (Sade Mod)...")
        
        url = "https://finans.truncgil.com/today.json"
        headers = {"User-Agent": "Mozilla/5.0"}
        
        # 🔥 İYİLEŞTİRME 1: API bağlantı ve HTTP başarı kontrolü
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status() # 4XX veya 5XX hatası varsa burada durur

        data = r.json()
        
        # 🔥 İYİLEŞTİRME 2: JSON yapısının doğruluğunu kontrol et
        if not data or not isinstance(data, dict):
             logger.error("API'den geçersiz/boş JSON cevabı geldi.")
             return False
        
        target_currencies = [
            ("USD", "USD", "Amerikan Doları"),
            ("EUR", "EUR", "Euro"),
            ("GBP", "GBP", "İngiliz Sterlini")
        ]
        
        # DB bağlantısı sadece veri çekildiğinde açılır
        conn = get_db()
        cur = conn.cursor()
        added = 0
        
        for my_code, api_key, my_name in target_currencies:
            # API'den veri çek (Büyük/küçük harf kontrolü ile)
            item = data.get(api_key) or data.get(api_key.lower())
            
            if not item or not isinstance(item, dict):
                logger.warning(f"⚠️ {my_code} verisi API cevabında bulunamadı veya formatı hatalı.")
                continue

            try:
                # Satış Fiyatını (Selling) alıyoruz
                selling = get_safe_float(item, ["Selling", "selling", "Satış", "satis"])
                
                if selling <= 0: continue
                rate = selling
                
                # --- DB İŞLEMLERİ (RATE kaydediliyor) ---
                cur.execute("SELECT rate FROM currencies WHERE code = %s", (my_code,))
                old_data = cur.fetchone()
                
                change_percent = 0.0
                if old_data and old_data[0]:
                    old_rate = float(old_data[0])
                    if old_rate > 0:
                        change_percent = ((rate - old_rate) / old_rate) * 100

                # Sadece RATE kaydediyoruz (DB'de buying/selling sütunları olmadığı için)
                cur.execute("""
                    INSERT INTO currencies (code, name, rate, change_percent, updated_at)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (code) DO UPDATE SET
                        name=EXCLUDED.name,
                        rate=EXCLUDED.rate,
                        change_percent=EXCLUDED.change_percent,
                        updated_at=CURRENT_TIMESTAMP
                """, (my_code, my_name, rate, change_percent))
                
                cur.execute("INSERT INTO currency_history (code, rate) VALUES (%s, %s)", (my_code, rate))
                added += 1

            except Exception as e:
                logger.error(f"❌ {my_code} işlenirken DB hatası: {e}")
                conn.rollback() # Hata oluşursa işlemi geri al
                continue

        conn.commit() # Tüm işlemler başarılıysa kaydet
        
        try:
            from utils.cache import clear_cache
            clear_cache()
        except: pass
            
        logger.info(f"✅ {added} döviz güncellendi.")
        return True
        
    except requests.exceptions.HTTPError as he:
        # HTTP Hatası (404, 500, vb.)
        logger.error(f"🌐 API Bağlantı Hatası: HTTP kodu {he.response.status_code}. İşlem atlandı.")
        if conn: conn.rollback()
        return False
    except Exception as e:
        logger.error(f"Genel Çekme Hatası: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if cur: cur.close()
        if conn: put_db(conn) # DB bağlantısını geri havuza bırak
