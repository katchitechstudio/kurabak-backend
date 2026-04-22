"""
Telegram Monitor - ŞEF KOMUTA MERKEZİ V5.3
=======================================================
✅ CIRCUIT BREAKER SPAM FIX: 15 dakika sürekli hata → TEK uyarı
✅ SELF-HEALING: Otomatik CPU/RAM izleme ve müdahale
✅ 🔒 ADMİN GÜVENLİĞİ: Sadece yetkili Telegram ID komut gönderebilir
✅ GÜNLÜK RAPOR: CPU, RAM, Disk, Circuit Breaker, Aktif kullanıcı
✅ 📱 V5.3: Device ID bazlı online tracking (10dk aktif + 12sa unique)
✅ TEMİZLENMİŞ KOMUTLAR: Sadece işe yarayanlar kaldı
   - /durum, /circuit, /online, /temizle, /duyuru, /bakim
"""

import os
import requests
import logging
import threading
import psutil
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

ALLOWED_ADMIN_IDS = [7101853980]


class TelegramMonitor:

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token  = bot_token
        self.chat_id    = chat_id
        self.base_url   = f"https://api.telegram.org/bot{bot_token}"
        self._lock      = threading.Lock()

        self.circuit_error_start_time  = None
        self.circuit_recovery_notified = False
        self.circuit_down_notified     = False

        self.last_critical_alert = datetime.min
        self.command_thread      = None
        self.is_listening        = False
        self.healing_thread      = None
        self.is_healing_active   = False

    # ──────────────────────────────────────────────
    # TEMEL GÖNDERIM
    # ──────────────────────────────────────────────

    def _send_raw(self, text: str, parse_mode: str = 'Markdown'):
        try:
            url     = f"{self.base_url}/sendMessage"
            payload = {
                'chat_id':                  self.chat_id,
                'text':                     text,
                'parse_mode':               parse_mode,
                'disable_web_page_preview': True,
            }
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"❌ Telegram Gönderim Hatası: {e}")

    def send_message(self, text: str, level: str = 'info') -> bool:
        if level in ['info', 'success', 'warning']:
            logger.info(f"Telegram (Sessiz): {text}")
            return True

        if level == 'critical':
            with self._lock:
                now = datetime.now()
                if (now - self.last_critical_alert) < timedelta(minutes=30):
                    logger.warning("Telegram: Kritik hata spam korumasına takıldı.")
                    return False
                self.last_critical_alert = now
            alert_msg = (
                f"🚨 *KRİTİK SİSTEM UYARISI* 🚨\n\n"
                f"{text}\n\n"
                f"⏳ _Zaman: {datetime.now().strftime('%H:%M:%S')}_"
            )
            threading.Thread(target=self._send_raw, args=(alert_msg,)).start()
            return True

        if level == 'report':
            threading.Thread(target=self._send_raw, args=(text,)).start()
            return True

        return False

    # ──────────────────────────────────────────────
    # CIRCUIT BREAKER OLAYLARI
    # ──────────────────────────────────────────────

    def notify_circuit_breaker_event(self, event_type: str, details: Dict[str, Any] = None):
        now = time.time()

        if event_type == "error":
            if self.circuit_error_start_time is None:
                self.circuit_error_start_time = now
                return
            error_duration = now - self.circuit_error_start_time
            if error_duration >= 900 and not self.circuit_down_notified:
                self.circuit_down_notified     = True
                self.circuit_recovery_notified = False
                threading.Thread(target=self._send_raw, args=(
                    f"🚨 *KRİTİK: V5 API 15 DAKİKADIR ÇALIŞMIYOR!*\n\n"
                    f"⏱️ *Süre:* {int(error_duration/60)} dakika\n"
                    f"💾 *Durum:* Backup veri kullanılıyor\n"
                    f"🔄 *Aksiyon:* Sistem otomatik kurtarma yapıyor\n\n"
                    f"_Sistem düzelince haber vereceğim._",
                )).start()

        elif event_type == "recovery":
            if self.circuit_down_notified and not self.circuit_recovery_notified:
                self.circuit_recovery_notified = True
                self.circuit_down_notified     = False
                self.circuit_error_start_time  = None
                downtime = ""
                if details and 'downtime_minutes' in details:
                    downtime = f"\n⏱️ *Downtime:* {details['downtime_minutes']} dakika"
                threading.Thread(target=self._send_raw, args=(
                    f"✅ *SİSTEM KURTARILDI!*\n\n"
                    f"🚀 V5 API tekrar çalışıyor\n"
                    f"📊 Veriler güncelleniyor{downtime}\n\n"
                    f"_Sistem normale döndü, sorun çözüldü._",
                )).start()
            else:
                self.circuit_error_start_time = None

    # ──────────────────────────────────────────────
    # GÜNLÜK RAPOR
    # ──────────────────────────────────────────────

    def send_daily_report(self, metrics: Dict[str, Any]):
        try:
            now      = datetime.now()
            date_str = now.strftime("%d.%m.%Y")

            total        = metrics.get('v5', 0) + metrics.get('backup', 0)
            success_rate = 100 if total == 0 else ((total - metrics.get('errors', 0)) / total) * 100
            status_icon  = "🟢" if success_rate > 95 else "🟡" if success_rate > 80 else "🔴"

            cpu  = psutil.cpu_percent(interval=1)
            ram  = psutil.virtual_memory().percent
            disk = psutil.disk_usage('/').percent

            cpu_icon  = "🟢" if cpu  < 80 else "🟡" if cpu  < 90 else "🔴"
            ram_icon  = "🟢" if ram  < 80 else "🟡" if ram  < 95 else "🔴"
            disk_icon = "🟢" if disk < 80 else "🟡" if disk < 90 else "🔴"

            # 12 saatlik unique cihaz sayısı
            try:
                from utils.cache import get_cache_keys
                daily_count = len(get_cache_keys("daily_user:*"))
            except Exception:
                daily_count = 0

            cb_status   = metrics.get('circuit_breaker', {})
            cb_state    = cb_status.get('state', 'UNKNOWN')
            cb_failures = cb_status.get('failure_count', 0)
            cb_icon     = "🟢" if cb_state == "CLOSED" else "🟡" if cb_state == "HALF_OPEN" else "🔴"
            cb_text     = f"{cb_icon} {cb_state}" + (f" ({cb_failures} hata)" if cb_failures > 0 else "")

            special_events = []
            if cb_state == "OPEN":
                special_events.append("🔴 Circuit Breaker açıldı (API hatası)")
            elif cb_state == "HALF_OPEN":
                special_events.append("🟡 Circuit Breaker test modunda")
            if metrics.get('circuit_breaker_trips', 0) > 0:
                special_events.append(f"⚡ Circuit Breaker {metrics['circuit_breaker_trips']} kez tetiklendi")

            try:
                from utils.cache import get_cache, get_disk_backup_stats
                from config import Config
                cleanup_last_run = get_cache(Config.CACHE_KEYS.get('cleanup_last_run'))
                if cleanup_last_run:
                    cleanup_time = datetime.fromtimestamp(float(cleanup_last_run))
                    if cleanup_time.date() == now.date():
                        stats = get_disk_backup_stats()
                        special_events.append(
                            f"🧹 Cleanup çalıştı: {stats.get('total_files', 0)} dosya, "
                            f"{stats.get('total_size_mb', 0)} MB"
                        )
            except Exception:
                pass

            lines = [
                f"🌙 *GÜN SONU RAPORU* | {date_str}",
                f"━━━━━━━━━━━━━━━━━━━━\n",
                f"📊 *GENEL DURUM*",
                f"• Durum: {status_icon} *{'Mükemmel' if success_rate > 95 else 'Stabil'}*",
                f"• Başarı Oranı: *%{success_rate:.1f}*",
                f"• Toplam İşlem: *{total}*\n",
                f"💻 *SİSTEM KAYNAKLARI*",
                f"• {cpu_icon} CPU: *%{cpu:.1f}*",
                f"• {ram_icon} RAM: *%{ram:.1f}*",
                f"• {disk_icon} Disk: *%{disk:.1f}*\n",
                f"🔌 *API & KAYNAK*",
                f"• 🚀 V5 API: `{metrics.get('v5', 0)}`",
                f"• 📦 Backup: `{metrics.get('backup', 0)}`",
                f"• 🛡️ Circuit Breaker: {cb_text}\n",
                f"👥 *KULLANICILAR*",
                f"• Son 12 Saat Unique: *{daily_count}* cihaz\n",
                f"🛡️ *GÜVENLİK & HATALAR*",
                f"• Hatalar: `{metrics.get('errors', 0)}`",
            ]

            if special_events:
                lines.append(f"\n🔔 *ÖZEL OLAYLAR*")
                for event in special_events:
                    lines.append(f"• {event}")

            lines.append(f"\n_KuraBak Backend v5.3 • {now.strftime('%H:%M')}_")
            self.send_message("\n".join(lines), level='report')

        except Exception as e:
            logger.error(f"❌ Günlük rapor hatası: {e}")
            self.send_message(
                f"🌙 *GÜN SONU RAPORU*\n\n⚠️ Detaylı rapor oluşturulamadı\nHata: {str(e)[:100]}",
                level='report'
            )

    # ──────────────────────────────────────────────
    # STARTUP & TAKVİM
    # ──────────────────────────────────────────────

    def send_startup_message(self):
        from config import Config
        self.send_message(
            f"🚀 *SİSTEM BAŞLATILDI*\n\n"
            f"📦 v{Config.APP_VERSION} • V5 API Only\n"
            f"🛡️ Circuit Breaker • Self-Healing\n"
            f"🔔 Push (12:00) • Cleanup (03:00)\n\n"
            f"✅ Tüm sistemler online!",
            level='report'
        )

    def send_calendar_notification(self, event_name: str, event_date: str):
        self.send_message(
            f"📅 *TAKVİM UYARISI*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📌 *Etkinlik:* {event_name}\n"
            f"🗓️ *Tarih:* {event_date}\n\n"
            f"ℹ️ Banner otomatik olarak aktif edilecek.",
            level='report'
        )

    # ──────────────────────────────────────────────
    # KOMUT DİNLEYİCİ
    # ──────────────────────────────────────────────

    def start_command_listener(self):
        if self.is_listening:
            return
        self.is_listening  = True
        self.command_thread = threading.Thread(target=self._listen_commands, daemon=True)
        self.command_thread.start()
        logger.info("🤖 Şef Komut Dinleyici başlatıldı! 🔒 Admin Filter: ACTIVE")

    def _is_admin(self, user_id: int) -> bool:
        return user_id in ALLOWED_ADMIN_IDS

    def _listen_commands(self):
        offset = 0
        while self.is_listening:
            try:
                response = requests.get(
                    f"{self.base_url}/getUpdates",
                    params={'offset': offset, 'timeout': 30, 'allowed_updates': ['message']},
                    timeout=35,
                )
                data = response.json()
                if not data.get('ok'):
                    time.sleep(5)
                    continue

                for update in data.get('result', []):
                    offset  = update['update_id'] + 1
                    message = update.get('message')
                    if not message:
                        continue
                    if str(message.get('chat', {}).get('id')) != str(self.chat_id):
                        continue

                    user_id = message.get('from', {}).get('id')
                    if not self._is_admin(user_id):
                        username = message.get('from', {}).get('username', 'Unknown')
                        logger.warning(f"🚨 Yetkisiz komut! User ID: {user_id}, @{username}")
                        self._send_raw(
                            "🔒 *ERİŞİM ENGELLENDİ*\n\n"
                            "Sadece yetkili admin kullanabilir.\n"
                            "⚠️ Bu deneme kaydedildi."
                        )
                        continue

                    text = message.get('text', '').strip()

                    if text == '/durum':
                        self._handle_durum()
                    elif text == '/online':
                        self._handle_online()
                    elif text == '/temizle':
                        self._handle_temizle()
                    elif text == '/circuit':
                        self._handle_circuit()
                    elif text.startswith('/duyuru'):
                        self._handle_duyuru(text)
                    elif text.startswith('/bakim'):
                        self._handle_bakim(text)
                    else:
                        self._send_help()

            except Exception as e:
                logger.error(f"Komut dinleyici hatası: {e}")
                time.sleep(10)

    # ──────────────────────────────────────────────
    # KOMUT HANDLERS
    # ──────────────────────────────────────────────

    def _send_help(self):
        self._send_raw(
            "❓ *KOMUT LİSTESİ* 🔒\n\n"
            "📊 *RAPOR:*\n"
            "`/durum` - Sistem sağlık raporu\n"
            "`/online` - Kullanıcı analizi\n"
            "`/circuit` - Circuit Breaker durumu\n\n"
            "📢 *YÖNETİM:*\n"
            "`/duyuru [mesaj]` - Duyuru as\n"
            "`/duyuru sil` - Duyuruyu kaldır\n"
            "`/bakim` - Bakım modu aç\n"
            "`/bakim kapat` - Bakım kapat\n\n"
            "🧹 *BAKIM:*\n"
            "`/temizle` - Güvenli cache temizliği\n\n"
            "🔒 _Sadece yetkili admin kullanabilir._"
        )

    def _handle_durum(self):
        try:
            from utils.cache import get_cache, redis_wrapper
            from config import Config

            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent

            last_worker_run = get_cache(Config.CACHE_KEYS['last_worker_run'])
            if last_worker_run:
                diff = time.time() - float(last_worker_run)
                if diff > 600:
                    worker_icon, worker_text = "🔴", f"Uyuyor ({int(diff/60)} dk)"
                elif diff > 300:
                    worker_icon, worker_text = "🟡", f"Yavaş ({int(diff/60)} dk)"
                else:
                    worker_icon, worker_text = "🟢", f"Aktif ({int(diff)}sn önce)"
            else:
                worker_icon, worker_text = "⚪", "Henüz Çalışmadı"

            redis_status     = "🟢 Bağlı" if redis_wrapper.is_enabled() else "🔴 RAM Modu"
            snapshot_exists  = bool(get_cache(Config.CACHE_KEYS['yesterday_prices']))
            maintenance_data = get_cache(Config.CACHE_KEYS['maintenance'])

            self._send_raw(
                f"👮‍♂️ *SİSTEM DURUMU*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"⚡ *SUNUCU*\n"
                f"• CPU: `%{cpu:.1f}`\n"
                f"• RAM: `%{ram:.1f}`\n"
                f"• Redis: {redis_status}\n\n"
                f"🛠️ *BİLEŞENLER*\n"
                f"• {worker_icon} Worker: `{worker_text}`\n"
                f"• {'🟢' if snapshot_exists else '🔴'} Snapshot: `{'Mevcut' if snapshot_exists else 'Kayıp'}`\n"
                f"• 🤖 Self-Healing: `{'Aktif' if self.is_healing_active else 'Kapalı'}`\n\n"
                f"🚧 *MODLAR*\n"
                f"• Bakım: `{'🔴 Aktif' if maintenance_data else '🟢 Kapalı'}`\n\n"
                f"_Rapor: {datetime.now().strftime('%H:%M:%S')}_"
            )
        except Exception as e:
            self._send_raw(f"❌ Durum raporu hatası: {str(e)}")

    def _handle_online(self):
        try:
            from utils.cache import get_cache_keys

            online_keys  = get_cache_keys("online_user:*")
            daily_keys   = get_cache_keys("daily_user:*")
            active_count = len(online_keys)
            daily_count  = len(daily_keys)

            # IP gibi görünenleri ayıkla
            import re
            ip_pattern   = re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$')
            device_based = sum(1 for k in daily_keys if not ip_pattern.match(k.replace("daily_user:", "")))
            ip_based     = daily_count - device_based

            if active_count == 0 and daily_count == 0:
                self._send_raw(
                    "📱 *KULLANICI ANALİZİ*\n\n"
                    "Şu an aktif kullanıcı yok.\n\n"
                    "_Son 10 dakika içinde istek atan cihazlar_"
                )
                return

            icon = "🔥" if active_count > 50 else "📊" if active_count > 10 else "📱"

            self._send_raw(
                f"{icon} *KULLANICI ANALİZİ*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"⚡ *ŞU AN AKTİF* (son 10 dk)\n"
                f"• Aktif Cihaz: `{active_count}`\n\n"
                f"📅 *SON 12 SAAT*\n"
                f"• Unique Cihaz: `{daily_count}`\n"
                f"• Device ID Bazlı: `{device_based}`\n"
                f"• IP Bazlı (fallback): `{ip_based}`\n\n"
                f"_Device ID = Android ID ile tanımlanan gerçek cihazlar_"
            )
        except Exception as e:
            logger.error(f"Online sayım hatası: {e}")
            self._send_raw(f"❌ Online sayım hatası: {str(e)}")

    def _handle_circuit(self):
        try:
            from services.financial_service import get_circuit_breaker_status
            status  = get_circuit_breaker_status()
            state   = status.get('state', 'UNKNOWN')
            failures = status.get('failure_count', 0)
            timeout  = status.get('timeout', 0)

            if state == "CLOSED":
                icon, status_text, detail = "🟢", "Normal Çalışıyor", "API çağrıları yapılıyor"
            elif state == "OPEN":
                icon, status_text = "🔴", "Devre Açık"
                last_open = status.get('last_open_time', 0)
                remaining = max(0, timeout - int(time.time() - last_open)) if last_open else timeout
                detail    = f"{remaining} saniye sonra test edilecek"
            elif state == "HALF_OPEN":
                icon, status_text, detail = "🟡", "Test Modu", "1 deneme yapılıyor..."
            else:
                icon, status_text, detail = "⚪", "Bilinmiyor", ""

            report = (
                f"{icon} *CIRCUIT BREAKER*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📊 *Durum:* {status_text}\n"
                f"🔢 *State:* `{state}`\n"
                f"❌ *Hata Sayısı:* {failures}\n"
                f"⏱️ *Timeout:* {timeout} saniye\n"
            )
            if detail:
                report += f"\nℹ️ {detail}"
            self._send_raw(report)
        except Exception as e:
            self._send_raw(f"❌ Circuit breaker sorgu hatası: {str(e)}")

    def _handle_temizle(self):
        try:
            from utils.cache import get_redis_client, delete_cache
            from config import Config

            self._send_raw(
                "⚠️ *GÜVENLİ CACHE TEMİZLİĞİ*\n\n"
                "Sadece KuraBak cache'leri silinecek.\n"
                "İşlem başlatılıyor..."
            )

            deleted_count = 0
            redis_client  = get_redis_client()

            if redis_client:
                keys = redis_client.keys("kurabak:*")
                if keys:
                    for key in keys:
                        try:
                            redis_client.delete(key)
                            deleted_count += 1
                        except Exception:
                            pass
                    self._send_raw(
                        f"✅ *TEMİZLİK TAMAMLANDI*\n\n"
                        f"🧹 Silinen: {deleted_count} key\n"
                        f"🔗 Redis Bağlantısı: Korundu ✅\n"
                        f"🔄 Worker 2 dakika içinde yeni veri çekecek."
                    )
                else:
                    self._send_raw("ℹ️ Cache zaten boş.")
            else:
                known_keys = [
                    Config.CACHE_KEYS.get('currencies_all'),
                    Config.CACHE_KEYS.get('golds_all'),
                    Config.CACHE_KEYS.get('silvers_all'),
                    Config.CACHE_KEYS.get('yesterday_prices'),
                    Config.CACHE_KEYS.get('last_worker_run'),
                    'system_banner',
                ]
                for key in known_keys:
                    if key:
                        delete_cache(key)
                        deleted_count += 1
                self._send_raw(
                    f"✅ *RAM CACHE TEMİZLENDİ*\n\n"
                    f"🧹 Silindi: {deleted_count} key\n"
                    f"⚠️ Redis yok (RAM modu)\n"
                    f"🔄 Worker 2 dakika içinde yeni veri çekecek."
                )
        except Exception as e:
            logger.error(f"Temizlik hatası: {e}")
            self._send_raw(f"❌ Temizlik hatası: `{str(e)[:150]}`")

    def _handle_duyuru(self, text):
        try:
            from utils.cache import set_cache, delete_cache
            from config import Config

            content = text.replace('/duyuru', '').strip()

            if not content or content.lower() == 'sil':
                delete_cache(Config.CACHE_KEYS['banner'])
                self._send_raw("🔇 *DUYURU KALDIRILDI*")
                return

            set_cache(Config.CACHE_KEYS['banner'], content, ttl=0)
            self._send_raw(
                f"📢 *DUYURU YAYINDA!*\n\n"
                f"📝 *Mesaj:* \"{content}\"\n"
                f"⏱️ *Süre:* Süresiz ♾️\n\n"
                f"✅ Uygulama ekranlarında görünüyor."
            )
        except Exception as e:
            self._send_raw(f"❌ Duyuru hatası: {str(e)}")

    def _handle_bakim(self, text):
        try:
            from services.maintenance_service import activate_maintenance, deactivate_maintenance

            content = text.replace('/bakim', '').strip().lower()

            if content in ['kapat', 'sil', '']:
                deactivate_maintenance()
                self._send_raw("✅ *BAKIM MODU KAPANDI*\n\nSistem normal moda döndü.")
                return

            activate_maintenance()
            self._send_raw(
                f"🚧 *BAKIM MODU AKTİF!*\n\n"
                f"Kullanıcılar bilgilendiriliyor.\n\n"
                f"Kapatmak için: `/bakim kapat`"
            )
        except Exception as e:
            self._send_raw(f"❌ Bakım modu hatası: {str(e)}")

    # ──────────────────────────────────────────────
    # SELF-HEALING
    # ──────────────────────────────────────────────

    def start_self_healing(self):
        if self.is_healing_active:
            return
        self.is_healing_active = True
        self.healing_thread    = threading.Thread(target=self._self_healing_loop, daemon=True)
        self.healing_thread.start()
        logger.info("🤖 Self-Healing sistemi başlatıldı!")

    def _self_healing_loop(self):
        from config import Config

        cpu_high_since        = None
        last_cpu_notification = 0
        last_ram_notification = 0

        while self.is_healing_active:
            try:
                cpu = psutil.cpu_percent(interval=1)
                ram = psutil.virtual_memory().percent
                now = time.time()

                # CPU kontrolü
                if cpu > Config.CPU_THRESHOLD:
                    if cpu_high_since is None:
                        cpu_high_since = now
                    elif (now - cpu_high_since) > Config.CPU_HIGH_DURATION:
                        if (now - last_cpu_notification) > Config.ALARM_NOTIFICATION_INTERVAL:
                            self._send_raw(
                                f"⚠️ *CPU YÜKSEK!*\n\n"
                                f"🧠 CPU: %{cpu:.1f}\n"
                                f"⏱️ Süre: {int((now - cpu_high_since)/60)} dakika\n\n"
                                f"Sistem müdahale edecek..."
                            )
                            last_cpu_notification = now
                        cpu_high_since = None
                else:
                    if cpu_high_since is not None:
                        logger.info(f"✅ CPU normale döndü: %{cpu:.1f}")
                    cpu_high_since = None

                # RAM kontrolü
                if ram > Config.RAM_THRESHOLD:
                    logger.warning(f"💾 RAM KRİTİK ({ram}%), otomatik temizlik...")
                    try:
                        from utils.cache import get_redis_client
                        redis_client = get_redis_client()
                        if redis_client:
                            for key in redis_client.keys("kurabak:*"):
                                try:
                                    redis_client.delete(key)
                                except Exception:
                                    pass

                        new_ram = psutil.virtual_memory().percent
                        if (now - last_ram_notification) > Config.ALARM_NOTIFICATION_INTERVAL:
                            if new_ram < Config.RAM_THRESHOLD:
                                self._send_raw(
                                    f"✅ *RAM DÜZELTİLDİ*\n\n"
                                    f"💾 Önceki: %{ram:.1f} → Şimdi: %{new_ram:.1f}\n"
                                    f"Cache temizlendi!"
                                )
                            else:
                                self._send_raw(
                                    f"⚠️ *RAM HALA YÜKSEK!*\n\n"
                                    f"💾 RAM: %{new_ram:.1f}\n"
                                    f"Temizlik yaptım ama düşmüyor. Kontrol et!"
                                )
                            last_ram_notification = now
                    except Exception as e:
                        logger.error(f"❌ RAM temizlik hatası: {e}")

                time.sleep(Config.ALARM_CHECK_INTERVAL)

            except Exception as e:
                logger.error(f"Self-Healing hatası: {e}")
                time.sleep(60)


# ──────────────────────────────────────────────
# SINGLETON
# ──────────────────────────────────────────────

telegram_monitor:  Optional[TelegramMonitor] = None
telegram_instance: Optional[TelegramMonitor] = None


def init_telegram_monitor() -> Optional[TelegramMonitor]:
    global telegram_monitor, telegram_instance

    if telegram_monitor:
        return telegram_monitor

    token   = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')

    if token and chat_id:
        telegram_monitor  = TelegramMonitor(token, chat_id)
        telegram_instance = telegram_monitor
        telegram_monitor.start_command_listener()
        telegram_monitor.start_self_healing()
        logger.info("✅ Telegram Monitor başlatıldı.")
        return telegram_monitor

    logger.warning("⚠️ Telegram Monitor başlatılamadı! Token veya Chat ID eksik.")
    telegram_instance = None
    return None


def get_telegram_monitor() -> Optional[TelegramMonitor]:
    return telegram_monitor
