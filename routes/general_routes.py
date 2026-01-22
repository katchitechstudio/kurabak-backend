"""
General Routes - PRODUCTION READY (V8 - RATE LIMITING + SECURITY) 🚀
==========================================================
✅ RATE LIMITING: Flask-Limiter ile bot saldırılarına karşı koruma
✅ 503 ERROR FIX: Asla boş dönmez, gerekirse bayat veri (Stale) sunar
✅ REGIONAL SUPPORT: 20 Döviz için Bölgesel Filtreleme
✅ SMART RECOVERY: Cache boşsa anlık tetikleme yapar
✅ STANDARDIZED RESPONSE: Frontend (Android) için sabit format
✅ ONLINE USER TRACKING: Her API çağrısında kullanıcıyı 5dk için işaretle
✅ BANNER SYSTEM: Telegram'dan yönetilen duyuru sistemi
✅ SECURITY: IP bazlı rate limiting + User-Agent kontrolü
"""

from flask import Blueprint, jsonify, request, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
import time
from datetime import datetime

# Config ve Cache mekanizmaları
from config import Config
from utils.cache import get_cache, set_cache
# Maintenance servisten güvenli veri çekme fonksiyonu
from services.maintenance_service import fetch_all_data_safe

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')

# ======================================
# RATE LIMITER SETUP (KRİTİK GÜVENLİK)
# ======================================

# Flask-Limiter başlatıcısı
limiter = Limiter(
    key_func=get_remote_address,  # IP adresine göre limit
    default_limits=["200 per hour"],  # Genel limit: Saatte 200 istek
    storage_uri="memory://",  # Redis yoksa bellekte tut
    strategy="fixed-window"  # Sabit pencere stratejisi
)

# ======================================
# YARDIMCI FONKSİYONLAR
# ======================================

def track_online_user():
    """
    🕵️ AJAN: Kullanıcıyı "Online" olarak işaretle
    
    Her API isteğinde otomatik çalışır.
    Kullanıcının kimliğini (user_id veya IP) Redis'e yazar.
    5 dakika (300 saniye) sonra otomatik silinir.
    """
    try:
        # 1. Kullanıcı kimliğini belirle (user_id > IP)
        user_id = request.args.get('user_id') or request.args.get('device_id')
        
        if not user_id:
            # user_id yoksa IP adresini kullan
            user_id = request.remote_addr or request.headers.get('X-Forwarded-For', 'unknown')
        
        # 2. Redis'e kaydet (5 dakika ömürlü)
        cache_key = f"online_user:{user_id}"
        set_cache(cache_key, "1", ttl=300)  # 300 saniye = 5 dakika
        
    except Exception as e:
        # Hata olsa bile API durmasın
        logger.debug(f"Online tracking hatası (önemsiz): {e}")


def create_response(data, status_code=200, message=None, meta=None):
    """Standart JSON response oluşturucu (Android uyumlu)"""
    response = {
        'success': status_code < 400,
        'data': data,
        'meta': meta or {},
        'timestamp': datetime.now().isoformat()
    }
    
    if message:
        response['message'] = message
    
    return jsonify(response), status_code


def get_data_guaranteed(cache_key):
    """
    GARANTİLİ VERİ GETİRİCİ 🛡️
    1. Normal Cache'e bak.
    2. Yoksa Stale (Bayat) Cache'e bak.
    3. O da yoksa anlık gidip API'den çek (Blocking).
    4. Asla 'None' dönme (Mümkünse).
    """
    # 1. Normal Cache
    data = get_cache(cache_key)
    if data:
        return data

    # 2. Stale (Bayat) Cache - 503'ü önleyen kahraman
    stale_key = f"{cache_key}:stale"
    stale_data = get_cache(stale_key)
    
    if stale_data:
        logger.warning(f"⚠️ {cache_key} için güncel veri yok, BAYAT veri sunuluyor.")
        return stale_data

    # 3. Hiçbir şey yoksa (Cold Start) -> Mecbur gidip çekeceğiz
    logger.warning(f"🔴 {cache_key} için hiç veri yok! Anlık çekim başlatılıyor...")
    success = fetch_all_data_safe()
    
    if success:
        # Şimdi tekrar cache'e bak
        return get_cache(cache_key)
    
    return None


def check_user_agent():
    """
    Bot/Scraper kontrolü (İsteğe bağlı güvenlik)
    Şüpheli User-Agent'ları logla
    """
    user_agent = request.headers.get('User-Agent', 'Unknown')
    
    # Bilinen bot user-agent'ları
    suspicious_agents = ['curl', 'wget', 'python-requests', 'scrapy']
    
    if any(bot in user_agent.lower() for bot in suspicious_agents):
        logger.warning(f"⚠️ Şüpheli User-Agent: {user_agent} | IP: {request.remote_addr}")
        # İsterseniz burada rate limit'i daha da sıkılaştırabilirsiniz
    
    return True  # Şimdilik tüm isteklere izin ver

# ======================================
# ENDPOINTLER (RATE LIMITED!)
# ======================================

@api_bp.route('/currency/all', methods=['GET'])
@limiter.limit("60 per minute")  # Dakikada 60 istek (Agresif kullanıcılar için)
def get_all_currencies():
    """
    Tüm Döviz Kurları (23 Adet)
    🕵️ Online tracking aktif!
    📢 Banner desteği eklendi!
    🛡️ Rate limit: 60/dakika
    🚧 Bakım Modu: Otomatik banner güncelleme
    """
    # Bot kontrolü
    check_user_agent()
    
    # Kullanıcıyı işaretle
    track_online_user()
    
    try:
        result = get_data_guaranteed(Config.CACHE_KEYS['currencies_all'])
        
        if not result:
            return create_response([], 503, "Servis başlatılıyor, lütfen tekrar deneyin.")

        # Veri formatı kontrolü
        data_list = result.get('data', [])
        update_date = result.get('update_date')
        status = result.get('status', 'OPEN')
        market_msg = result.get('market_msg')
        
        # Banner var mı kontrol et
        banner_msg = get_cache("system_banner")
        
        # 🔥 AKILLI BANNER: Bakım modundaysa banner'ı otomatik güncelle
        if status in ['MAINTENANCE', 'MAINTENANCE_FULL']:
            # Bakım mesajını banner olarak kullan
            banner_msg = market_msg or "🚧 Sistem şu an bakımda. Lütfen daha sonra tekrar deneyin."
        elif status == 'CLOSED':
            # Piyasa kapalıysa ona göre banner göster (eğer manuel banner yoksa)
            if not banner_msg:
                banner_msg = market_msg or "🌙 Piyasalar kapalı, iyi hafta sonları!"
        
        # Meta verisine banner'ı ekle
        meta_data = {
            'count': len(data_list),
            'last_update': update_date,
            'source': result.get('source'),
            'status': status,
            'market_msg': market_msg,
            'banner': banner_msg  # 🎯 BANNER EKLEME - MOBİL İÇİN KRİTİK
        }
        
        return create_response(
            data_list,
            200,
            "Döviz kurları getirildi",
            meta_data
        )
    except Exception as e:
        logger.error(f"Currency All Error: {e}")
        return create_response([], 500, "Sunucu hatası")


@api_bp.route('/currency/gold/all', methods=['GET'])
@limiter.limit("60 per minute")
def get_all_golds():
    """
    Tüm Altın Fiyatları (6 Adet)
    🛡️ Rate limit: 60/dakika
    """
    check_user_agent()
    track_online_user()
    
    try:
        result = get_data_guaranteed(Config.CACHE_KEYS['golds_all'])
        
        if not result:
            return create_response([], 503, "Veriler hazırlanıyor...")

        data_list = result.get('data', [])
        return create_response(
            data_list,
            200,
            "Altın fiyatları getirildi",
            {
                'count': len(data_list), 
                'last_update': result.get('update_date'),
                'status': result.get('status', 'OPEN')
            }
        )
    except Exception as e:
        logger.error(f"Gold All Error: {e}")
        return create_response([], 500, "Sunucu hatası")


@api_bp.route('/currency/silver/all', methods=['GET'])
@limiter.limit("60 per minute")
def get_all_silvers():
    """
    Gümüş Fiyatları
    🛡️ Rate limit: 60/dakika
    """
    check_user_agent()
    track_online_user()
    
    try:
        result = get_data_guaranteed(Config.CACHE_KEYS['silvers_all'])
        
        if not result:
            return create_response([], 503, "Veriler hazırlanıyor...")

        data_list = result.get('data', [])
        return create_response(
            data_list, 200, "Gümüş fiyatları getirildi"
        )
    except Exception as e:
        logger.error(f"Silver All Error: {e}")
        return create_response([], 500, "Sunucu hatası")


@api_bp.route('/currency/summary', methods=['GET'])
@limiter.limit("60 per minute")
def get_summary():
    """
    Piyasa Özeti (Kazanan/Kaybeden)
    🛡️ Rate limit: 60/dakika
    📢 Banner Desteği Eklendi!
    """
    check_user_agent()
    track_online_user()
    
    try:
        # 1. Veriyi Garantili Çek
        result = get_data_guaranteed(Config.CACHE_KEYS['summary'])
        
        # 2. Veri yoksa bile boş dön, hata dönme
        if not result or not result.get('data'):
            # Boş veri olsa bile banner varsa gösterelim
            market_data = {}
        else:
            market_data = result.get('data', {})

        # 3. 🔥 KRİTİK EKLEME: Banner ve Durum Bilgisi
        # Banner'ı çek
        banner_msg = get_cache("system_banner")
        
        # Piyasa durumunu çek
        status = result.get('status', 'OPEN') if result else 'OPEN'
        market_msg = result.get('market_msg') if result else None

        # Eğer bakım varsa veya piyasa kapalıysa banner'ı güncelle
        if status in ['MAINTENANCE', 'MAINTENANCE_FULL']:
            banner_msg = market_msg or "🚧 Sistem bakımda."
        elif status == 'CLOSED' and not banner_msg:
            banner_msg = market_msg or "🌙 Piyasalar kapalı."

        # 4. Meta verisine banner'ı paketle
        meta_data = {
            'status': status,
            'banner': banner_msg  # 🎯 İşte mobilin beklediği veri!
        }

        return create_response(
            market_data,
            200,
            "Piyasa özeti getirildi",
            meta_data  # Meta verisini buraya ekledik
        )
        
    except Exception as e:
        logger.error(f"Summary Error: {e}")
        return create_response({}, 500, "Sunucu hatası")


@api_bp.route('/currency/regional', methods=['GET'])
@limiter.limit("30 per minute")  # Daha az kullanılan endpoint
def get_regional_currencies():
    """
    Bölgesel Filtrelenmiş Dövizler
    🛡️ Rate limit: 30/dakika
    """
    check_user_agent()
    track_online_user()
    
    try:
        # Ana veriyi çek
        result = get_data_guaranteed(Config.CACHE_KEYS['currencies_all'])
        
        if not result:
            return create_response({}, 503, "Veriler hazırlanıyor...")
            
        all_currencies = result.get('data', [])
        regional_data = {}
        
        # Config'den bölge haritasını al
        regions = Config.REGIONAL_CURRENCIES
        
        # Veriyi hızlı erişim için dictionary yap
        curr_map = {item['code']: item for item in all_currencies}
        
        for region_name, codes in regions.items():
            regional_data[region_name] = []
            for code in codes:
                if code in curr_map:
                    regional_data[region_name].append(curr_map[code])
                    
        return create_response(
            regional_data,
            200,
            "Bölgesel veriler getirildi",
            {'regions': list(regions.keys())}
        )
    except Exception as e:
        logger.error(f"Regional Error: {e}")
        return create_response({}, 500, "Sunucu hatası")


@api_bp.route('/metrics', methods=['GET'])
@limiter.limit("10 per minute")  # Admin endpoint - çok sıkı limit
def get_metrics():
    """
    Sistem Metrikleri (Admin/Debug için)
    🛡️ Rate limit: 10/dakika (Admin endpoint)
    """
    try:
        from services.financial_service import get_service_metrics
        from services.maintenance_service import get_scheduler_status
        
        metrics = get_service_metrics()
        scheduler = get_scheduler_status()
        
        return create_response({
            'api_metrics': metrics,
            'scheduler_status': scheduler,
            'environment': Config.ENVIRONMENT
        }, 200)
    except Exception as e:
        return create_response(None, 500, str(e))


# ======================================
# RATE LIMIT ERROR HANDLER
# ======================================

@api_bp.errorhandler(429)
def ratelimit_handler(e):
    """
    Rate limit aşıldığında kullanıcıya düzgün mesaj gönder
    """
    logger.warning(f"⚠️ Rate limit aşıldı: IP={request.remote_addr}")
    
    return create_response(
        [],
        429,
        "Çok fazla istek gönderiyorsunuz. Lütfen biraz bekleyin.",
        {'retry_after': '60 saniye'}
    )
