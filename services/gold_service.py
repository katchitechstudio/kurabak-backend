import requests
import logging
from bs4 import BeautifulSoup # HTML parçalamak için eklendi
from models.db import get_db, put_db
from config import Config

logger = logging.getLogger(__name__)

def clean_turkish_money(text):
    """
    '2.950,50' şeklindeki Türk para formatını 
    2950.50 (float) formatına çevirir.
    """
    if not text:
        return 0.0
    try:
        # Binlik ayracı (.) kaldır, ondalık ayracı (,) nokta yap
        temiz = text.replace(".", "").replace(",", ".")
        return float(temiz)
    except ValueError:
        return 0.0

def fetch_golds():
    conn = None
    cur = None
    
    try:
        logger.info("🥇 Altınlar Altin.in üzerinden çekiliyor...")
        
        # 1. ADIM: Siteden HTML'i Çek
        url = "https://altin.in/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        
        soup = BeautifulSoup(r.content, "html.parser")
        
        # 2. ADIM: Hangi altınları çekeceğimizi ve sitedeki ID'lerini tanımlayalım
        # format: "Veritabanındaki Adı": "Sitedeki ID öneki"
        # Altin.in'de alış sonu -a, satış sonu -s ile biter (örn: c-ga-a)
        target_golds = {
            "Gram Altın": "c-ga",
            "Çeyrek Altın": "c-ca",
            "Yarım Altın": "c-ya",
            "Tam Altın": "c-ta",
            "Cumhuriyet Altını": "c-cum",
            "Ata Altın": "c-ata",
            "Ons Altın": "c-ons",  # Dolar cinsinden olabilir, dikkat
            "Dolar": "c-usd",
            "Euro": "c-eur"
        }

        conn = get_db()
        cur = conn.cursor()
        added = 0
        
        for name, id_prefix in target_golds.items():
            
            # Eğer Config dosyasında bu altın yoksa atla (Senin eski kontrolün)
            if hasattr(Config, 'GOLD_FORMATS') and name not in Config.GOLD_FORMATS:
                continue

            try:
                # Siteden veriyi bul (Text olarak gelir: "2.950,50")
                buying_raw = soup.find("li", {"id": f"{id_prefix}-a"}).text
                selling_raw = soup.find("li", {"id": f"{id_prefix}-s"}).text
                
                # Temizleyip sayıya çevir
                buying = clean_turkish_money(buying_raw)
                selling = clean_turkish_money(selling_raw)
                
                # 🔥 NEGATİF/SIFIR KONTROLÜ
                if buying <= 0 or selling <= 0:
                    continue

                # Rate genelde satış fiyatı baz alınır
                rate = selling

                # 3. ADIM: Veritabanı İşlemleri (Senin kodunun aynısı)
                cur.execute("SELECT rate FROM golds WHERE name = %s", (name,))
                old_data = cur.fetchone()
                
                if old_data and old_data[0]:
                    old_rate = float(old_data[0])
                    if old_rate > 0:
                        change_percent = ((rate - old_rate) / old_rate) * 100
                    else:
                        change_percent = 0.0
                else:
                    change_percent = 0.0

                # Veritabanına kaydet (UPSERT)
                cur.execute("""
                    INSERT INTO golds (name, buying, selling, rate, change_percent, updated_at)
                    VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (name) DO UPDATE SET
                        buying=EXCLUDED.buying,
                        selling=EXCLUDED.selling,
                        rate=EXCLUDED.rate,
                        change_percent=EXCLUDED.change_percent,
                        updated_at=CURRENT_TIMESTAMP
                """, (name, buying, selling, rate, change_percent))
                
                # Geçmiş tablosuna ekle
                cur.execute("INSERT INTO gold_history (name, rate) VALUES (%s, %s)", 
                            (name, rate))
                
                added += 1

            except AttributeError:
                logger.warning(f"⚠️ {name} için veri sitede bulunamadı.")
                continue

        conn.commit()
        
        # Cache'i temizle
        try:
            from utils.cache import clear_cache
            clear_cache()
        except Exception as e:
            logger.warning(f"Cache temizleme hatası: {e}")
        
        logger.info(f"✅ {added} adet veri başarıyla güncellendi.")
        return True
        
    except Exception as e:
        logger.error(f"Veri çekme hatası: {e}")
        if conn:
            conn.rollback()
        return False
        
    finally:
        if cur:
            cur.close()
        if conn:
            put_db(conn)
