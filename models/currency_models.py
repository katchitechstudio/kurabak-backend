import logging
from models.db import get_db, put_db

logger = logging.getLogger(__name__)

def init_db():
    """
    Tüm veritabanı tablolarını otomatik oluşturur
    Mevcut tablolara ALTER TABLE ile eksik kolonları ekler
    """
    conn = None
    cur = None
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        logger.info("🔧 Veritabanı tabloları kontrol ediliyor...")
        
        # ==========================================
        # 1. CURRENCIES (Dövizler)
        # ==========================================
        cur.execute('''
            CREATE TABLE IF NOT EXISTS currencies (
                id SERIAL PRIMARY KEY,
                code VARCHAR(10) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                rate DECIMAL(10, 4) NOT NULL,
                change_percent DECIMAL(10, 2) DEFAULT 0.0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        logger.info("✅ currencies tablosu hazır")
        
        # ==========================================
        # 2. CURRENCY_HISTORY (Döviz Geçmişi)
        # ==========================================
        cur.execute('''
            CREATE TABLE IF NOT EXISTS currency_history (
                id SERIAL PRIMARY KEY,
                code VARCHAR(10) NOT NULL,
                rate DECIMAL(10, 4) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Index oluştur (varsa skip eder)
        cur.execute('''
            DO $$ 
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_indexes 
                    WHERE indexname = 'idx_currency_history_code_date'
                ) THEN
                    CREATE INDEX idx_currency_history_code_date 
                    ON currency_history(code, created_at DESC);
                END IF;
            END $$;
        ''')
        logger.info("✅ currency_history tablosu hazır")
        
        # ==========================================
        # 3. GOLDS (Altın)
        # ==========================================
        cur.execute('''
            CREATE TABLE IF NOT EXISTS golds (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                buying DECIMAL(10, 2) DEFAULT 0.0,
                selling DECIMAL(10, 2) DEFAULT 0.0,
                rate DECIMAL(10, 2) NOT NULL,
                change_percent DECIMAL(10, 2) DEFAULT 0.0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        logger.info("✅ golds tablosu hazır")
        
        # ==========================================
        # 4. GOLD_HISTORY (Altın Geçmişi)
        # ==========================================
        cur.execute('''
            CREATE TABLE IF NOT EXISTS gold_history (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                rate DECIMAL(10, 2) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            DO $$ 
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_indexes 
                    WHERE indexname = 'idx_gold_history_name_date'
                ) THEN
                    CREATE INDEX idx_gold_history_name_date 
                    ON gold_history(name, created_at DESC);
                END IF;
            END $$;
        ''')
        logger.info("✅ gold_history tablosu hazır")
        
        # ==========================================
        # 5. GOLD_DAILY_OPENING (Altın Günlük Açılış) ⭐
        # ==========================================
        cur.execute('''
            CREATE TABLE IF NOT EXISTS gold_daily_opening (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                opening_rate DECIMAL(10, 2) NOT NULL,
                date DATE NOT NULL DEFAULT CURRENT_DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(name, date)
            )
        ''')
        
        cur.execute('''
            DO $$ 
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_indexes 
                    WHERE indexname = 'idx_gold_daily_opening_name_date'
                ) THEN
                    CREATE INDEX idx_gold_daily_opening_name_date 
                    ON gold_daily_opening(name, date);
                END IF;
            END $$;
        ''')
        logger.info("✅ gold_daily_opening tablosu hazır")
        
        # ==========================================
        # 6. SILVERS (Gümüş)
        # ==========================================
        cur.execute('''
            CREATE TABLE IF NOT EXISTS silvers (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                buying DECIMAL(10, 2) DEFAULT 0.0,
                selling DECIMAL(10, 2) DEFAULT 0.0,
                rate DECIMAL(10, 2) NOT NULL,
                change_percent DECIMAL(10, 2) DEFAULT 0.0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        logger.info("✅ silvers tablosu hazır")
        
        # ==========================================
        # 7. SILVER_HISTORY (Gümüş Geçmişi)
        # ==========================================
        cur.execute('''
            CREATE TABLE IF NOT EXISTS silver_history (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                rate DECIMAL(10, 2) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            DO $$ 
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_indexes 
                    WHERE indexname = 'idx_silver_history_name_date'
                ) THEN
                    CREATE INDEX idx_silver_history_name_date 
                    ON silver_history(name, created_at DESC);
                END IF;
            END $$;
        ''')
        logger.info("✅ silver_history tablosu hazır")
        
        conn.commit()
        logger.info("🎉 Tüm veritabanı tabloları başarıyla hazırlandı!")
        
        # Tablo sayılarını göster
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        tables = [row[0] for row in cur.fetchall()]
        logger.info(f"📊 Mevcut tablolar ({len(tables)}): {', '.join(tables)}")
        
    except Exception as e:
        logger.error(f"❌ Veritabanı başlatma hatası: {e}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
        raise e
        
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


def check_table_exists(table_name):
    """
    Belirli bir tablonun var olup olmadığını kontrol eder
    """
    conn = None
    cur = None
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = %s
            )
        """, (table_name,))
        
        exists = cur.fetchone()[0]
        return exists
        
    except Exception as e:
        logger.error(f"❌ Tablo kontrolü hatası ({table_name}): {e}")
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


def verify_database_health():
    """
    Veritabanı sağlık kontrolü yapar
    Tüm gerekli tabloların var olduğunu doğrular
    """
    required_tables = [
        'currencies',
        'currency_history',
        'golds',
        'gold_history',
        'gold_daily_opening',
        'silvers',
        'silver_history'
    ]
    
    logger.info("🔍 Veritabanı sağlık kontrolü yapılıyor...")
    
    missing_tables = []
    for table in required_tables:
        if not check_table_exists(table):
            missing_tables.append(table)
    
    if missing_tables:
        logger.warning(f"⚠️ Eksik tablolar bulundu: {', '.join(missing_tables)}")
        logger.info("🔧 Eksik tablolar oluşturuluyor...")
        init_db()
        return False
    else:
        logger.info("✅ Tüm tablolar mevcut ve sağlıklı!")
        return True
