import requests
import logging
from models.db import get_db, put_db
from config import Config

logger = logging.getLogger(__name__)

def fetch_currencies():
    conn = None
    cur = None
    
    try:
        logger.info("💱 Dövizler çekiliyor (currencyToAll)...")
        
        headers = {
            'authorization': f'apikey {Config.COLLECTAPI_TOKEN}'
        }
        
        # 🔥 YENİ ENDPOINT: currencyToAll (gerçek fiyatlar)
        url = "https://api.collectapi.com/economy/currencyToAll"
        params = {
            'int': '10',
            'base': 'TRY'  # TRY bazlı fiyatlar
        }
        
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        if not data.get("success"):
            logger.error(f"API hata: {data}")
            return False
        
        items = data.get("result", {}).get("data", [])
        if not isinstance(items, list) or len(items) == 0:
            logger.error("API döviz listesi boş.")
            return False
        
        # 🔥 YENİ: TRY'yi manuel olarak listeye ekle (API base=TRY olunca TRY'yi göstermiyor)
        items.append({
            "code": "TRY",
            "name": "Turkish Lira",
            "rate": 1.0
        })
        
        logger.info(f"✅ {len(items)} döviz alındı")
        
        conn = get_db()
        cur = conn.cursor()
        
        added = 0
        
        for row in items:
            code = row.get("code")
            name = row.get("name")
            
            try:
                # 🔥 GÜVENLİ PARSE: String veya number olabilir
                rate_value = row.get("rate")
                if isinstance(rate_value, str):
                    rate = float(rate_value.replace(",", "."))  # Virgül varsa nokta yap
                else:
                    rate = float(rate_value)
                
                # 🔥 YENİ: NEGATİF/SIFIR KONTROLÜ
                if rate <= 0:
                    logger.warning(f"⚠️ {code} rate={rate} (negatif/sıfır), atlanıyor")
                    continue
                
                # 🔥 YENİ MANTIK: base=TRY olduğu için rate zaten TRY cinsinden
                # Örnek: USD rate = 0.0236 → 1 TRY = 0.0236 USD → 1 USD = 1/0.0236 = 42.37 TRY
                
                if code == "TRY":
                    price_tl = 1.0  # 1 TL = 1 TL
                else:
                    # Diğer dövizler: 1 TRY = rate [döviz]
                    # Örnek: 1 TRY = 0.0236 USD → 1 USD = 1/0.0236 = 42.37 TRY
                    price_tl = 1.0 / rate
                
            except Exception as e:
                logger.error(f"{code} hesaplama hatası: {e}")
                continue
            
            # 🔥 YENİ: FİYAT SAĞLIK KONTROLÜ
            if price_tl <= 0 or price_tl > 1000000:
                logger.warning(f"⚠️ {code} price_tl={price_tl} (anormal), atlanıyor")
                continue
            
            # Değişim oranı için önceki fiyatı al
            cur.execute("SELECT rate FROM currencies WHERE code = %s", (code,))
            old_data = cur.fetchone()
            
            if old_data and old_data[0]:
                old_price = float(old_data[0])
                if old_price > 0:
                    change_percent = ((price_tl - old_price) / old_price) * 100
                else:
                    change_percent = 0.0
            else:
                change_percent = 0.0  # İlk kayıt
            
            # Veritabanına kaydet
            cur.execute("""
                INSERT INTO currencies (code, name, rate, change_percent, updated_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (code) DO UPDATE SET
                    name=EXCLUDED.name,
                    rate=EXCLUDED.rate,
                    change_percent=EXCLUDED.change_percent,
                    updated_at=CURRENT_TIMESTAMP
            """, (code, name, price_tl, change_percent))
            
            cur.execute("""
                INSERT INTO currency_history (code, rate)
                VALUES (%s, %s)
            """, (code, price_tl))
            
            added += 1
        
        conn.commit()
        
        # 🔥 YENİ: Cache'i temizle
        try:
            from utils.cache import clear_cache
            clear_cache()
        except Exception as e:
            logger.warning(f"Cache temizleme hatası: {e}")
        
        logger.info(f"✅ {added} döviz güncellendi")
        return True
        
    except Exception as e:
        logger.error(f"Döviz çekme hatası: {e}")
        if conn:
            conn.rollback()
        return False
        
    finally:
        # ← HATA OLSA BİLE burası çalışır!
        if cur:
            cur.close()
        if conn:
            put_db(conn)
