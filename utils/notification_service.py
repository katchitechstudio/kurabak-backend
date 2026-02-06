"""
Firebase Push Notification Service V5.2 🔥 - FIREBASE CHECK FIX
=====================================
✅ HTTP v1 API Migration (send_each yerine send_all kullanımı)
✅ Token Yönetimi (Kayıt/Silme)
✅ Bildirim Gönderme (Tekil/Toplu)
✅ 500 Token Batch Limiti (Firebase Compliant)
✅ Özel Bildirim Tipleri (Fiyat Alarmı, Günlük Özet, vb.)
✅ Hata Yönetimi ve Logging
✅ GÜNLÜK ÖZET: 14:00 otomatik gönderim (V5.0)
✅ 🔥 GENERATOR PATTERN: RAM dostu token okuma
✅ 🔥 V5.0: BAYRAM/HABER SİSTEMİ (event_manager entegrasyonu)
✅ 🔥 V5.1: FCM HTTP v1 API 404 HATASI ÇÖZÜLDÜ!
✅ 🔥 V5.2: FIREBASE CHECK FIX - Singleton pattern uyumlu

V5.2 Değişiklikler (CRITICAL FIX):
- firebase_admin._apps kontrolü kaldırıldı
- app.py'deki singleton pattern ile uyumlu
- Hata durumunda try-catch yakalıyor
"""
import logging
import json
from typing import List, Dict, Optional, Generator
from datetime import datetime
import firebase_admin
from firebase_admin import messaging
from config import Config
from utils.cache import get_cache, set_cache, get_redis_client

logger = logging.getLogger("KuraBak.Notification")

FCM_BATCH_SIZE = 500


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


def get_tokens_generator(batch_size: int = 500) -> Generator[List[str], None, None]:
    """
    🔥 Tokenları Redis'ten parça parça okuyan Generator
    
    SMEMBERS sorunu: 100,000 token'ı RAM'e yükler (200-300 MB) → OOM Kill
    SSCAN çözümü: Parça parça okur, RAM kullanımı sabit kalır
    
    Args:
        batch_size: Her batch'te kaç token (varsayılan 500)
        
    Yields:
        List[str]: Token batch'i
    """
    redis_client = get_redis_client()
    if not redis_client:
        return

    key = Config.CACHE_KEYS['fcm_tokens']
    cursor = 0
    batch = []

    try:
        while True:
            cursor, data = redis_client.sscan(key, cursor=cursor, count=batch_size)
            
            for token in data:
                if isinstance(token, bytes):
                    token = token.decode('utf-8')
                batch.append(token)

                if len(batch) >= batch_size:
                    yield batch
                    batch = []
            
            if cursor == 0:
                break
        
        if batch:
            yield batch
            
    except Exception as e:
        logger.error(f"❌ [FCM] Generator hatası: {e}")
        if batch:
            yield batch


def get_all_tokens() -> List[str]:
    """
    Tüm kayıtlı FCM tokenlarını getir (DEPRECATED - Geriye uyumluluk için)
    
    ⚠️ UYARI: Bu fonksiyon RAM dostu değildir!
    Yeni kod için get_tokens_generator() kullanın.
    
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


def send_notification(
    tokens: List[str],
    title: str,
    body: str,
    data: Optional[Dict] = None,
    priority: str = "high",
    sound: str = "default"
) -> Dict:
    """
    🔥 V5.2 FIX: FCM bildirimi gönder (Singleton pattern uyumlu)
    
    V5.1 → V5.2 Değişiklik:
    - firebase_admin._apps kontrolü KALDIRILDI
    - app.py'deki init_firebase() singleton pattern ile başlatıyor
    - Hata varsa try-catch yakalıyor
    
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
        # 🔥 V5.2 FIX: Firebase kontrolü kaldırıldı
        # app.py'de singleton pattern ile başlatılıyor
        # Hata varsa try-catch yakalayacak
        
        if not tokens:
            logger.warning("⚠️ [FCM] Token bulunamadı!")
            return {"success": False, "error": "No tokens"}
        
        total_success = 0
        total_failure = 0
        failed_tokens_all = []
        
        total_tokens = len(tokens)
        batch_count = (total_tokens + FCM_BATCH_SIZE - 1) // FCM_BATCH_SIZE
        
        logger.info(f"📦 [FCM] {total_tokens} token, {batch_count} batch'e bölünüyor...")
        
        for i in range(0, total_tokens, FCM_BATCH_SIZE):
            batch_tokens = tokens[i:i + FCM_BATCH_SIZE]
            batch_num = (i // FCM_BATCH_SIZE) + 1
            
            logger.info(f"📤 [FCM] Batch {batch_num}/{batch_count} gönderiliyor ({len(batch_tokens)} token)...")
            
            # 🔥 V5.1 FIX: send_each_for_multicast() kullan (HTTP v1 API uyumlu)
            try:
                response = messaging.send_each_for_multicast(
                    messaging.MulticastMessage(
                        notification=messaging.Notification(title=title, body=body),
                        tokens=batch_tokens,
                        data=data or {},
                        android=messaging.AndroidConfig(
                            priority=priority,
                            notification=messaging.AndroidNotification(
                                sound=sound,
                                channel_id='kurabak_default'
                            )
                        )
                    )
                )
                
                total_success += response.success_count
                total_failure += response.failure_count
                
                # Başarısız tokenları topla
                if response.failure_count > 0:
                    for idx, send_response in enumerate(response.responses):
                        if not send_response.success:
                            failed_tokens_all.append(batch_tokens[idx])
                            logger.debug(f"   ❌ Token {idx+1}: {send_response.exception}")
                
                logger.info(f"   ✅ Batch {batch_num}: {response.success_count} başarılı, {response.failure_count} başarısız")
                
            except Exception as batch_error:
                logger.error(f"❌ [FCM] Batch {batch_num} kritik hata: {batch_error}")
                total_failure += len(batch_tokens)
                failed_tokens_all.extend(batch_tokens)
        
        # Başarısız tokenları temizle
        if failed_tokens_all:
            logger.warning(f"🗑️ [FCM] {len(failed_tokens_all)} başarısız token temizleniyor...")
            for token in failed_tokens_all:
                unregister_fcm_token(token)
        
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
        
        set_cache(Config.CACHE_KEYS['fcm_last_notification'], str(datetime.now().timestamp()), ttl=86400)
        
        return result
        
    except Exception as e:
        logger.error(f"❌ [FCM] Bildirim gönderme hatası: {e}")
        import traceback
        logger.error(f"   Traceback: {traceback.format_exc()}")
        return {"success": False, "error": str(e)}


def send_to_all(title: str, body: str, data: Optional[Dict] = None) -> Dict:
    """
    TÜM kayıtlı cihazlara bildirim gönder (RAM dostu - Generator ile)
    
    🔥 V4.5: Generator pattern kullanır, RAM şişmesi olmaz
    🔥 V5.1: HTTP v1 API uyumlu send_notification() kullanır
    🔥 V5.2: Singleton pattern uyumlu
    
    Args:
        title: Bildirim başlığı
        body: Bildirim metni
        data: Ek veri
        
    Returns:
        Dict: Sonuç
    """
    try:
        logger.info("📢 [FCM] Toplu bildirim gönderiliyor (Generator modu)...")
        
        total_success = 0
        total_failure = 0
        total_tokens = 0
        
        token_generator = get_tokens_generator(batch_size=FCM_BATCH_SIZE)
        
        batch_num = 0
        for batch_tokens in token_generator:
            batch_num += 1
            
            if not batch_tokens:
                continue
            
            logger.info(f"📤 [FCM] Batch {batch_num} gönderiliyor ({len(batch_tokens)} token)...")
            
            # 🔥 V5.2: send_notification() singleton pattern uyumlu
            result = send_notification(
                tokens=batch_tokens,
                title=title,
                body=body,
                data=data
            )
            
            if result.get('success'):
                total_success += result.get('success_count', 0)
                total_failure += result.get('failure_count', 0)
                total_tokens += len(batch_tokens)
            else:
                logger.error(f"❌ [FCM] Batch {batch_num} tamamen başarısız!")
                total_failure += len(batch_tokens)
                total_tokens += len(batch_tokens)
        
        if total_tokens == 0:
            logger.warning("⚠️ [FCM] Hiç kayıtlı cihaz yok!")
            return {"success": False, "error": "No registered devices"}
        
        result = {
            "success": True,
            "total_sent": total_tokens,
            "success_count": total_success,
            "failure_count": total_failure,
            "batch_count": batch_num,
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"🏁 [FCM] Toplu gönderim tamamlandı!")
        logger.info(f"   📊 Toplam: {total_tokens} token")
        logger.info(f"   ✅ Başarılı: {total_success}")
        logger.info(f"   ❌ Başarısız: {total_failure}")
        
        set_cache(Config.CACHE_KEYS['fcm_last_notification'], str(datetime.now().timestamp()), ttl=86400)
        
        return result
        
    except Exception as e:
        logger.error(f"❌ [FCM] Toplu gönderim hatası: {e}")
        import traceback
        logger.error(f"   Traceback: {traceback.format_exc()}")
        return {"success": False, "error": str(e)}


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


def send_daily_summary() -> Dict:
    """
    🔔 GÜNLÜK BİLDİRİM (14:00)
    
    🔥 V5.0: Bayram/Haber sistemi ile entegre
    
    ÖNCELİK SIRASI:
    1. Bayram varsa → Bayram mesajı
    2. Bayram yoksa → Günün haberi
    3. İkisi de yoksa → Bildirim gönderilmez
    
    Returns:
        Dict: {
            'success': bool,
            'type': 'bayram' | 'news' | None,
            'recipient_count': int,
            'title': str,
            'body': str,
            'error': str (opsiyonel)
        }
    """
    try:
        logger.info("🔔 [DAILY SUMMARY] Günlük bildirim hazırlanıyor...")
        
        from utils.event_manager import get_daily_notification_content
        
        notification_content = get_daily_notification_content()
        
        if not notification_content:
            logger.warning("⚠️ [DAILY SUMMARY] Gönderilecek içerik yok (Ne bayram ne haber)")
            return {
                'success': False,
                'type': None,
                'recipient_count': 0,
                'error': 'Gönderilecek içerik yok'
            }
        
        data = {
            "type": "daily_summary",
            "content_type": notification_content['type'],
            "timestamp": str(datetime.now().timestamp())
        }
        
        result = send_to_all(
            title=notification_content['title'],
            body=notification_content['body'],
            data=data
        )
        
        if result.get('success'):
            recipient_count = result.get('success_count', 0)
            logger.info(
                f"✅ [DAILY SUMMARY] {notification_content['type'].upper()} bildirimi gönderildi "
                f"({recipient_count} kullanıcı)"
            )
            
            return {
                'success': True,
                'type': notification_content['type'],
                'recipient_count': recipient_count,
                'title': notification_content['title'],
                'body': notification_content['body']
            }
        else:
            logger.error(f"❌ [DAILY SUMMARY] Gönderim başarısız: {result.get('error')}")
            return {
                'success': False,
                'type': notification_content['type'],
                'recipient_count': 0,
                'error': result.get('error')
            }
        
    except Exception as e:
        logger.error(f"❌ [DAILY SUMMARY] Hata: {e}")
        import traceback
        logger.error(f"   Traceback: {traceback.format_exc()}")
        
        return {
            'success': False,
            'type': None,
            'recipient_count': 0,
            'error': str(e)
        }


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
