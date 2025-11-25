import requests
import logging
from bs4 import BeautifulSoup
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
        temiz = text.replace(".", "").replace(",", ".")
        return float(temiz)
    except ValueError:
        return 0.0

def fetch_golds():
    conn = None
    cur = None
    
    try:
        logger.info("🥇 Altınlar Altin.in üzerinden çekiliyor...")
        
        # 1. ADIM: Siteden HTML'i Çek (GÜÇLÜ HEADER İLE)
        url = "https://altin.in/"
        
        # Site bizi bot sanmasın diye tam bir tarayıcı gibi davranıyoruz
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.google.com/",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }
        
        # Timeout süresini 15 saniyeye çıkardık
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        
        soup = BeautifulSoup(r.content, "html.parser")
        
        # 2. ADIM: Altın ID Eşleşmeleri
        target_golds = {
            "Gram Altın": "c-ga",
            "Çeyrek Altın": "c-ca",
            "Yarım Altın": "c-ya",
            "Tam Altın": "c-ta",
            "Cumhuriyet Altını": "c-cum",
            "Ata Altın": "c-ata",
            "Ons Altın": "c-ons",
            "Dolar": "c-usd",
            "Euro": "c-eur"
        }

        conn = get_db()
        cur = conn.cursor()
        added = 0
        
        for name, id_prefix in target_golds.items():
            
            # Config kontrolü (Opsiyonel)
            if hasattr(Config, 'GOLD_FORMATS') and name not in Config.GOLD_FORMATS:
                continue

            try:
                # Siteden veriyi bul
                buying_raw = soup.find("li", {"id": f"{id_prefix}-a"}).text
                selling_raw = soup.find("li", {"id": f"{id_prefix}-s"}).text
                
                # Temizle
                buying = clean_turkish_money(buying_raw)
                selling = clean_turkish_money(selling_raw)
                
                # Kontrol
                if buying <= 0 or selling <= 0:
                    continue

                rate = selling

                # --- VERİTABANI İŞLEMLERİ ---
                cur.execute("SELECT rate FROM golds WHERE name = %s", (name,))
                old_data = cur.fetchone()
                
                change_percent = 0.0
                if old_data and old_data[0]:
                    old_rate = float(old_data[0])
                    if old_rate > 0:
                        change_percent = ((rate - old_rate) / old_rate) * 100

                # Kaydet (UPSERT)
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
                
                # Geçmişe Ekle
                cur.execute("INSERT INTO gold_history (name, rate) VALUES (%s, %s)", 
                            (name, rate))
                
                added += 1

            except AttributeError:
                logger.warning(f"⚠️ {name} için veri sitede bulunamadı (Bot koruması veya ID değişimi).")
                continue

        conn.commit()
        
        # Cache Temizle
        try:
            from utils.cache import clear_cache
            clear_cache()
        except Exception as e:
            logger.warning(f"Cache temizleme hatası: {e}")
        
        logger.info(f"✅ {added} adet altın verisi güncellendi.")
        return True
        
    except Exception as e:
        logger.error(f"Altın çekme hatası: {e}")
        if conn:
            conn.rollback()
        return False
        
    finally:
        if cur:
            cur.close()
        if conn:
            put_db(conn)
