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

FCM_BATCH_SIZE = 25

_FIREBASE_NOT_INIT_ERRORS = [
    "the default firebase app does not exist",
    "initialize_app",
    "firebase app",
]

def _is_firebase_init_error(error: Exception) -> bool:
    error_str = str(error).lower()
    return any(msg in error_str for msg in _FIREBASE_NOT_INIT_ERRORS)

def _is_invalid_token_error(error: Exception) -> bool:
    error_str = str(error).lower()
    invalid_indicators = [
        "registration-token-not-registered",
        "invalid-registration-token",
        "invalid argument",
        "not registered",
        "requested entity was not found",
        "unregistered",
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

        cursor = 0
        device_hash = None
        while True:
            cursor, keys = redis_client.scan(cursor, match="fcm_token_map:*", count=100)
            for key in keys:
                val = redis_client.get(key)
                if val:
                    val_str = val.decode('utf-8') if isinstance(val, bytes) else val
                    if val_str == token:
                        key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                        device_hash = key_str.replace("fcm_token_map:", "")
                        break
            if device_hash or cursor == 0:
                break

        if device_hash:
            redis_client.delete(f"fcm_token_map:{device_hash}")
            logger.info(f"🗑️ [FCM] Token map silindi: {device_hash}")

            alarm_cursor   = 0
            deleted_alarms = 0
            while True:
                alarm_cursor, alarm_keys = redis_client.scan(
                    alarm_cursor, match=f"alarm:{device_hash}:*", count=100
                )
                if alarm_keys:
                    redis_client.delete(*alarm_keys)
                    deleted_alarms += len(alarm_keys)
                if alarm_cursor == 0:
                    break

            if deleted_alarms > 0:
                logger.info(f"🗑️ [FCM] {deleted_alarms} alarm silindi (cihaz: {device_hash})")
        else:
            logger.debug(f"🔍 [FCM] Token map bulunamadı, alarm temizleme atlandı")

        return True

    except Exception as e:
        logger.error(f"❌ [FCM] Token silme hatası: {e}")
        return False


def is_token_registered(token: str) -> bool:
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


def cleanup_invalid_tokens() -> Dict:
    try:
        if not firebase_admin._apps:
            logger.error("❌ [CLEANUP] Firebase başlatılmamış, temizlik atlanıyor")
            return {"success": False, "error": "Firebase not initialized"}

        logger.info("🧹 [CLEANUP] Geçersiz token temizliği başlıyor...")

        all_tokens = get_all_tokens()
        if not all_tokens:
            logger.info("ℹ️ [CLEANUP] Kontrol edilecek token yok")
            return {"success": True, "checked": 0, "removed": 0}

        total_checked = 0
        total_removed = 0

        for i in range(0, len(all_tokens), FCM_BATCH_SIZE):
            batch = all_tokens[i:i + FCM_BATCH_SIZE]

            messages = [
                messaging.Message(
                    data={"type": "dry_run"},
                    token=token,
                    android=messaging.AndroidConfig(priority="normal")
                )
                for token in batch
            ]

            try:
                response = messaging.send_each(messages, dry_run=True)
                total_checked += len(batch)

                for idx, send_response in enumerate(response.responses):
                    if not send_response.success:
                        err = send_response.exception
                        if err and _is_invalid_token_error(err):
                            unregister_fcm_token(batch[idx])
                            total_removed += 1
                            logger.info(f"🗑️ [CLEANUP] Geçersiz token silindi: {batch[idx][:20]}...")

            except Exception as batch_err:
                if _is_firebase_init_error(batch_err):
                    logger.error(f"❌ [CLEANUP] Firebase init hatası: {batch_err}")
                    break
                logger.error(f"❌ [CLEANUP] Batch hatası: {batch_err}")

            time.sleep(0.2)

        logger.info(f"✅ [CLEANUP] Temizlik tamamlandı: {total_checked} kontrol edildi, {total_removed} silindi")

        return {
            "success":   True,
            "checked":   total_checked,
            "removed":   total_removed,
            "remaining": total_checked - total_removed,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ [CLEANUP] Beklenmeyen hata: {e}")
        import traceback
        logger.error(f"   Traceback: {traceback.format_exc()}")
        return {"success": False, "error": str(e)}


def get_tokens_generator(batch_size: int = 25) -> Generator[List[str], None, None]:
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


def _send_batch(
    batch_tokens: List[str],
    data_payload: Dict,
    priority: str,
    batch_num: int,
    batch_count: int
) -> Dict:
    """Tek bir batch'i FCM'e gönderir. send_notification ve send_to_all tarafından ortak kullanılır."""
    total_success     = 0
    total_failure     = 0
    failed_tokens     = []

    logger.info(f"📤 [FCM] Batch {batch_num}/{batch_count} gönderiliyor ({len(batch_tokens)} token)...")

    try:
        response = messaging.send_each_for_multicast(
            messaging.MulticastMessage(
                tokens=batch_tokens,
                data=data_payload,
                android=messaging.AndroidConfig(priority=priority)
            )
        )

        total_success += response.success_count
        total_failure += response.failure_count

        if response.failure_count > 0:
            for idx, send_response in enumerate(response.responses):
                if not send_response.success:
                    err = send_response.exception
                    if err and _is_invalid_token_error(err):
                        failed_tokens.append(batch_tokens[idx])
                        logger.debug(f"   ❌ Geçersiz token {idx+1}: {err}")
                    else:
                        logger.debug(f"   ⚠️ Geçici hata token {idx+1}: {err} (token korunuyor)")

        logger.info(f"   ✅ Batch {batch_num}: {response.success_count} başarılı, {response.failure_count} başarısız")

    except Exception as batch_error:
        if _is_firebase_init_error(batch_error):
            logger.error(f"❌ [FCM] Batch {batch_num} Firebase init hatası: {batch_error}")
        else:
            logger.error(f"❌ [FCM] Batch {batch_num} kritik hata: {batch_error}")
        total_failure += len(batch_tokens)

    if failed_tokens:
        logger.warning(f"🗑️ [FCM] {len(failed_tokens)} geçersiz token temizleniyor...")
        for token in failed_tokens:
            unregister_fcm_token(token)

    return {"success_count": total_success, "failure_count": total_failure}


def send_notification(
    tokens: List[str],
    title: str,
    body: str,
    data: Optional[Dict] = None,
    priority: str = "high",
    sound: str = "default"
) -> Dict:
    try:
        if not tokens:
            logger.warning("⚠️ [FCM] Token bulunamadı!")
            return {"success": False, "error": "No tokens"}

        if not firebase_admin._apps:
            logger.error("❌ [FCM] Firebase başlatılmamış! Token gönderimi atlanıyor, tokenlar KORUNUYOR.")
            return {"success": False, "error": "Firebase not initialized", "tokens_preserved": True}

        data_payload          = dict(data) if data else {}
        data_payload["title"] = title
        data_payload["body"]  = body

        total_success = 0
        total_failure = 0
        total_tokens  = len(tokens)
        batch_count   = (total_tokens + FCM_BATCH_SIZE - 1) // FCM_BATCH_SIZE

        logger.info(f"📦 [FCM] {total_tokens} token, {batch_count} batch'e bölünüyor...")

        for i in range(0, total_tokens, FCM_BATCH_SIZE):
            batch_tokens = tokens[i:i + FCM_BATCH_SIZE]
            batch_num    = (i // FCM_BATCH_SIZE) + 1

            result         = _send_batch(batch_tokens, data_payload, priority, batch_num, batch_count)
            total_success += result["success_count"]
            total_failure += result["failure_count"]

            if batch_num < batch_count:
                time.sleep(0.1)

        logger.info(f"🎉 [FCM] Gönderim tamamlandı!")
        logger.info(f"   📊 Toplam: {total_tokens} token")
        logger.info(f"   ✅ Başarılı: {total_success}")
        logger.info(f"   ❌ Başarısız: {total_failure}")
        logger.info(f"   📝 Başlık: {title}")
        logger.info(f"   📄 Mesaj: {body[:50]}...")

        set_cache(Config.CACHE_KEYS['fcm_last_notification'], str(datetime.now().timestamp()), ttl=86400)

        return {
            "success":       True,
            "success_count": total_success,
            "failure_count": total_failure,
            "total_tokens":  total_tokens,
            "batch_count":   batch_count,
            "timestamp":     datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ [FCM] Bildirim gönderme hatası: {e}")
        import traceback
        logger.error(f"   Traceback: {traceback.format_exc()}")
        return {"success": False, "error": str(e)}


def send_to_all(title: str, body: str, data: Optional[Dict] = None, priority: str = "high") -> Dict:
    try:
        if not firebase_admin._apps:
            logger.error("❌ [FCM] Firebase başlatılmamış! send_to_all atlanıyor, tokenlar KORUNUYOR.")
            return {"success": False, "error": "Firebase not initialized", "tokens_preserved": True}

        logger.info("📢 [FCM] Toplu bildirim gönderiliyor (Generator modu)...")

        data_payload          = dict(data) if data else {}
        data_payload["title"] = title
        data_payload["body"]  = body

        total_success = 0
        total_failure = 0
        total_tokens  = 0
        batch_num     = 0

        # Toplam token sayısını batch sayısı için önceden al
        total_token_count = get_token_count()
        batch_count       = (total_token_count + FCM_BATCH_SIZE - 1) // FCM_BATCH_SIZE if total_token_count else 1

        for batch_tokens in get_tokens_generator(batch_size=FCM_BATCH_SIZE):
            if not batch_tokens:
                continue

            batch_num    += 1
            total_tokens += len(batch_tokens)

            result         = _send_batch(batch_tokens, data_payload, priority, batch_num, batch_count)
            total_success += result["success_count"]
            total_failure += result["failure_count"]

            time.sleep(0.2)

        if total_tokens == 0:
            logger.warning("⚠️ [FCM] Hiç kayıtlı cihaz yok!")
            return {"success": False, "error": "No registered devices"}

        logger.info(f"🏁 [FCM] Toplu gönderim tamamlandı!")
        logger.info(f"   📊 Toplam: {total_tokens} token")
        logger.info(f"   ✅ Başarılı: {total_success}")
        logger.info(f"   ❌ Başarısız: {total_failure}")

        set_cache(Config.CACHE_KEYS['fcm_last_notification'], str(datetime.now().timestamp()), ttl=86400)

        return {
            "success":       True,
            "total_sent":    total_tokens,
            "success_count": total_success,
            "failure_count": total_failure,
            "batch_count":   batch_num,
            "timestamp":     datetime.now().isoformat()
        }

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
            alarm_status      = "Hedef ÜZERİNE çıktı" if alarm_type == "HIGH" else "Hedef ALTINA düştü"
            change_symbol     = "+" if change_from_start >= 0 else ""

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
            alarm_status      = f"%{percent_value:.1f} YÜKSELDİ" if percent_direction == "UP" else f"%{percent_value:.1f} DÜŞTÜ"
            change_symbol     = "+" if change_from_start >= 0 else ""

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
                data=data,
                token=fcm_token,
                android=messaging.AndroidConfig(priority='high')
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
    title     = f"{emoji} {currency_code} Fiyat Uyarısı!"
    body      = f"{direction} {price:.4f} TL ({change_percent:+.2f}%)"
    data      = {
        "type":     "price_alert",
        "currency": currency_code,
        "price":    str(price),
        "change":   str(change_percent)
    }
    return send_to_all(title, body, data)


def send_daily_summary() -> Dict:
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
    data  = {
        "type":      "test",
        "timestamp": str(datetime.now().timestamp())
    }
    return send_to_all(title, body, data)
