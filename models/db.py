import os
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ==========================================
# CONNECTION POOL - GLOBAL
# ==========================================
connection_pool = None


def get_db_config():
    """
    DATABASE_URL varsa onu parse et, yoksa ayrı değişkenleri kullan
    Render, Heroku gibi platformlar DATABASE_URL kullanır
    """
    database_url = os.getenv("DATABASE_URL")
    
    if database_url:
        # postgres:// → postgresql:// dönüşümü (bazı platformlar eski format kullanır)
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        
        parsed = urlparse(database_url)
        config = {
            "host": parsed.hostname,
            "port": parsed.port or 5432,
            "database": parsed.path[1:],  # başındaki / karakterini kaldır
            "user": parsed.username,
            "password": parsed.password
        }
        logger.info(f"📡 DATABASE_URL kullanılıyor (host: {parsed.hostname})")
        return config
    else:
        # Lokal geliştirme için ayrı değişkenler
        logger.info("📡 Ayrı DB_* environment değişkenleri kullanılıyor")
        return {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "database": os.getenv("DB_NAME", "kurabak"),
            "user": os.getenv("DB_USER", "postgres"),
            "password": os.getenv("DB_PASSWORD", "")
        }


def init_connection_pool():
    """
    Uygulama başlarken bir kez çağrılır
    Connection pool'u oluşturur
    """
    global connection_pool
    
    if connection_pool is None:
        try:
            db_config = get_db_config()
            
            connection_pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=10,  # Maksimum 10 bağlantı
                **db_config
            )
            logger.info("✅ Database connection pool oluşturuldu (1-10 connection)")
        except Exception as e:
            logger.error(f"❌ Connection pool oluşturulamadı: {e}")
            raise e


def get_db():
    """
    Pool'dan bir bağlantı al
    """
    global connection_pool
    
    if connection_pool is None:
        init_connection_pool()
    
    try:
        conn = connection_pool.getconn()
        return conn
    except Exception as e:
        logger.error(f"❌ Connection alınamadı: {e}")
        raise e


def put_db(conn):
    """
    Bağlantıyı pool'a geri ver (kapatma!)
    """
    global connection_pool
    
    if connection_pool and conn:
        try:
            connection_pool.putconn(conn)
        except Exception as e:
            logger.error(f"❌ Connection geri verilemedi: {e}")


@contextmanager
def get_db_connection():
    """
    Context manager - bağlantıyı otomatik kapat
    
    Kullanım:
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT ...")
    """
    conn = get_db()
    try:
        yield conn
    finally:
        put_db(conn)


@contextmanager
def get_db_cursor():
    """
    Context manager - hem cursor hem connection'ı otomatik kapat
    
    Kullanım:
    with get_db_cursor() as (conn, cur):
        cur.execute("SELECT ...")
        conn.commit()
    """
    conn = get_db()
    cur = None
    try:
        cur = conn.cursor()
        yield conn, cur
    finally:
        if cur:
            try:
                cur.close()
            except:
                pass
        put_db(conn)


def close_all_connections():
    """
    Tüm bağlantıları kapat (uygulama kapanırken)
    """
    global connection_pool
    
    if connection_pool:
        connection_pool.closeall()
        logger.info("🔒 Tüm database bağlantıları kapatıldı")
