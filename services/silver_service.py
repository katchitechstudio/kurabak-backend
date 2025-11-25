import requests
import logging
from bs4 import BeautifulSoup
from models.db import get_db, put_db
# Config importuna gerek yok çünkü API key kullanmıyoruz artık

logger = logging.getLogger(__name__)

def clean_turkish_money(text):
    """
    '34,50' metnini 34.50 (float) sayısına çevirir.
    """
    if not text:
        return 0.0
    try:
        # Binlik ayracı (.) kaldır, ondalık ayracı (,) nokta yap
        temiz = text.replace(".", "").replace(",", ".")
        return float(temiz)
    except ValueError:
        return 0.0

def fetch_silvers():
    conn = None
    cur = None
    
    try:
        logger.info("🥈 Gümüş verisi Altin.in üzerinden çekiliyor...")
        
        # 1. ADIM: Siteye Bağlan
        url = "https://altin.in/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "html.parser")
        
        # 2. ADIM: Gümüş Verisini Bul (c-gum)
        try:
            buying_raw = soup.find("li", {"id": "c-gum-a"}).text # Alış
            selling_raw = soup.find("li", {"id": "c-gum-s"}).text # Satış
            
            # Temizle ve Sayıya Çevir
            buying = clean_turkish_money(buying_raw)
            selling = clean_turkish_money(selling_raw)
            
            name = "Gümüş"
            
            # Hatalı veri kontrolü
            if buying <= 0 or selling <= 0:
                logger.warning(f"⚠️ {name} fiyatı alınamadı (0 veya negatif).")
                return False
            
            # Genelde ekranda gösterilen "Kur" satış fiyatıdır
            rate = selling 
            
            conn = get_db()
            cur = conn.cursor()
            
            # 3. ADIM: Veritabanı İşlemleri (silvers tablosu)
            
            # Değişim oranını hesaplamak için eski veriyi çek
            cur.execute("SELECT rate FROM silvers WHERE name = %s", (name,))
            old_data = cur.fetchone()
            
            change_percent = 0.0
            if old_data and old_data[0]:
                old_rate = float(old_data[0])
                if old_rate > 0:
                    change_percent = ((rate - old_rate) / old_rate) * 100
            
            # Veritabanına Kaydet (UPSERT)
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
            
            # Geçmiş Tablosuna Ekle
            cur.execute("INSERT INTO silver_history (name, rate) VALUES (%s, %s)", 
                        (name, rate))
            
            conn.commit()
            
            # Cache Temizle
            try:
                from utils.cache import clear_cache
                clear_cache()
            except Exception as e:
                logger.warning(f"Cache temizleme hatası: {e}")
            
            logger.info("✅ Gümüş verisi güncellendi.")
            return True

        except AttributeError:
            logger.warning("⚠️ Gümüş verisi sitede bulunamadı (HTML ID değişmiş olabilir).")
            return False

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
