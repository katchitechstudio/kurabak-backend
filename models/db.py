import os
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

connection_pool = None

def get_db_config():
    database_url = os.getenv("DATABASE_URL")
    
    if database_url:
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        
        parsed = urlparse(database_url)
        config = {
            "host": parsed.hostname,
            "port": parsed.port or 5432,
            "database": parsed.path[1:],
            "user": parsed.username,
            "password": parsed.password
        }
        logger.info(f"📡 DATABASE_URL kullanılıyor (host: {parsed.hostname})")
        return config
    else:
        logger.info("📡 Ayrı DB_* environment değişkenleri kullanılıyor")
        return {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "database": os.getenv("DB_NAME", "kurabak"),
            "user": os.getenv("DB_USER", "postgres"),
            "password": os.getenv("DB_PASSWORD", "")
        }

def init_connection_pool():
    global connection_pool
    
    if connection_pool is None:
        try:
            db_config = get_db_config()
            
            connection_pool = psycopg2.pool.SimpleConnectionPool(
                minconn=2,
                maxconn=20,
                **db_config
            )
            logger.info("✅ Database connection pool oluşturuldu (2-20 connection)")
        except Exception as e:
            logger.error(f"❌ Connection pool oluşturulamadı: {e}")
            raise e

def get_db():
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
    global connection_pool
    
    if connection_pool and conn:
        try:
            connection_pool.putconn(conn)
        except Exception as e:
            logger.error(f"❌ Connection geri verilemedi: {e}")

@contextmanager
def get_db_connection():
    conn = get_db()
    try:
        yield conn
    finally:
        put_db(conn)

@contextmanager
def get_db_cursor():
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
    global connection_pool
    
    if connection_pool:
        connection_pool.closeall()
        logger.info("🔒 Tüm database bağlantıları kapatıldı")
