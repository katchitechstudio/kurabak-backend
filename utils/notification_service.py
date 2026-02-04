"""
Notification Service - Firebase Cloud Messaging V3.0
====================================================
✅ FCM Token Management
✅ Push Notifications
✅ Daily Summary (V3.0: Bayram/Haber sistemi)
✅ Batch Sending
✅ Error Handling

V3.0 Değişiklikler:
- send_daily_summary() tamamen yenilendi
- Artık 23 döviz özeti YOK
- event_manager.get_daily_notification_content() kullanılıyor
- Bayram varsa bayram, yoksa haber gönderiliyor
"""

import logging
import firebase_admin
from firebase_admin import credentials, messaging
from typing import List, Dict, Optional
import os

from utils.cache import get_cache, set_cache
from config import Config

logger = logging.getLogger(__name__)

FIREBASE_INITIALIZED = False


def initialize_firebase():
    """
    Firebase Admin SDK'yi başlatır.
    """
    global FIREBASE_INITIALIZED
    
    if FIREBASE_INITIALIZED:
        return True
    
    try:
        cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH', 'firebase-credentials.json')
        
        if not os.path.exists(cred_path):
            logger.error(f"❌ Firebase credentials dosyası bulunamadı: {cred_path}")
            return False
        
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        
        FIREBASE_INITIALIZED = True
        logger.info("✅ Firebase Admin SDK başlatıldı")
        return True
        
    except Exception as e:
        logger.error(f"❌ Firebase başlatma hatası: {e}")
        return False


def get_all_fcm_tokens() -> List[str]:
    """
    Redis'teki tüm FCM token'ları getirir.
    
    Returns:
        List[str]: Token listesi
    """
    try:
        tokens_data = get_cache(Config.CACHE_KEYS['fcm_tokens'])
        
        if not tokens_data:
            logger.warning("⚠️ FCM token bulunamadı")
            return []
        
        tokens = list(tokens_data.keys())
        logger.info(f"📱 {len(tokens)} FCM token bulundu")
        return tokens
        
    except Exception as e:
        logger.error(f"❌ FCM token getirme hatası: {e}")
        return []


def send_notification(
    tokens: List[str],
    title: str,
    body: str,
    data: Optional[Dict[str, str]] = None
) -> Dict[str, int]:
    """
    Birden fazla cihaza push notification gönderir.
    
    Args:
        tokens: FCM token listesi
        title: Bildirim başlığı
        body: Bildirim içeriği
        data: Ek veri (opsiyonel)
    
    Returns:
        Dict: {"success": int, "failed": int}
    """
    if not initialize_firebase():
        return {"success": 0, "failed": len(tokens)}
    
    if not tokens:
        logger.warning("⚠️ Gönderilecek token yok")
        return {"success": 0, "failed": 0}
    
    success_count = 0
    failed_count = 0
    
    message = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=title,
            body=body
        ),
        data=data or {},
        tokens=tokens
    )
    
    try:
        response = messaging.send_multicast(message)
        success_count = response.success_count
        failed_count = response.failure_count
        
        logger.info(
            f"📤 Push gönderildi: "
            f"✅ {success_count} başarılı, "
            f"❌ {failed_count} başarısız"
        )
        
        if response.failure_count > 0:
            for idx, resp in enumerate(response.responses):
                if not resp.success:
                    logger.warning(f"   Token {idx}: {resp.exception}")
        
        return {"success": success_count, "failed": failed_count}
        
    except Exception as e:
        logger.error(f"❌ Push gönderme hatası: {e}")
        return {"success": 0, "failed": len(tokens)}


def send_daily_summary() -> Dict[str, any]:
    """
    14:00'da çalışır. Bayram/Haber bildirimi gönderir.
    
    ÖNCELİK SIRASI:
    1. Bayram varsa → Bayram mesajı
    2. Bayram yoksa → Günün haberi
    3. İkisi de yoksa → Bildirim gönderilmez
    
    Returns:
        Dict: {
            "sent": bool,
            "type": "bayram" | "news" | None,
            "success": int,
            "failed": int,
            "message": str
        }
    """
    try:
        logger.info("🔔 [DAILY SUMMARY] Günlük bildirim hazırlanıyor...")
        
        from utils.event_manager import get_daily_notification_content
        
        notification_content = get_daily_notification_content()
        
        if not notification_content:
            logger.warning("⚠️ [DAILY SUMMARY] Gönderilecek içerik yok (Ne bayram ne haber)")
            return {
                "sent": False,
                "type": None,
                "success": 0,
                "failed": 0,
                "message": "Gönderilecek içerik yok"
            }
        
        tokens = get_all_fcm_tokens()
        
        if not tokens:
            logger.warning("⚠️ [DAILY SUMMARY] FCM token bulunamadı")
            return {
                "sent": False,
                "type": notification_content['type'],
                "success": 0,
                "failed": 0,
                "message": "FCM token yok"
            }
        
        result = send_notification(
            tokens=tokens,
            title=notification_content['title'],
            body=notification_content['body'],
            data={
                "type": "daily_summary",
                "content_type": notification_content['type']
            }
        )
        
        logger.info(
            f"✅ [DAILY SUMMARY] {notification_content['type'].upper()} bildirimi gönderildi: "
            f"{result['success']} başarılı, {result['failed']} başarısız"
        )
        
        return {
            "sent": True,
            "type": notification_content['type'],
            "success": result['success'],
            "failed": result['failed'],
            "message": f"{notification_content['type']} bildirimi gönderildi"
        }
        
    except Exception as e:
        logger.error(f"❌ [DAILY SUMMARY] Hata: {e}")
        import traceback
        logger.error(f"   Traceback: {traceback.format_exc()}")
        
        return {
            "sent": False,
            "type": None,
            "success": 0,
            "failed": 0,
            "message": f"Hata: {str(e)}"
        }


def save_fcm_token(user_id: str, token: str) -> bool:
    """
    Kullanıcının FCM token'ını kaydeder.
    
    Args:
        user_id: Kullanıcı ID
        token: FCM token
    
    Returns:
        bool: Başarılı mı?
    """
    try:
        tokens_data = get_cache(Config.CACHE_KEYS['fcm_tokens']) or {}
        tokens_data[token] = {
            "user_id": user_id,
            "registered_at": str(datetime.now())
        }
        set_cache(Config.CACHE_KEYS['fcm_tokens'], tokens_data)
        logger.info(f"✅ FCM token kaydedildi: {user_id}")
        return True
    except Exception as e:
        logger.error(f"❌ FCM token kaydetme hatası: {e}")
        return False


def remove_fcm_token(token: str) -> bool:
    """
    FCM token'ı siler.
    
    Args:
        token: FCM token
    
    Returns:
        bool: Başarılı mı?
    """
    try:
        tokens_data = get_cache(Config.CACHE_KEYS['fcm_tokens']) or {}
        if token in tokens_data:
            del tokens_data[token]
            set_cache(Config.CACHE_KEYS['fcm_tokens'], tokens_data)
            logger.info(f"✅ FCM token silindi: {token[:20]}...")
            return True
        return False
    except Exception as e:
        logger.error(f"❌ FCM token silme hatası: {e}")
        return False
