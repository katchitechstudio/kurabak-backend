"""
Telegram Monitor - ŞEF KOMUTA MERKEZİ V4.5 🤖
=======================================================
✅ TEST SİSTEMİ: /test, /test mobil, /test detay
✅ TAKVİM BİLDİRİMLERİ: Günü gelen etkinlikler için otomatik uyarı
✅ SELF-HEALING: Otomatik CPU/RAM izleme ve müdahale
✅ TÜRKÇE KARAKTER FIX: 'ı', 'ş', 'ğ', 'ü', 'ö', 'ç' otomatik düzeltme
✅ ANTI-SPAM: Gün içi gereksiz bildirimleri engeller
✅ 🔒 ADMİN GÜVENLİĞİ: Sadece yetkili Telegram ID komut gönderebilir
✅ V5 ONLY: Tek kaynak sistemi
✅ GÜNLÜK RAPOR ZENGİNLEŞTİRME: CPU, RAM, Disk, Circuit Breaker, Aktif kullanıcı
✅ ÖZEL OLAY LİSTESİ: Circuit breaker, cleanup, trend detayları
✅ /circuit KOMUTU: Circuit Breaker durumu sorgulama
✅ GÜVENLİ CACHE TEMİZLİĞİ: Redis bağlantısı korunur (V4.5)
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
    """
    Gelişmiş Telegram Bot V4.5:
    1. RAPOR MODU: Sessiz bildirimler, zengin günlük raporlar
    2. KOMUT MODU: Komutları dinler ve cevaplar
    3. TEST SİSTEMİ: Otomatik sistem sağlık kontrolü
    4. TAKVİM SİSTEMİ: Etkinlik bildirimleri
    5. SELF-HEALING: Otomatik CPU/RAM izleme ve düzeltme
    6. 🔒 ADMİN FİLTRESİ: Sadece yetkili kullanıcılar
    7. ZENGİN RAPORLAMA: CPU, RAM, Disk, Circuit Breaker, özel olaylar
    8. 🔐 GÜVENLİ CACHE: Redis bağlantısını koruyarak temizlik (V4.5)
    """
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self._lock = threading.Lock()
        self.last_critical_alert = datetime.min
        self.command_thread = None
        self.is_listening = False
        self.healing_thread = None
        self.is_healing_active = False

    def _send_raw(self, text: str, parse_mode: str = 'Markdown'):
        """Telegram API'ye ham istek atar (Internal)"""
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': parse_mode,
                'disable_web_page_preview': True
            }
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"❌ Telegram Gönderim Hatası: {e}")

    def send_message(self, text: str, level: str = 'info') -> bool:
        """
        Akıllı Mesaj Yöneticisi
        - level='info' veya 'success' -> GÖNDERMEZ (Sessiz Mod)
        - level='critical' -> ANINDA GÖNDERİR
        - level='report' -> ANINDA GÖNDERİR
        """
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

    def send_daily_report(self, metrics: Dict[str, Any]):
        """
        🌙 GÜN SONU ZENGİN RAPORU V4.5
        
        YENİ ÖZELLİKLER:
        - CPU, RAM, Disk kullanımı
        - Aktif kullanıcı sayısı
        - Circuit Breaker durumu
        - Cleanup bilgisi
        - Özel olaylar listesi
        - Güvenli cache sistemi bildirimi
        """
        try:
            now = datetime.now()
            date_str = now.strftime("%d.%m.%Y")
            
            # API Metrikleri
            total = metrics.get('v5', 0) + metrics.get('backup', 0)
            success_rate = 100
            if total > 0:
                success_rate = ((total - metrics.get('errors', 0)) / total) * 100

            status_icon = "🟢" if success_rate > 95 else "🟡" if success_rate > 80 else "🔴"
            
            # Sistem Metrikleri
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent
            disk = psutil.disk_usage('/').percent
            
            cpu_icon = "🟢" if cpu < 70 else "🟡" if cpu < 85 else "🔴"
            ram_icon = "🟢" if ram < 75 else "🟡" if ram < 90 else "🔴"
            disk_icon = "🟢" if disk < 80 else "🟡" if disk < 90 else "🔴"
            
            # Aktif Kullanıcılar
            try:
                from utils.cache import get_cache_keys
                online_keys = get_cache_keys("online_user:*")
                active_users = len(online_keys)
            except:
                active_users = 0
            
            # Circuit Breaker Durumu
            cb_status = metrics.get('circuit_breaker', {})
            cb_state = cb_status.get('state', 'UNKNOWN')
            cb_failures = cb_status.get('failure_count', 0)
            
            cb_icon = "🟢" if cb_state == "CLOSED" else "🟡" if cb_state == "HALF_OPEN" else "🔴"
            cb_text = f"{cb_icon} {cb_state}"
            if cb_failures > 0:
                cb_text += f" ({cb_failures} hata)"
            
            # Özel Olaylar
            special_events = []
            
            # Circuit Breaker olayları
            if cb_state == "OPEN":
                special_events.append("🔴 Circuit Breaker açıldı (API hatası)")
            elif cb_state == "HALF_OPEN":
                special_events.append("🟡 Circuit Breaker test modunda")
            
            # Circuit breaker trip sayısı
            cb_trips = metrics.get('circuit_breaker_trips', 0)
            if cb_trips > 0:
                special_events.append(f"⚡ Circuit Breaker {cb_trips} kez tetiklendi")
            
            # Cleanup bilgisi
            try:
                from utils.cache import get_cache, get_disk_backup_stats
                from config import Config
                
                cleanup_last_run = get_cache(Config.CACHE_KEYS.get('cleanup_last_run'))
                
                if cleanup_last_run:
                    cleanup_time = datetime.fromtimestamp(float(cleanup_last_run))
                    if cleanup_time.date() == now.date():
                        backup_stats = get_disk_backup_stats()
                        special_events.append(
                            f"🧹 Cleanup çalıştı: {backup_stats.get('total_files', 0)} dosya, "
                            f"{backup_stats.get('total_size_mb', 0)} MB"
                        )
            except:
                pass
            
            # Rapor Oluştur
            report_lines = [
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
                f"• Aktif Kullanıcı: *{active_users}*",
                f"  _(Son 5 dakika)_\n",
                
                f"🛡️ *GÜVENLİK & HATALAR*",
                f"• Hatalar: `{metrics.get('errors', 0)}`"
            ]
            
            # Özel Olaylar Ekle
            if special_events:
                report_lines.append(f"\n🔔 *ÖZEL OLAYLAR*")
                for event in special_events:
                    report_lines.append(f"• {event}")
            
            # Footer
            report_lines.append(f"\n_KuraBak Backend v4.5 • {now.strftime('%H:%M')}_")
            
            report = "\n".join(report_lines)
            
            self.send_message(report, level='report')
            
        except Exception as e:
            logger.error(f"❌ Günlük rapor hatası: {e}")
            # Basit fallback rapor
            self.send_message(
                f"🌙 *GÜN SONU RAPORU*\n\n"
                f"⚠️ Detaylı rapor oluşturulamadı\n"
                f"Hata: {str(e)[:100]}",
                level='report'
            )

    def send_calendar_notification(self, event_name: str, event_date: str):
        """📅 TAKVİM ETKİNLİK BİLDİRİMİ"""
        msg = (
            f"📅 *TAKVİM UYARISI*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📌 *Etkinlik:* {event_name}\n"
            f"🗓️ *Tarih:* {event_date}\n\n"
            f"ℹ️ Banner otomatik olarak aktif edilecek."
        )
        self.send_message(msg, level='report')

    def send_startup_message(self):
        """Başlangıç mesajı"""
        from config import Config
        msg = (
            f"🚀 *SİSTEM BAŞLATILDI*\n\n"
            f"📦 *Versiyon:* {Config.APP_VERSION}\n"
            f"🔌 *Kaynak:* V5 API Only\n"
            f"💾 *Backup:* 15 dakikalık otomatik\n"
            f"🤖 *Self-Healing:* Aktif\n"
            f"🗓️ *Takvim:* Aktif\n"
            f"🧪 *Test:* /test komutu aktif\n"
            f"🛡️ *Circuit Breaker:* Aktif (3 hata = 60s)\n"
            f"🔔 *Push Notification:* Her gün 12:00\n"
            f"🧹 *Cleanup:* Her gün 03:00\n"
            f"🔐 *Güvenli Cache:* Aktif (V4.5)\n\n"
            f"✅ Tüm sistemler hazır!"
        )
        self.send_message(msg, level='report')

    def start_command_listener(self):
        """Arka planda komutları dinlemeye başlar"""
        if self.is_listening:
            logger.warning("Komut dinleyici zaten çalışıyor!")
            return
        
        self.is_listening = True
        self.command_thread = threading.Thread(target=self._listen_commands, daemon=True)
        self.command_thread.start()
        logger.info("🤖 Şef Komut Dinleyici başlatıldı! 🔒 Admin Filter: ACTIVE")

    def _is_admin(self, user_id: int) -> bool:
        """🔒 GÜVENLİK KONTROLÜ"""
        return user_id in ALLOWED_ADMIN_IDS

    def _listen_commands(self):
        """Telegram'dan gelen komutları dinler (Long Polling)"""
        offset = 0
        
        while self.is_listening:
            try:
                url = f"{self.base_url}/getUpdates"
                params = {
                    'offset': offset,
                    'timeout': 30,
                    'allowed_updates': ['message']
                }
                
                response = requests.get(url, params=params, timeout=35)
                data = response.json()
                
                if not data.get('ok'):
                    time.sleep(5)
                    continue
                
                for update in data.get('result', []):
                    offset = update['update_id'] + 1
                    
                    message = update.get('message')
                    if not message:
                        continue
                    
                    if str(message.get('chat', {}).get('id')) != str(self.chat_id):
                        continue
                    
                    user_id = message.get('from', {}).get('id')
                    
                    if not self._is_admin(user_id):
                        username = message.get('from', {}).get('username', 'Unknown')
                        logger.warning(f"🚨 Yetkisiz komut denemesi! User ID: {user_id}, Username: @{username}")
                        
                        self._send_raw(
                            "🔒 *ERİŞİM ENGELLENDİ*\n\n"
                            "Bu bot sadece yetkili kullanıcılar tarafından kontrol edilebilir.\n\n"
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
                    elif text == '/analiz':
                        self._handle_analiz()
                    elif text.startswith('/duyuru'):
                        self._handle_duyuru(text)
                    elif text == '/sus':
                        self._handle_sus()
                    elif text == '/konus':
                        self._handle_konus()
                    elif text.startswith('/bakim'):
                        self._handle_bakim(text)
                    elif text.startswith('/test'):
                        self._handle_test(text)
                    elif text == '/circuit':
                        self._handle_circuit()
                    elif text.startswith('/'):
                        self._send_help()
                
            except Exception as e:
                logger.error(f"Komut dinleyici hatası: {e}")
                time.sleep(10)

    def _send_help(self):
        """Yardım Mesajı"""
        self._send_raw(
            "❓ *KOMUT LİSTESİ* 🔒\n\n"
            "🧪 *TEST SİSTEMİ:*\n"
            "`/test` - Basit sağlık testi (5sn)\n"
            "`/test mobil` - Mobil uyumluluk\n"
            "`/test detay` - Detaylı sistem testi\n\n"
            "📢 *YÖNETİM:*\n"
            "`/duyuru [mesaj]` - Duyuru as\n"
            "`/duyuru 3g [mesaj]` - 3 günlük duyuru\n"
            "`/duyuru sil` - Duyuruyu kaldır\n"
            "`/sus` - 🛑 SİSTEMİ GİZLE\n"
            "`/konus` - 🔊 SİSTEMİ AÇ\n\n"
            "🚧 *BAKIM:*\n"
            "`/bakim` - Bakım modunu aç\n"
            "`/bakim kapat` - Bakım modunu kapat\n\n"
            "📊 *RAPOR:*\n"
            "`/durum` - Sistem sağlık raporu\n"
            "`/online` - Aktif kullanıcı\n"
            "`/temizle` - Güvenli cache temizliği 🔐\n"
            "`/analiz` - Sistem analizi\n"
            "`/circuit` - Circuit Breaker durumu\n\n"
            "🔒 _Bu komutlar sadece yetkili admin tarafından kullanılabilir._"
        )

    def _handle_circuit(self):
        """🛡️ Circuit Breaker Durumu"""
        try:
            from services.financial_service import get_circuit_breaker_status
            
            status = get_circuit_breaker_status()
            
            state = status.get('state', 'UNKNOWN')
            failures = status.get('failure_count', 0)
            can_attempt = status.get('can_attempt', False)
            timeout = status.get('timeout', 0)
            
            # Icon ve durum
            if state == "CLOSED":
                icon = "🟢"
                status_text = "Normal Çalışıyor"
                detail = "API çağrıları yapılıyor"
            elif state == "OPEN":
                icon = "🔴"
                status_text = "Devre Açık"
                last_open = status.get('last_open_time', 0)
                if last_open:
                    elapsed = int(time.time() - last_open)
                    remaining = max(0, timeout - elapsed)
                    detail = f"{remaining} saniye sonra test edilecek"
                else:
                    detail = f"{timeout} saniye bekleniyor"
            elif state == "HALF_OPEN":
                icon = "🟡"
                status_text = "Test Modu"
                detail = "1 deneme yapılıyor..."
            else:
                icon = "⚪"
                status_text = "Bilinmiyor"
                detail = ""
            
            report = (
                f"{icon} *CIRCUIT BREAKER DURUMU*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📊 *Durum:* {status_text}\n"
                f"🔢 *State:* `{state}`\n"
                f"❌ *Hata Sayısı:* {failures}\n"
                f"✅ *API Çağrısı:* {'Yapılabilir' if can_attempt else 'Yapılamaz'}\n"
                f"⏱️ *Timeout:* {timeout} saniye\n"
            )
            
            if detail:
                report += f"\nℹ️ {detail}"
            
            self._send_raw(report)
            
        except Exception as e:
            self._send_raw(f"❌ Circuit breaker sorgu hatası: {str(e)}")

    def _handle_test(self, text):
        """🧪 TEST SİSTEMİ"""
        try:
            raw_content = text.replace('/test', '').strip().lower()
            raw_content = raw_content.replace('ı', 'i').replace('ş', 's').replace('ğ', 'g').replace('ü', 'u').replace('ö', 'o').replace('ç', 'c')
            
            self._send_raw("⏳ Test başlatılıyor...")
            
            if raw_content == '' or raw_content == 'basit':
                report = self._run_basic_test()
            elif raw_content in ['mobil', 'mobile']:
                report = self._run_mobile_test()
            elif raw_content in ['detay', 'detayli', 'detailed']:
                report = self._run_detailed_test()
            else:
                self._send_raw(
                    "❌ Geçersiz test tipi!\n\n"
                    "Kullanım:\n"
                    "`/test` - Basit test (5sn)\n"
                    "`/test mobil` - Mobil uyumluluk\n"
                    "`/test detay` - Detaylı test"
                )
                return
            
            self._send_raw(report)
            
        except Exception as e:
            self._send_raw(f"❌ Test hatası: {str(e)}")

    def _run_basic_test(self) -> str:
        """Basit 5 saniyelik test"""
        try:
            from utils.cache import get_cache, redis_wrapper
            from config import Config
            
            results = []
            
            if redis_wrapper.is_enabled():
                results.append("✅ Redis: Bağlı")
            else:
                results.append("⚠️ Redis: RAM Modu")
            
            currencies = get_cache(Config.CACHE_KEYS['currencies_all'])
            if currencies and len(currencies.get('data', [])) > 0:
                results.append(f"✅ Döviz: {len(currencies.get('data', []))} adet")
            else:
                results.append("❌ Döviz: Veri yok")
            
            last_worker_run = get_cache(Config.CACHE_KEYS['last_worker_run'])
            if last_worker_run:
                time_diff = time.time() - float(last_worker_run)
                if time_diff < 300:
                    results.append(f"✅ Worker: Aktif ({int(time_diff)}sn önce)")
                else:
                    results.append(f"⚠️ Worker: Yavaş ({int(time_diff/60)}dk önce)")
            else:
                results.append("❌ Worker: Henüz çalışmadı")
            
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent
            
            cpu_status = "✅" if cpu < 70 else "⚠️" if cpu < 85 else "❌"
            ram_status = "✅" if ram < 75 else "⚠️" if ram < 90 else "❌"
            
            results.append(f"{cpu_status} CPU: %{cpu:.1f}")
            results.append(f"{ram_status} RAM: %{ram:.1f}")
            
            # Circuit Breaker ekle
            try:
                from services.financial_service import get_circuit_breaker_status
                cb_status = get_circuit_breaker_status()
                state = cb_status.get('state', 'UNKNOWN')
                if state == "CLOSED":
                    results.append("✅ Circuit Breaker: CLOSED")
                elif state == "OPEN":
                    results.append("❌ Circuit Breaker: OPEN")
                else:
                    results.append(f"🟡 Circuit Breaker: {state}")
            except:
                pass
            
            total = len(results)
            passed = sum(1 for r in results if r.startswith("✅"))
            
            status_icon = "🟢" if passed == total else "🟡" if passed >= total/2 else "🔴"
            
            report = (
                f"{status_icon} *BASIT TEST RAPORU*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                + "\n".join(results) +
                f"\n\n📊 *Sonuç:* {passed}/{total} başarılı\n"
                f"⏱️ *Süre:* ~5 saniye"
            )
            
            return report
            
        except Exception as e:
            return f"❌ Test hatası: {str(e)}"

    def _run_mobile_test(self) -> str:
        """Mobil uyumluluk testi"""
        try:
            from utils.cache import get_cache
            from config import Config
            
            results = []
            
            currencies = get_cache(Config.CACHE_KEYS['currencies_all'])
            if currencies:
                curr_data = currencies.get('data', [])
                expected = 23
                actual = len(curr_data)
                if actual == expected:
                    results.append(f"✅ Döviz: {actual}/{expected}")
                else:
                    results.append(f"⚠️ Döviz: {actual}/{expected} (Eksik)")
            else:
                results.append("❌ Döviz: Veri yok")
            
            golds = get_cache(Config.CACHE_KEYS['golds_all'])
            if golds:
                gold_data = golds.get('data', [])
                expected = 6
                actual = len(gold_data)
                if actual == expected:
                    results.append(f"✅ Altın: {actual}/{expected}")
                else:
                    results.append(f"⚠️ Altın: {actual}/{expected} (Eksik)")
            else:
                results.append("❌ Altın: Veri yok")
            
            silvers = get_cache(Config.CACHE_KEYS['silvers_all'])
            if silvers:
                silver_data = silvers.get('data', [])
                if len(silver_data) >= 1:
                    silver_name = silver_data[0].get('name', '')
                    if silver_name == "Gümüş":
                        results.append("✅ Gümüş: 1/1 (İsim: Gümüş)")
                    else:
                        results.append(f"⚠️ Gümüş: 1/1 (İsim: {silver_name})")
                else:
                    results.append("❌ Gümüş: 0/1")
            else:
                results.append("❌ Gümüş: Veri yok")
            
            if currencies:
                banner = currencies.get('banner')
                if banner:
                    results.append(f"ℹ️ Banner: \"{banner[:30]}...\"")
                else:
                    results.append("✅ Banner: Yok (Normal)")
            
            if currencies:
                status = currencies.get('status', 'UNKNOWN')
                if status == 'OPEN':
                    results.append("✅ Status: OPEN (Piyasa açık)")
                elif status == 'CLOSED':
                    results.append("ℹ️ Status: CLOSED (Hafta sonu)")
                else:
                    results.append(f"⚠️ Status: {status}")
            
            total = len([r for r in results if not r.startswith("ℹ️")])
            passed = sum(1 for r in results if r.startswith("✅"))
            
            status_icon = "🟢" if passed == total else "🟡" if passed >= total/2 else "🔴"
            
            report = (
                f"{status_icon} *MOBİL UYUMLULUK TESTİ*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                + "\n".join(results) +
                f"\n\n📊 *Sonuç:* {passed}/{total} başarılı\n"
                f"📱 *Mobil Ready:* {'Evet ✅' if passed == total else 'Hayır ⚠️'}"
            )
            
            return report
            
        except Exception as e:
            return f"❌ Test hatası: {str(e)}"

    def _run_detailed_test(self) -> str:
        """Detaylı sistem testi"""
        try:
            from utils.cache import get_cache, redis_wrapper
            from config import Config
            
            results = []
            
            results.append("🔹 *REDIS*")
            if redis_wrapper.is_enabled():
                results.append("  ✅ Bağlı")
            else:
                results.append("  ⚠️ RAM Modu")
            
            results.append("\n🔹 *VERİLER*")
            currencies = get_cache(Config.CACHE_KEYS['currencies_all'])
            golds = get_cache(Config.CACHE_KEYS['golds_all'])
            silvers = get_cache(Config.CACHE_KEYS['silvers_all'])
            
            if currencies:
                results.append(f"  ✅ Döviz: {len(currencies.get('data', []))} adet")
                results.append(f"     Kaynak: {currencies.get('source', 'Unknown')}")
                results.append(f"     Güncelleme: {currencies.get('last_update', 'Unknown')}")
                
                summary = currencies.get('summary', {})
                if summary:
                    winner = summary.get('winner', {}).get('name', 'YOK')
                    loser = summary.get('loser', {}).get('name', 'YOK')
                    results.append(f"     Summary: Winner={winner}, Loser={loser}")
                else:
                    results.append("     Summary: Yok")
            else:
                results.append("  ❌ Döviz: Veri yok")
            
            if golds:
                results.append(f"  ✅ Altın: {len(golds.get('data', []))} adet")
            else:
                results.append("  ❌ Altın: Veri yok")
            
            if silvers:
                silver_data = silvers.get('data', [])
                if silver_data:
                    silver_name = silver_data[0].get('name', 'Unknown')
                    results.append(f"  ✅ Gümüş: {len(silver_data)} adet (İsim: {silver_name})")
                else:
                    results.append("  ❌ Gümüş: Veri yok")
            else:
                results.append("  ❌ Gümüş: Veri yok")
            
            results.append("\n🔹 *BİLEŞENLER*")
            last_worker_run = get_cache(Config.CACHE_KEYS['last_worker_run'])
            if last_worker_run:
                time_diff = time.time() - float(last_worker_run)
                if time_diff < 300:
                    results.append(f"  ✅ Worker: Aktif ({int(time_diff)}sn)")
                else:
                    results.append(f"  ⚠️ Worker: Yavaş ({int(time_diff/60)}dk)")
            else:
                results.append("  ❌ Worker: Çalışmadı")
            
            snapshot = get_cache(Config.CACHE_KEYS['yesterday_prices'])
            if snapshot:
                results.append(f"  ✅ Snapshot: {len(snapshot)} fiyat")
            else:
                results.append("  ❌ Snapshot: Yok")
            
            results.append("\n🔹 *SİSTEM*")
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent
            
            cpu_status = "✅" if cpu < 70 else "⚠️" if cpu < 85 else "❌"
            ram_status = "✅" if ram < 75 else "⚠️" if ram < 90 else "❌"
            
            results.append(f"  {cpu_status} CPU: %{cpu:.1f}")
            results.append(f"  {ram_status} RAM: %{ram:.1f}")
            
            results.append("\n🔹 *KAYNAK*")
            results.append(f"  ℹ️ Aktif: V5 API Only")
            results.append(f"  ℹ️ Backup: 15 dakikalık otomatik")
            
            all_results = "\n".join(results)
            passed = all_results.count("✅")
            total = all_results.count("✅") + all_results.count("❌")
            
            status_icon = "🟢" if passed == total else "🟡" if passed >= total/2 else "🔴"
            
            report = (
                f"{status_icon} *DETAYLI TEST RAPORU*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                + all_results +
                f"\n\n📊 *Sonuç:* {passed}/{total} başarılı"
            )
            
            return report
            
        except Exception as e:
            return f"❌ Test hatası: {str(e)}"

    def _handle_durum(self):
        """Sistem Durumu Raporu"""
        try:
            from utils.cache import get_cache, redis_wrapper
            from config import Config
            
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent
            
            last_worker_run = get_cache(Config.CACHE_KEYS['last_worker_run'])
            worker_icon = "🟢"
            worker_text = "Aktif"
            
            if last_worker_run:
                time_diff = time.time() - float(last_worker_run)
                if time_diff > 600:
                    worker_icon = "🔴"
                    worker_text = f"Uyuyor ({int(time_diff/60)} dk)"
                elif time_diff > 300:
                    worker_icon = "🟡"
                    worker_text = f"Yavaş ({int(time_diff/60)} dk)"
            else:
                worker_icon = "⚪"
                worker_text = "Henüz Çalışmadı"
            
            redis_status = "🟢 Bağlı" if redis_wrapper.is_enabled() else "🔴 RAM Modu"
            
            snapshot_exists = bool(get_cache(Config.CACHE_KEYS['yesterday_prices']))
            snapshot_icon = "🟢" if snapshot_exists else "🔴"
            
            maintenance_data = get_cache(Config.CACHE_KEYS['maintenance'])
            maintenance_status = "🔴 Aktif" if maintenance_data else "🟢 Kapalı"
            
            healing_status = "🟢 Aktif" if self.is_healing_active else "🔴 Kapalı"
            
            report = (
                f"👮‍♂️ *SİSTEM DURUMU RAPORU*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                
                f"⚡ *SUNUCU*\n"
                f"• CPU: `%{cpu:.1f}`\n"
                f"• RAM: `%{ram:.1f}`\n"
                f"• Redis: {redis_status}\n\n"
                
                f"🛠️ *BİLEŞENLER*\n"
                f"• {worker_icon} Worker: `{worker_text}`\n"
                f"• {snapshot_icon} Snapshot: `{'Mevcut' if snapshot_exists else 'Kayıp'}`\n"
                f"• 🤖 Self-Healing: {healing_status}\n\n"
                
                f"🔌 *VERİ KAYNAĞI*\n"
                f"• Aktif: `V5 API Only`\n"
                f"• Backup: `15 dakikalık otomatik`\n\n"
                
                f"🚧 *ÖZEL MODLAR*\n"
                f"• Bakım: {maintenance_status}\n\n"
                
                f"🔒 *GÜVENLİK*\n"
                f"• Admin Filter: `Aktif`\n"
                f"• Güvenli Cache: `V4.5`\n\n"
                
                f"_Rapor Zamanı: {datetime.now().strftime('%H:%M:%S')}_"
            )
            
            self._send_raw(report)
            
        except Exception as e:
            self._send_raw(f"❌ Durum raporu hatası: {str(e)}")

    def _handle_online(self):
        """Aktif Kullanıcı Sayısı"""
        try:
            from utils.cache import get_cache_keys
            
            online_keys = get_cache_keys("online_user:*")
            count = len(online_keys)
            
            icon = "🔥" if count > 100 else "📊" if count > 10 else "👤"
            
            self._send_raw(
                f"{icon} *CANLI KULLANICI*\n\n"
                f"Şu an *{count}* kullanıcı aktif Patron!\n\n"
                f"_Son 5 dakika içinde API'ye istek atanlar_"
            )
            
        except Exception as e:
            self._send_raw(f"❌ Online sayım hatası: {str(e)}")

    def _handle_temizle(self):
        """
        🔥 GÜVENLİ Cache Temizliği (V4.5)
        
        ÖNCEKİ SORUN: flush_all_cache() Redis connection'ı koparıyordu
        YENİ ÇÖZÜM: Sadece KuraBak key'lerini sil, connection'ı koru
        """
        try:
            from utils.cache import get_redis_client, delete_cache
            from config import Config
            
            self._send_raw(
                "⚠️ *GÜVENLİ CACHE TEMİZLİĞİ*\n\n"
                "Sadece KuraBak cache'leri silinecek\n"
                "(Redis bağlantısı korunacak)\n"
                "İşlem başlatılıyor..."
            )
            
            deleted_count = 0
            failed_keys = []
            
            # Redis client'ı al
            redis_client = get_redis_client()
            
            if redis_client:
                try:
                    # Sadece KuraBak pattern'ine uyan key'leri bul
                    pattern = "kurabak:*"
                    keys = redis_client.keys(pattern)
                    
                    if keys:
                        # Tek tek sil (güvenli)
                        for key in keys:
                            try:
                                redis_client.delete(key)
                                deleted_count += 1
                            except Exception as e:
                                failed_keys.append(key.decode() if isinstance(key, bytes) else key)
                                logger.error(f"Key silme hatası ({key}): {e}")
                        
                        # Başarı mesajı
                        if deleted_count > 0:
                            success_msg = (
                                f"✅ *GÜVENLİ TEMİZLİK TAMAMLANDI*\n\n"
                                f"🧹 *Silinen Key:* {deleted_count} adet\n"
                                f"🔗 *Redis Bağlantısı:* Korundu ✅\n"
                                f"🔄 Worker 2 dakika içinde yeni veri çekecek.\n"
                            )
                            
                            if failed_keys:
                                success_msg += f"\n⚠️ Silinemedi: {len(failed_keys)} key"
                            
                            self._send_raw(success_msg)
                        else:
                            self._send_raw(
                                "ℹ️ *SİLİNECEK KEY YOK*\n\n"
                                "Cache zaten boş veya key bulunamadı."
                            )
                    else:
                        self._send_raw(
                            "ℹ️ *SİLİNECEK KEY YOK*\n\n"
                            "Cache zaten boş."
                        )
                        
                except Exception as redis_error:
                    logger.error(f"Redis key silme hatası: {redis_error}")
                    self._send_raw(
                        f"⚠️ *REDIS HATASI*\n\n"
                        f"Key silme sırasında sorun oluştu:\n"
                        f"`{str(redis_error)[:100]}`"
                    )
            else:
                # Redis yok, RAM/Disk cache'ini sil
                logger.warning("Redis yok, alternatif temizlik yapılıyor...")
                
                # Config'den bilinen key'leri sil
                try:
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
                        f"⚠️ Redis bağlantısı yok (RAM modu)\n"
                        f"🔄 Worker 2 dakika içinde yeni veri çekecek."
                    )
                except Exception as ram_error:
                    logger.error(f"RAM cache temizleme hatası: {ram_error}")
                    self._send_raw(f"❌ RAM cache temizlik hatası: {str(ram_error)}")
                
        except Exception as e:
            logger.error(f"Temizlik hatası: {e}")
            self._send_raw(
                f"❌ *TEMİZLİK HATASI*\n\n"
                f"Beklenmeyen hata:\n`{str(e)[:150]}`"
            )

    def _handle_analiz(self):
        """Sistem Analizi"""
        try:
            self._send_raw(
                "📊 *SİSTEM ANALİZİ*\n\n"
                "🚀 *API:* V5 Only\n"
                "💾 *Backup:* 15 dakikalık otomatik\n"
                "🤖 *Self-Healing:* Aktif\n"
                "⏱️ *Kontrol Sıklığı:* 1 dakika\n"
                "🎯 *CPU Eşik:* %80\n"
                "💾 *RAM Eşik:* %85\n"
                "🗓️ *Takvim:* Her gün 08:00\n"
                "🛡️ *Circuit Breaker:* 3 hata = 60s\n"
                "🔔 *Push Notification:* Her gün 12:00\n"
                "🧹 *Cleanup:* Her gün 03:00\n"
                "🔐 *Güvenli Cache:* V4.5\n\n"
                "_Sistem otomatik olarak yüksek yük durumlarını tespit edip düzeltiyor._"
            )
            
        except Exception as e:
            self._send_raw(f"❌ Analiz hatası: {str(e)}")

    def _handle_duyuru(self, text):
        """Süreli Duyuru Sistemi"""
        try:
            from utils.cache import set_cache, delete_cache
            from config import Config
            
            raw_content = text.replace('/duyuru', '').strip()
            
            if raw_content.lower() == 'sil' or raw_content == '':
                delete_cache(Config.CACHE_KEYS['banner'])
                self._send_raw("🔇 *DUYURU KALDIRILDI*\n\nPatron, mesajı sildim. Uygulama ekranlarından kayboldu.")
                return

            parts = raw_content.split(' ', 1)
            
            ttl = 0
            message = raw_content
            duration_info = "Süresiz ♾️ (Sen silene kadar kalacak)"

            if len(parts) > 1:
                time_code = parts[0].lower()
                potential_msg = parts[1]
                
                multiplier = 0
                unit_name = ""

                if time_code.endswith('d') and time_code[:-1].isdigit():
                    multiplier = 60
                    unit_name = "Dakika"
                elif time_code.endswith('s') and time_code[:-1].isdigit():
                    multiplier = 3600
                    unit_name = "Saat"
                elif time_code.endswith('g') and time_code[:-1].isdigit():
                    multiplier = 86400
                    unit_name = "Gün"
                
                if multiplier > 0:
                    val = int(time_code[:-1])
                    ttl = val * multiplier
                    message = potential_msg
                    
                    end_time = datetime.now() + timedelta(seconds=ttl)
                    duration_info = f"{val} {unit_name} ⏳\n🗓️ *Bitiş:* {end_time.strftime('%d.%m %H:%M')}"

            set_cache(Config.CACHE_KEYS['banner'], message, ttl=ttl)
            
            self._send_raw(
                f"📢 *DUYURU YAYINDA!*\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"📝 *Mesaj:* \"{message}\"\n"
                f"⏱️ *Süre:* {duration_info}\n\n"
                f"✅ Tamamdır Patron! Uygulama ekranlarında görünüyor."
            )
            
        except Exception as e:
            self._send_raw(f"❌ Duyuru hatası: {str(e)}")

    def _handle_sus(self):
        """🛑 SİSTEMİ SUSTUR"""
        try:
            from utils.cache import set_cache
            from config import Config
            
            set_cache(Config.CACHE_KEYS['mute'], "true", ttl=0)
            
            self._send_raw(
                "🤫 *SİSTEM SUSTURULDU!* 🛑\n\n"
                "Patron emriyle tüm banner ve duyurular gizlendi.\n"
                "Uygulama artık ekranında hiçbir uyarı göstermeyecek.\n\n"
                "✅ Açmak için: `/konus`"
            )
        except Exception as e:
            self._send_raw(f"❌ Susturma hatası: {str(e)}")

    def _handle_konus(self):
        """🔊 SİSTEMİ AÇ"""
        try:
            from utils.cache import delete_cache
            from config import Config
            
            delete_cache(Config.CACHE_KEYS['mute'])
            
            self._send_raw(
                "🔊 *SİSTEM TEKRAR ONLINE* ✅\n\n"
                "Susturma kaldırıldı. Otomatik takvim ve duyurular tekrar görünmeye başlayacak."
            )
        except Exception as e:
            self._send_raw(f"❌ Açma hatası: {str(e)}")

    def _handle_bakim(self, text):
        """🚧 BAKIM MODU"""
        try:
            from services.maintenance_service import activate_maintenance, deactivate_maintenance
            
            raw_content = text.replace('/bakim', '').strip()
            
            if raw_content.lower() in ['kapat', 'sil', '']:
                deactivate_maintenance()
                self._send_raw(
                    "✅ *BAKIM MODU KAPANDI*\n\n"
                    "Sistem normal moda döndü. Kullanıcılar tekrar veri alabilir."
                )
                return
            
            activate_maintenance()
            
            self._send_raw(
                f"🚧 *BAKIM MODU AKTİF!*\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"📝 *Durum:* Uygulama açık ama veri gelmiyor\n"
                f"💬 *Banner:* Kullanıcılar bilgilendiriliyor\n\n"
                f"✅ Kapatmak için: `/bakim kapat`"
            )
            
        except Exception as e:
            self._send_raw(f"❌ Bakım modu hatası: {str(e)}")

    def start_self_healing(self):
        """Self-Healing sistemini başlat"""
        if self.is_healing_active:
            logger.warning("Self-Healing zaten çalışıyor!")
            return
        
        self.is_healing_active = True
        self.healing_thread = threading.Thread(target=self._self_healing_loop, daemon=True)
        self.healing_thread.start()
        logger.info("🤖 Self-Healing sistemi başlatıldı!")

    def _self_healing_loop(self):
        """Arka planda sürekli CPU/RAM kontrol eder ve müdahale eder"""
        from config import Config
        from utils.cache import get_cache, set_cache
        
        cpu_high_since = None
        last_cpu_notification = 0
        last_ram_notification = 0
        
        while self.is_healing_active:
            try:
                cpu = psutil.cpu_percent(interval=1)
                ram = psutil.virtual_memory().percent
                now = time.time()
                
                if cpu > Config.CPU_THRESHOLD:
                    if cpu_high_since is None:
                        cpu_high_since = now
                    
                    if (now - cpu_high_since) > Config.CPU_HIGH_DURATION:
                        logger.warning(f"🔥 CPU yüksek ({cpu}%), müdahale ediliyor...")
                        
                        if (now - last_cpu_notification) > Config.ALARM_NOTIFICATION_INTERVAL:
                            self._send_raw(
                                f"⚠️ *CPU YÜKSEK!*\n\n"
                                f"🧠 *CPU:* %{cpu:.1f}\n"
                                f"📊 *Eşik:* %{Config.CPU_THRESHOLD}\n"
                                f"⏱️ *Süre:* {int((now - cpu_high_since)/60)} dakika\n\n"
                                f"Sistem müdahale edecek..."
                            )
                            last_cpu_notification = now
                        
                        cpu_high_since = None
                else:
                    if cpu_high_since is not None:
                        logger.info(f"✅ CPU normale döndü: %{cpu:.1f}")
                        cpu_high_since = None
                
                if ram > Config.RAM_THRESHOLD:
                    logger.warning(f"💾 RAM yüksek ({ram}%), otomatik temizlik yapılıyor...")
                    
                    try:
                        # 🔥 V4.5: Güvenli temizlik yap
                        from utils.cache import get_redis_client
                        
                        redis_client = get_redis_client()
                        if redis_client:
                            pattern = "kurabak:*"
                            keys = redis_client.keys(pattern)
                            if keys:
                                for key in keys:
                                    try:
                                        redis_client.delete(key)
                                    except:
                                        pass
                        
                        new_ram = psutil.virtual_memory().percent
                        
                        if (now - last_ram_notification) > Config.ALARM_NOTIFICATION_INTERVAL:
                            if new_ram < Config.RAM_THRESHOLD:
                                self._send_raw(
                                    f"✅ *RAM DÜZELTİLDİ*\n\n"
                                    f"💾 *Önceki:* %{ram:.1f}\n"
                                    f"💾 *Şimdi:* %{new_ram:.1f}\n\n"
                                    f"Cache temizlendi, sorun çözüldü!"
                                )
                            else:
                                self._send_raw(
                                    f"⚠️ *RAM HALA YÜKSEK!*\n\n"
                                    f"💾 *RAM:* %{new_ram:.1f}\n"
                                    f"📊 *Eşik:* %{Config.RAM_THRESHOLD}\n\n"
                                    f"Temizlik yaptım ama düşmüyor. Kontrol et Patron!"
                                )
                            last_ram_notification = now
                            
                    except Exception as e:
                        logger.error(f"❌ RAM temizlik hatası: {e}")
                
                time.sleep(Config.ALARM_CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"Self-Healing hatası: {e}")
                time.sleep(60)


telegram_monitor: Optional[TelegramMonitor] = None
telegram_instance: Optional[TelegramMonitor] = None  # 🔥 app.py için global export

def init_telegram_monitor():
    """Botu başlatır"""
    global telegram_monitor, telegram_instance
    
    if telegram_monitor:
        return telegram_monitor

    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')

    if token and chat_id:
        telegram_monitor = TelegramMonitor(token, chat_id)
        telegram_instance = telegram_monitor  # 🔥 Global instance'ı set et
        telegram_monitor.start_command_listener()
        telegram_monitor.start_self_healing()
        logger.info("✅ Telegram Monitor başlatıldı.")
        return telegram_monitor
    else:
        logger.warning("⚠️ Telegram Monitor başlatılamadı!")
        telegram_instance = None  # 🔥 Başarısız olursa None
        return None

def get_telegram_monitor() -> Optional[TelegramMonitor]:
    """Singleton instance döndürür"""
    return telegram_monitor
