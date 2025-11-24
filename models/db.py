import psycopg2
from psycopg2.pool import SimpleConnectionPool
from config import Config
import urllib.parse as urlparse
import os

# ==========================================
# DATABASE URL (Render, Heroku, Railway)
# ==========================================
DATABASE_URL = os.environ.get("DATABASE_URL", None)

if DATABASE_URL:
    # URL parse et
    url = urlparse.urlparse(DATABASE_URL)
    DB_USER = url.username
    DB_PASSWORD = url.password
    DB_HOST = url.hostname
    DB_PORT = url.port
    DB_NAME = url.path[1:]   # /dbname → dbname
else:
    # Lokal ortam
    DB_USER = Config.DB_USER
    DB_PASSWORD = Config.DB_PASSWORD
    DB_HOST = Config.DB_HOST
    DB_PORT = Config.DB_PORT
    DB_NAME = Config.DB_NAME

# ==========================================
# CONNECTION POOL
# ==========================================
db_pool = SimpleConnectionPool(
    minconn=1,
    maxconn=10,
    user=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME
)

# ==========================================
# PUBLIC METHODS
# ==========================================
def get_db():
    """Pool'dan bağlantı al"""
    return db_pool.getconn()

def put_db(conn):
    """Bağlantıyı pool'a geri bırak"""
    db_pool.putconn(conn)
