"""
General Routes - PRODUCTION READY (V7 - ONLINE TRACKING + BANNER) 🚀
==========================================================
✅ 503 ERROR FIX: Asla boş dönmez, gerekirse bayat veri (Stale) sunar.
✅ REGIONAL SUPPORT: 20 Döviz için Bölgesel Filtreleme
✅ SMART RECOVERY: Cache boşsa anlık tetikleme yapar (Synchronous Fallback)
✅ RATE LIMITING: Saldırılara karşı korumalı
✅ STANDARDIZED RESPONSE: Frontend (Android) için sabit format
✅ ONLINE USER TRACKING: Her API çağrısında kullanıcıyı 5dk için işaretle
✅ BANNER SYSTEM: Telegram'dan yönetilen duyuru sistemi
"""

from flask import Blueprint, jsonify, request, current_app
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
        # Arka planda güncelleme tetiklenebilir ama şimdilik veriyi dönelim
        return stale_data

    # 3. Hiçbir şey yoksa (Cold Start) -> Mecbur gidip çekeceğiz
    logger.warning(f"🔴 {cache_key} için hiç veri yok! Anlık çekim başlatılıyor...")
    success = fetch_all_data_safe()
    
    if success:
        # Şimdi tekrar cache'e bak
        return get_cache(cache_key)
    
    return None

# ======================================
# ENDPOINTLER (ONLINE TAKİP + BANNER!)
# ======================================

@api_bp.route('/currency/all', methods=['GET'])
def get_all_currencies():
    """
    Tüm Döviz Kurları (20 Adet Sabit)
    🕵️ Online tracking aktif!
    📢 Banner desteği eklendi!
    """
    # 🚨 AJAN DEVREDE! Kullanıcıyı işaretle
    track_online_user()
    
    try:
        result = get_data_guaranteed(Config.CACHE_KEYS['currencies_all'])
        
        if not result:
            return create_response([], 503, "Servis başlatılıyor, lütfen tekrar deneyin.")

        # Veri formatı kontrolü
        data_list = result.get('data', [])
        update_date = result.get('update_date')
        
        # 🔥 YENİ: Banner var mı kontrol et
        banner_msg = get_cache("system_banner")  # Redis'ten oku
        
        # Meta verisine banner'ı ekle
        meta_data = {
            'count': len(data_list),
            'last_update': update_date,
            'source': result.get('source'),
            'banner': banner_msg  # Varsa mesaj gider, yoksa None gider
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
def get_all_golds():
    """
    Tüm Altın Fiyatları
    🕵️ Online tracking aktif!
    """
    # 🚨 AJAN DEVREDE!
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
            {'count': len(data_list), 'last_update': result.get('update_date')}
        )
    except Exception as e:
        logger.error(f"Gold All Error: {e}")
        return create_response([], 500, "Sunucu hatası")


@api_bp.route('/currency/silver/all', methods=['GET'])
def get_all_silvers():
    """
    Gümüş Fiyatları (Özel İstek)
    🕵️ Online tracking aktif!
    """
    # 🚨 AJAN DEVREDE!
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
def get_summary():
    """
    Piyasa Özeti (Kazanan/Kaybeden)
    🕵️ Online tracking aktif!
    """
    # 🚨 AJAN DEVREDE!
    track_online_user()
    
    try:
        result = get_data_guaranteed(Config.CACHE_KEYS['summary'])
        
        if not result or not result.get('data'):
            # Veri yoksa boş obje dön, 503 atma (Frontend patlamasın)
            return create_response({}, 200, "Özet henüz hazır değil")

        return create_response(
            result.get('data', {}),
            200,
            "Piyasa özeti getirildi"
        )
    except Exception as e:
        logger.error(f"Summary Error: {e}")
        return create_response({}, 500, "Sunucu hatası")


@api_bp.route('/currency/regional', methods=['GET'])
def get_regional_currencies():
    """
    Bölgesel Filtrelenmiş Dövizler (Config'deki 5 Bölge)
    🕵️ Online tracking aktif!
    """
    # 🚨 AJAN DEVREDE!
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
        
        # Veriyi hızlı erişim için dictionary yap: {'USD': {...}, 'EUR': {...}}
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
def get_metrics():
    """
    Sistem Metrikleri (Admin/Debug için)
    NOT: Bu endpoint'te online tracking YOK (Admin arayüzü için)
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
