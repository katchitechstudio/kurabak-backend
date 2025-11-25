import requests
import logging
from bs4 import BeautifulSoup
from models.db import get_db, put_db
from config import Config

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

def fetch_currencies():
    conn = None
    cur = None
    
    try:
        logger.info("💱 Dövizler Altin.in üzerinden çekiliyor...")
        
        # 1. ADIM: Siteye Bağlan (GÜÇLENDİRİLMİŞ HEADER)
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
        
        # Timeout süresini 15 saniyeye çıkardık, garanti olsun
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "html.parser")
        
        # 2. ADIM: Hangi Dövizleri Çekeceğiz?
        target_currencies = [
            ("USD", "Amerikan Doları", "c-usd"),
            ("EUR", "Euro", "c-eur"),
            ("GBP", "İngiliz Sterlini", "c-gbp")
        ]
        
        conn = get_db()
        cur = conn.cursor()
        added = 0
        
        for code, name, id_prefix in target_currencies:
            try:
                # Siteden verileri bul
                buying_raw = soup.find("li", {"id": f"{id_prefix}-a"}).text
                selling_raw = soup.find("li", {"id": f"{id_prefix}-s"}).text
                
                # Temizle ve Sayıya Çevir
                buying = clean_turkish_money(buying_raw)
                selling = clean_turkish_money(selling_raw)
                
                # Hatalı veri kontrolü
                if buying <= 0 or selling <= 0:
                    logger.warning(f"⚠️ {code} için fiyat alınamadı (0 veya negatif).")
                    continue
                
                rate = selling
                
                # --- VERİTABANI İŞLEMLERİ ---
                
                # Değişim oranını hesaplamak için eski veriyi çek
                cur.execute("SELECT rate FROM currencies WHERE code = %s", (code,))
                old_data = cur.fetchone()
                
                change_percent = 0.0
                if old_data and old_data[0]:
                    old_rate = float(old_data[0])
                    if old_rate > 0:
                        change_percent = ((rate - old_rate) / old_rate) * 100

                # Veritabanına Kaydet (UPSERT)
                cur.execute("""
                    INSERT INTO currencies (code, name, buying, selling, rate, change_percent, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (code) DO UPDATE SET
                        name=EXCLUDED.name,
                        buying=EXCLUDED.buying,
                        selling=EXCLUDED.selling,
                        rate=EXCLUDED.rate,
                        change_percent=EXCLUDED.change_percent,
                        updated_at=CURRENT_TIMESTAMP
                """, (code, name, buying, selling, rate, change_percent))
                
                # Geçmiş Tablosuna Ekle
                cur.execute("""
                    INSERT INTO currency_history (code, rate)
                    VALUES (%s, %s)
                """, (code, rate))
                
                added += 1

            except AttributeError:
                logger.warning(f"⚠️ {code} verisi sitede bulunamadı (HTML ID değişmiş olabilir).")
                continue
            except Exception as e:
                logger.error(f"❌ {code} işlenirken hata: {e}")
                continue

        conn.commit()
        
        # Cache Temizle
        try:
            from utils.cache import clear_cache
            clear_cache()
        except Exception as e:
            logger.warning(f"Cache temizleme hatası: {e}")
            
        logger.info(f"✅ {added} adet döviz güncellendi.")
        return True
        
    except Exception as e:
        logger.error(f"Döviz çekme genel hatası: {e}")
        if conn:
            conn.rollback()
        return False
        
    finally:
        if cur:
            cur.close()
        if conn:
            put_db(conn)
