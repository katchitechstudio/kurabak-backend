"""
Firebase Push Notification Service 🔥
=====================================
✅ Token Yönetimi (Kayıt/Silme)
✅ Bildirim Gönderme (Tekil/Toplu)
✅ 500 Token Batch Limiti (Firebase Compliant)
✅ Özel Bildirim Tipleri (Fiyat Alarmı, Günlük Özet, vb.)
✅ Hata Yönetimi ve Logging
"""
import logging
import json
from typing import List, Dict, Optional
from datetime import datetime
import firebase_admin
from firebase_admin import messaging
from config import Config
from utils.cache import get_cache, set_cache, get_redis_client

logger = logging.getLogger("KuraBak.Notification")

# Firebase limit: send_multicast() maksimum 500 token kabul eder
FCM_BATCH_SIZE = 500

# ======================================
# TOKEN YÖNETİMİ
# ======================================

def register_fcm_token(token: str) -> bool:
    """
    Yeni bir FCM token'ı kaydet
    
    Args:
        token: Firebase Cloud Messaging token
        
    Returns:
        bool: Başarılı ise True
    """
    try:
        redis_client = get_redis_client()
        if not redis_client:
            logger.error("Redis bağlantısı yok!")
            return False
        
        # Token'ı Redis Set'ine ekle (otomatik tekil tutar)
        redis_client.sadd(Config.CACHE_KEYS['fcm_tokens'], token)
        
        logger.info(f"✅ [FCM] Token kaydedildi: {token[:20]}...")
        return True
        
    except Exception as e:
        logger.error(f"❌ [FCM] Token kayıt hatası: {e}")
        return False

def unregister_fcm_token(token: str) -> bool:
    """
    FCM token'ı sil
    
    Args:
        token: Silinecek token
        
    Returns:
        bool: Başarılı ise True
    """
    try:
        redis_client = get_redis_client()
        if not redis_client:
            return False
        
        redis_client.srem(Config.CACHE_KEYS['fcm_tokens'], token)
        logger.info(f"🗑️ [FCM] Token silindi: {token[:20]}...")
        return True
        
    except Exception as e:
        logger.error(f"❌ [FCM] Token silme hatası: {e}")
        return False

def get_all_tokens() -> List[str]:
    """
    Tüm kayıtlı FCM tokenlarını getir
    
    Returns:
        List[str]: Token listesi
    """
    try:
        redis_client = get_redis_client()
        if not redis_client:
            return []
        
        tokens = redis_client.smembers(Config.CACHE_KEYS['fcm_tokens'])
        return [token.decode('utf-8') if isinstance(token, bytes) else token for token in tokens]
        
    except Exception as e:
        logger.error(f"❌ [FCM] Token listesi hatası: {e}")
        return []

def get_token_count() -> int:
    """
    Kayıtlı token sayısını getir
    
    Returns:
        int: Token sayısı
    """
    try:
        redis_client = get_redis_client()
        if not redis_client:
            return 0
        
        return redis_client.scard(Config.CACHE_KEYS['fcm_tokens'])
        
    except Exception as e:
        logger.error(f"❌ [FCM] Token sayısı hatası: {e}")
        return 0

# ======================================
# BİLDİRİM GÖNDERME (BATCH SUPPORT)
# ======================================

def send_notification(
    tokens: List[str],
    title: str,
    body: str,
    data: Optional[Dict] = None,
    priority: str = "high",
    sound: str = "default"
) -> Dict:
    """
    FCM bildirimi gönder (500'lük batch'lere otomatik böler)
    
    Args:
        tokens: Hedef cihaz tokenları
        title: Bildirim başlığı
        body: Bildirim metni
        data: Ek veri (dict)
        priority: Öncelik (high/normal)
        sound: Ses (default/silent)
        
    Returns:
        Dict: Sonuç bilgisi
    """
    try:
        # Firebase başlatılmış mı kontrol et
        if not firebase_admin._apps:
            logger.warning("⚠️ [FCM] Firebase başlatılmamış, bildirim gönderilemedi!")
            return {"success": False, "error": "Firebase not initialized"}
        
        if not tokens:
            logger.warning("⚠️ [FCM] Token bulunamadı!")
            return {"success": False, "error": "No tokens"}
        
        # Toplam sonuç için sayaçlar
        total_success = 0
        total_failure = 0
        failed_tokens_all = []
        
        # 🔥 BATCH İŞLEMİ: 500'lük parçalara böl
        total_tokens = len(tokens)
        batch_count = (total_tokens + FCM_BATCH_SIZE - 1) // FCM_BATCH_SIZE  # Yukarı yuvarlama
        
        logger.info(f"📦 [FCM] {total_tokens} token, {batch_count} batch'e bölünüyor...")
        
        for i in range(0, total_tokens, FCM_BATCH_SIZE):
            batch_tokens = tokens[i:i + FCM_BATCH_SIZE]
            batch_num = (i // FCM_BATCH_SIZE) + 1
            
            logger.info(f"📤 [FCM] Batch {batch_num}/{batch_count} gönderiliyor ({len(batch_tokens)} token)...")
            
            # Bildirim mesajını hazırla
            notification = messaging.Notification(
                title=title,
                body=body
            )
            
            # Android ayarları
            android_config = messaging.AndroidConfig(
                priority=priority,
                notification=messaging.AndroidNotification(
                    sound=sound,
                    channel_id='kurabak_default'
                )
            )
            
            # MulticastMessage oluştur
            message = messaging.MulticastMessage(
                notification=notification,
                tokens=batch_tokens,
                data=data or {},
                android=android_config
            )
            
            # Gönder
            response = messaging.send_multicast(message)
            
            # Sayaçları güncelle
            total_success += response.success_count
            total_failure += response.failure_count
            
            # Başarısız tokenları topla
            if response.failure_count > 0:
                failed_tokens = [batch_tokens[idx] for idx, resp in enumerate(response.responses) if not resp.success]
                failed_tokens_all.extend(failed_tokens)
            
            logger.info(f"   ✅ Batch {batch_num}: {response.success_count} başarılı, {response.failure_count} başarısız")
        
        # Tüm başarısız tokenları temizle
        if failed_tokens_all:
            logger.warning(f"🗑️ [FCM] {len(failed_tokens_all)} başarısız token temizleniyor...")
            for token in failed_tokens_all:
                unregister_fcm_token(token)
        
        # Sonuç
        result = {
            "success": True,
            "success_count": total_success,
            "failure_count": total_failure,
            "total_tokens": total_tokens,
            "batch_count": batch_count,
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"🎉 [FCM] Gönderim tamamlandı!")
        logger.info(f"   📊 Toplam: {total_tokens} token")
        logger.info(f"   ✅ Başarılı: {total_success}")
        logger.info(f"   ❌ Başarısız: {total_failure}")
        logger.info(f"   📝 Başlık: {title}")
        logger.info(f"   📄 Mesaj: {body[:50]}...")
        
        # Son bildirim zamanını kaydet
        set_cache(Config.CACHE_KEYS['fcm_last_notification'], str(datetime.now().timestamp()), ttl=86400)
        
        return result
        
    except Exception as e:
        logger.error(f"❌ [FCM] Bildirim gönderme hatası: {e}")
        return {"success": False, "error": str(e)}

def send_to_all(title: str, body: str, data: Optional[Dict] = None) -> Dict:
    """
    TÜM kayıtlı cihazlara bildirim gönder
    
    Args:
        title: Bildirim başlığı
        body: Bildirim metni
        data: Ek veri
        
    Returns:
        Dict: Sonuç
    """
    tokens = get_all_tokens()
    
    if not tokens:
        logger.warning("⚠️ [FCM] Hiç kayıtlı cihaz yok!")
        return {"success": False, "error": "No registered devices"}
    
    logger.info(f"📢 [FCM] Toplu bildirim gönderiliyor ({len(tokens)} cihaz)")
    
    return send_notification(tokens, title, body, data)

# ======================================
# ÖZEL BİLDİRİM TİPLERİ
# ======================================

def send_price_alert(currency_code: str, price: float, change_percent: float) -> Dict:
    """
    Fiyat alarm bildirimi
    
    Args:
        currency_code: Döviz kodu (USD, EUR, vb.)
        price: Güncel fiyat
        change_percent: Değişim yüzdesi
        
    Returns:
        Dict: Sonuç
    """
    # Emoji seç
    emoji = "🔥" if abs(change_percent) >= 2.0 else "📊"
    direction = "📈" if change_percent > 0 else "📉"
    
    title = f"{emoji} {currency_code} Fiyat Uyarısı!"
    body = f"{direction} {price:.4f} TL ({change_percent:+.2f}%)"
    
    data = {
        "type": "price_alert",
        "currency": currency_code,
        "price": str(price),
        "change": str(change_percent)
    }
    
    return send_to_all(title, body, data)

def send_daily_summary(summary_data: Dict) -> Dict:
    """
    Günlük özet bildirimi
    
    Args:
        summary_data: Özet veriler
        
    Returns:
        Dict: Sonuç
    """
    try:
        # En çok yükselen
        top_gainer = summary_data.get('top_gainer', {})
        top_gainer_name = top_gainer.get('name', 'N/A')
        top_gainer_change = top_gainer.get('change_percent', 0)
        
        # En çok düşen
        top_loser = summary_data.get('top_loser', {})
        top_loser_name = top_loser.get('name', 'N/A')
        top_loser_change = top_loser.get('change_percent', 0)
        
        title = "📊 Günlük Piyasa Özeti"
        body = f"📈 En yükselen: {top_gainer_name} ({top_gainer_change:+.2f}%)\n📉 En düşen: {top_loser_name} ({top_loser_change:+.2f}%)"
        
        data = {
            "type": "daily_summary",
            "data": json.dumps(summary_data)
        }
        
        return send_to_all(title, body, data)
        
    except Exception as e:
        logger.error(f"❌ [FCM] Günlük özet hatası: {e}")
        return {"success": False, "error": str(e)}

def send_market_alert(event_title: str, event_description: str) -> Dict:
    """
    Piyasa/Takvim etkinliği bildirimi
    
    Args:
        event_title: Etkinlik başlığı
        event_description: Açıklama
        
    Returns:
        Dict: Sonuç
    """
    title = f"🗓️ {event_title}"
    body = event_description
    
    data = {
        "type": "market_event",
        "title": event_title,
        "description": event_description
    }
    
    return send_to_all(title, body, data)

def send_system_notification(message: str, is_critical: bool = False) -> Dict:
    """
    Sistem bildirimi (bakım, güncelleme, vb.)
    
    Args:
        message: Bildirim mesajı
        is_critical: Kritik bildirim mi?
        
    Returns:
        Dict: Sonuç
    """
    emoji = "🚨" if is_critical else "ℹ️"
    title = f"{emoji} Sistem Bildirimi"
    body = message
    
    data = {
        "type": "system_notification",
        "is_critical": str(is_critical)
    }
    
    return send_to_all(title, body, data)

# ======================================
# TEST FONKSİYONU
# ======================================

def send_test_notification() -> Dict:
    """
    Test bildirimi gönder
    
    Returns:
        Dict: Sonuç
    """
    title = "🔔 KuraBak Test Bildirimi"
    body = f"Bildirim sistemi çalışıyor! {datetime.now().strftime('%H:%M:%S')}"
    
    data = {
        "type": "test",
        "timestamp": str(datetime.now().timestamp())
    }
    
    return send_to_all(title, body, data)
