"""
Firebase Push Notification Service V5.7 🔥 - TOKEN CHECK
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
✅ 🔥 V5.3: ALARM BİLDİRİMİ YENİDEN TASARLANDI
✅ 🔥 V5.4: PERCENT ALARM DESTEĞİ EKLENDİ
✅ 🔥 V5.5: BATCH RATE LIMIT EKLENDİ (Firebase spam koruması)
✅ 🔥 V5.6: FIREBASE INIT GUARD - Firebase başlatılmamışsa token SİLİNMEZ
✅ 🔥 V5.7: TOKEN CHECK - is_token_registered() eklendi
"""
import logging
import time
import json
from typing import List, Dict, Optional, Generator
from datetime import datetime
import firebase_admin
from firebase_admin import messaging
from config import Config
from utils.cache import get_cache, set_cache, get_redis_client

logger = logging.getLogger("KuraBak.Notification")

FCM_BATCH_SIZE = 500

# Firebase başlatılmamış hatası için kontrol stringi
_FIREBASE_NOT_INIT_ERRORS = [
    "the default firebase app does not exist",
    "initialize_app",
    "firebase app",
]

def _is_firebase_init_error(error: Exception) -> bool:
    """Firebase başlatılmamış hatası mı kontrol et"""
    error_str = str(error).lower()
    return any(msg in error_str for msg in _FIREBASE_NOT_INIT_ERRORS)

def _is_invalid_token_error(error: Exception) -> bool:
    """Geçersiz/süresi dolmuş token hatası mı kontrol et"""
    error_str = str(error).lower()
    invalid_indicators = [
        "registration-token-not-registered",
        "invalid-registration-token", 
        "invalid argument",
        "not registered",
    ]
    return any(msg in error_str for msg in invalid_indicators)


def register_fcm_token(token: str) -> bool:
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


def is_token_registered(token: str) -> bool:
    """
    🔥 V5.7: Token sunucuda kayıtlı mı kontrol et.
    Android açılışta bunu sorgular, kayıtlı değilse yeniden register eder.
    """
    try:
        redis_client = get_redis_client()
        if not redis_client:
            logger.error("❌ [FCM] Token kontrol hatası: Redis bağlantısı yok")
            return False
        
        result = redis_client.sismember(Config.CACHE_KEYS['fcm_tokens'], token)
        logger.info(f"🔍 [FCM] Token kontrol: {token[:20]}... → {'Kayıtlı ✅' if result else 'Kayıtlı değil ❌'}")
        return bool(result)
        
    except Exception as e:
        logger.error(f"❌ [FCM] Token kontrol hatası: {e}")
        return False


def get_tokens_generator(batch_size: int = 500) -> Generator[List[str], None, None]:
    """
    🔥 Tokenları Redis'ten parça parça okuyan Generator

    SMEMBERS sorunu: 100,000 token'ı RAM'e yükler (200-300 MB) → OOM Kill
    SSCAN çözümü: Parça parça okur, RAM kullanımı sabit kalır
    """
    redis_client = get_redis_client()
    if not redis_client:
        return

    key    = Config.CACHE_KEYS['fcm_tokens']
    cursor = 0
    batch  = []

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
    🔥 V5.6 FIX: Firebase başlatılmamışsa token SİLİNMEZ
    Sadece Firebase'den "invalid token" yanıtı gelince token silinir.
    """
    try:
        if not tokens:
            logger.warning("⚠️ [FCM] Token bulunamadı!")
            return {"success": False, "error": "No tokens"}

        # 🔥 V5.6: Firebase başlatılmış mı kontrol et
        if not firebase_admin._apps:
            logger.error("❌ [FCM] Firebase başlatılmamış! Token gönderimi atlanıyor, tokenlar KORUNUYOR.")
            return {"success": False, "error": "Firebase not initialized", "tokens_preserved": True}
        
        total_success      = 0
        total_failure      = 0
        failed_tokens_all  = []
        
        total_tokens = len(tokens)
        batch_count  = (total_tokens + FCM_BATCH_SIZE - 1) // FCM_BATCH_SIZE
        
        logger.info(f"📦 [FCM] {total_tokens} token, {batch_count} batch'e bölünüyor...")
        
        for i in range(0, total_tokens, FCM_BATCH_SIZE):
            batch_tokens = tokens[i:i + FCM_BATCH_SIZE]
            batch_num    = (i // FCM_BATCH_SIZE) + 1
            
            logger.info(f"📤 [FCM] Batch {batch_num}/{batch_count} gönderiliyor ({len(batch_tokens)} token)...")
            
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
                
                # Sadece gerçekten geçersiz tokenları işaretle
                if response.failure_count > 0:
                    for idx, send_response in enumerate(response.responses):
                        if not send_response.success:
                            err = send_response.exception
                            if err and _is_invalid_token_error(err):
                                # Gerçekten geçersiz token → sil
                                failed_tokens_all.append(batch_tokens[idx])
                                logger.debug(f"   ❌ Geçersiz token {idx+1}: {err}")
                            else:
                                # Geçici hata (network, quota vb.) → SILME
                                logger.debug(f"   ⚠️ Geçici hata token {idx+1}: {err} (token korunuyor)")
                
                logger.info(f"   ✅ Batch {batch_num}: {response.success_count} başarılı, {response.failure_count} başarısız")
                
            except Exception as batch_error:
                # 🔥 V5.6 KRİTİK FIX: Firebase init hatası → tokenları SILME
                if _is_firebase_init_error(batch_error):
                    logger.error(f"❌ [FCM] Batch {batch_num} Firebase init hatası: {batch_error}")
                    logger.error("   ⚠️ Tokenlar KORUNUYOR — Firebase yeniden başlatılana kadar bekleniyor")
                    total_failure += len(batch_tokens)
                    # failed_tokens_all'a EKLEME — silme
                else:
                    logger.error(f"❌ [FCM] Batch {batch_num} kritik hata: {batch_error}")
                    total_failure += len(batch_tokens)
                    # Bilinmeyen hata → tokenları da silme, güvenli taraf
                    logger.warning(f"   ⚠️ Bilinmeyen hata, tokenlar KORUNUYOR: {batch_error}")
        
        if failed_tokens_all:
            logger.warning(f"🗑️ [FCM] {len(failed_tokens_all)} geçersiz token temizleniyor...")
            for token in failed_tokens_all:
                unregister_fcm_token(token)
        
        result = {
            "success":       True,
            "success_count": total_success,
            "failure_count": total_failure,
            "total_tokens":  total_tokens,
            "batch_count":   batch_count,
            "timestamp":     datetime.now().isoformat()
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
    🔥 V5.5: Batch arası rate limit eklendi
    🔥 V5.6: Firebase init hatası → tokenlar korunur
    """
    try:
        # 🔥 V5.6: Firebase başlatılmış mı erken kontrol
        if not firebase_admin._apps:
            logger.error("❌ [FCM] Firebase başlatılmamış! send_to_all atlanıyor, tokenlar KORUNUYOR.")
            return {"success": False, "error": "Firebase not initialized", "tokens_preserved": True}

        logger.info("📢 [FCM] Toplu bildirim gönderiliyor (Generator modu)...")
        
        total_success = 0
        total_failure = 0
        total_tokens  = 0
        
        token_generator = get_tokens_generator(batch_size=FCM_BATCH_SIZE)
        
        batch_num = 0
        for batch_tokens in token_generator:
            batch_num += 1
            
            if not batch_tokens:
                continue
            
            logger.info(f"📤 [FCM] Batch {batch_num} gönderiliyor ({len(batch_tokens)} token)...")
            
            result = send_notification(
                tokens=batch_tokens,
                title=title,
                body=body,
                data=data
            )
            
            if result.get('success'):
                total_success += result.get('success_count', 0)
                total_failure += result.get('failure_count', 0)
                total_tokens  += len(batch_tokens)
            else:
                logger.error(f"❌ [FCM] Batch {batch_num} tamamen başarısız!")
                total_failure += len(batch_tokens)
                total_tokens  += len(batch_tokens)
            
            if batch_num > 1:
                time.sleep(0.1)
        
        if total_tokens == 0:
            logger.warning("⚠️ [FCM] Hiç kayıtlı cihaz yok!")
            return {"success": False, "error": "No registered devices"}
        
        result = {
            "success":       True,
            "total_sent":    total_tokens,
            "success_count": total_success,
            "failure_count": total_failure,
            "batch_count":   batch_num,
            "timestamp":     datetime.now().isoformat()
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


def send_alarm_notification(
    fcm_token: str,
    currency_code: str,
    currency_name: str,
    current_price: float,
    alarm_mode: str = "PRICE",
    target_price: Optional[float] = None,
    start_price: Optional[float] = None,
    alarm_type: Optional[str] = None,
    percent_value: Optional[float] = None,
    percent_direction: Optional[str] = None
) -> bool:
    """
    🔥 V5.4: Fiyat alarmı bildirimi gönder (PERCENT DESTEĞI EKLENDİ!)
    """
    try:
        alarm_mode = alarm_mode.upper()
        
        if alarm_mode == "PRICE":
            if not target_price or not alarm_type:
                logger.error("❌ [ALARM] PRICE modunda target_price ve alarm_type gerekli!")
                return False
            
            if not start_price:
                start_price = current_price
            
            price_diff        = current_price - target_price
            change_from_start = current_price - start_price
            change_percent    = (change_from_start / start_price) * 100 if start_price > 0 else 0
            
            emoji        = "📈" if alarm_type == "HIGH" else "📉"
            alarm_status = "Hedef ÜZERİNE çıktı" if alarm_type == "HIGH" else "Hedef ALTINA düştü"
            change_symbol = "+" if change_from_start >= 0 else ""
            
            title = f"{emoji} Fiyat Alarmı!"
            body  = (
                f"{currency_name} / {currency_code}\n\n"
                f"Hedef: ₺{target_price:,.2f}\n"
                f"Anlık: ₺{current_price:,.2f}\n\n"
                f"{alarm_status}\n\n"
                f"{change_symbol}{change_from_start:,.2f} TL ({change_symbol}{change_percent:.2f}%)"
            )
            
            data = {
                "type":              "alarm_triggered",
                "alarm_mode":        "PRICE",
                "currency_code":     currency_code,
                "currency_name":     currency_name,
                "target_price":      f"{target_price:.2f}",
                "current_price":     f"{current_price:.2f}",
                "start_price":       f"{start_price:.2f}",
                "alarm_type":        alarm_type,
                "alarm_status":      alarm_status,
                "price_diff":        f"{price_diff:.2f}",
                "change_from_start": f"{change_from_start:.2f}",
                "change_percent":    f"{change_percent:.2f}"
            }
            
        elif alarm_mode == "PERCENT":
            if not start_price or not percent_value or not percent_direction:
                logger.error("❌ [ALARM] PERCENT modunda start_price, percent_value, percent_direction gerekli!")
                return False
            
            change_from_start = current_price - start_price
            actual_percent    = (change_from_start / start_price) * 100 if start_price > 0 else 0
            
            emoji        = "📈" if percent_direction == "UP" else "📉"
            alarm_status = f"%{percent_value:.1f} YÜKSELDİ" if percent_direction == "UP" else f"%{percent_value:.1f} DÜŞTÜ"
            change_symbol = "+" if change_from_start >= 0 else ""
            
            title = f"{emoji} Fiyat Alarmı!"
            body  = (
                f"{currency_name} / {currency_code}\n\n"
                f"Başlangıç: ₺{start_price:,.2f}\n"
                f"Anlık: ₺{current_price:,.2f}\n\n"
                f"{alarm_status}\n\n"
                f"{change_symbol}{change_from_start:,.2f} TL ({change_symbol}{actual_percent:.2f}%)"
            )
            
            data = {
                "type":              "alarm_triggered",
                "alarm_mode":        "PERCENT",
                "currency_code":     currency_code,
                "currency_name":     currency_name,
                "start_price":       f"{start_price:.2f}",
                "current_price":     f"{current_price:.2f}",
                "percent_value":     f"{percent_value:.1f}",
                "percent_direction": percent_direction,
                "alarm_status":      alarm_status,
                "change_from_start": f"{change_from_start:.2f}",
                "actual_percent":    f"{actual_percent:.2f}"
            }
        
        else:
            logger.error(f"❌ [ALARM] Geçersiz alarm_mode: {alarm_mode}")
            return False
        
        messaging.send(
            messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data=data,
                token=fcm_token,
                android=messaging.AndroidConfig(
                    priority='high',
                    notification=messaging.AndroidNotification(
                        sound='default',
                        channel_id='kurabak_alarm',
                        color='#10B981'
                    )
                )
            )
        )
        
        logger.info(f"✅ [ALARM] Bildirim gönderildi: {currency_name} ({currency_code}) - {alarm_status}")
        
        if alarm_mode == "PRICE":
            logger.info(f"   📊 Hedef: ₺{target_price:.2f} | Anlık: ₺{current_price:.2f} | Değişim: {change_symbol}{change_from_start:.2f} TL ({change_symbol}{change_percent:.2f}%)")
        else:
            logger.info(f"   📊 Başlangıç: ₺{start_price:.2f} | Anlık: ₺{current_price:.2f} | Değişim: {change_symbol}{change_from_start:.2f} TL ({change_symbol}{actual_percent:.2f}%)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ [ALARM] Bildirim gönderme hatası: {e}")
        import traceback
        logger.error(f"   Traceback: {traceback.format_exc()}")
        return False


def send_price_alert(currency_code: str, price: float, change_percent: float) -> Dict:
    emoji     = "🔥" if abs(change_percent) >= 2.0 else "📊"
    direction = "📈" if change_percent > 0 else "📉"
    
    title = f"{emoji} {currency_code} Fiyat Uyarısı!"
    body  = f"{direction} {price:.4f} TL ({change_percent:+.2f}%)"
    
    data = {
        "type":     "price_alert",
        "currency": currency_code,
        "price":    str(price),
        "change":   str(change_percent)
    }
    
    return send_to_all(title, body, data)


def send_daily_summary() -> Dict:
    """
    🔔 GÜNLÜK BİLDİRİM (14:00)

    ÖNCELİK SIRASI:
    1. Bayram varsa → Bayram mesajı
    2. Bayram yoksa → Günün haberi
    3. İkisi de yoksa → Bildirim gönderilmez
    """
    try:
        logger.info("🔔 [DAILY SUMMARY] Günlük bildirim hazırlanıyor...")
        
        from utils.event_manager import get_daily_notification_content
        
        notification_content = get_daily_notification_content()
        
        if not notification_content:
            logger.warning("⚠️ [DAILY SUMMARY] Gönderilecek içerik yok (Ne bayram ne haber)")
            return {
                'success':         False,
                'type':            None,
                'recipient_count': 0,
                'error':           'Gönderilecek içerik yok'
            }
        
        data = {
            "type":         "daily_summary",
            "content_type": notification_content['type'],
            "timestamp":    str(datetime.now().timestamp())
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
                'success':         True,
                'type':            notification_content['type'],
                'recipient_count': recipient_count,
                'title':           notification_content['title'],
                'body':            notification_content['body']
            }
        else:
            logger.error(f"❌ [DAILY SUMMARY] Gönderim başarısız: {result.get('error')}")
            return {
                'success':         False,
                'type':            notification_content['type'],
                'recipient_count': 0,
                'error':           result.get('error')
            }
        
    except Exception as e:
        logger.error(f"❌ [DAILY SUMMARY] Hata: {e}")
        import traceback
        logger.error(f"   Traceback: {traceback.format_exc()}")
        return {
            'success':         False,
            'type':            None,
            'recipient_count': 0,
            'error':           str(e)
        }


def send_test_notification() -> Dict:
    title = "🔔 KuraBak Test Bildirimi"
    body  = f"Bildirim sistemi çalışıyor! {datetime.now().strftime('%H:%M:%S')}"
    
    data = {
        "type":      "test",
        "timestamp": str(datetime.now().timestamp())
    }
    
    return send_to_all(title, body, data)
