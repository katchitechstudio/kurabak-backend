import os

class Config:
    """KuraBak Backend genel ayarları"""
    
    # ======================================
    # DATABASE
    # ======================================
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = os.environ.get("DB_PORT", "5432")
    DB_USER = os.environ.get("DB_USER", "postgres")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "kurabak")
    
    # Eğer Render/Heroku DATABASE_URL veriyorsa override et
    DATABASE_URL = os.environ.get("DATABASE_URL")
    
    # ======================================
    # CollectAPI Token
    # ======================================
    COLLECTAPI_TOKEN = os.environ.get("COLLECTAPI_TOKEN")
    
    # ======================================
    # Döviz (Currency) Ayarları
    # Sadece 15 döviz işlenecek
    # ======================================
    CURRENCIES_LIST = [
        "USD", "EUR", "JPY", "GBP", "CNY",
        "CHF", "CAD", "AUD", "NZD", "SGD",
        "HKD", "SEK", "KRW", "NOK", "INR"
    ]
    
    # ======================================
    # ALTIN FORMATLARI
    # ======================================
    GOLD_FORMATS = [
        "Gram Altın",
        "ONS Altın",
        "Çeyrek Altın",
        "Yarım Altın",
        "Tam Altın",
        "Cumhuriyet Altını",
        "Has Altın",
        "Ziynet Altın",
        "Reşat Lira Altın"
    ]
    
    # ======================================
    # GÜMÜŞ FORMATLARI
    # ======================================
    SILVER_FORMATS = ["Gümüş"]
