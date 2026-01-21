"""
Telegram Monitor - ŞEF KOMUTA MERKEZİ + BAKIM + ALARM + RAPOR SİSTEMİ 🤖
=======================================================
✅ KOMUTLAR: /durum, /online, /temizle, /analiz, /duyuru, /sus, /konus
✅ YENİ: /bakim, /alarm, /rapor
✅ ANTI-SPAM: Gün içi gereksiz bildirimleri engeller
✅ MODERN RAPOR: Gece raporu için özel "Şekilli" tasarım
✅ CRITICAL ONLY: Sadece sistem çökerse veya rapor zamanıysa yazar
✅ THREAD-SAFE: Arka planda sessizce çalışır
✅ DUYURU SİSTEMİ: Süreli/Süresiz banner yönetimi
✅ DEATH STAR MODU: /sus ile sistemi tamamen gizle, /konus ile aç
✅ BAKIM MODU: Senaryo A (Tam Engel) + Senaryo B (Kısıtlı Kullanım)
✅ AKILLI ALARM: CPU/RAM izleme
✅ HAFTALIK RAPOR: Detaylı performans özeti
✅ 🔒 ADMİN GÜVENLİĞİ: Sadece yetkili Telegram ID komut gönderebilir (7101853980)
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

# ======================================
# 🔒 GÜVENLİK: YETKİLİ ADMİN ID'LERİ
# ======================================
ALLOWED_ADMIN_IDS = [7101853980]  # Sadece senin Telegram ID'n

# ======================================
# TELEGRAM MONITOR (RAPOR + KOMUT)
# ======================================

class TelegramMonitor:
    """
    Çift Modlu Telegram Bot:
    1. RAPOR MODU: Sessiz bildirimler, günlük raporlar
    2. KOMUT MODU: Senin komutlarını dinler ve cevaplar
    3. BAKIM MODU: Sistem bakım yönetimi
    4. ALARM SİSTEMİ: CPU/RAM izleme
    5. HAFTALIK RAPOR: Performans özeti
    6. 🔒 ADMİN FİLTRESİ: Sadece yetkili kullanıcılar komut gönderebilir
    """
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self._lock = threading.Lock()
        
        # Spam Koruması: Aynı hatayı 30 dakika içinde tekrar atmasın
        self.last_critical_alert = datetime.min
        
        # Komut Dinleyici Thread
        self.command_thread = None
        self.is_listening = False
        
        # Alarm Thread
        self.alarm_thread = None
        self.is_alarm_active = False

    # ==========================================
    # BÖLÜM 1: RAPOR SİSTEMİ (Mevcut Kod)
    # ==========================================

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
        # 1. Önemsiz mesajları filtrele (Kullanıcı isteği: Sessizlik)
        if level in ['info', 'success', 'warning']:
            # Sadece log'a yaz, Telegram'a atma
            logger.info(f"Telegram (Sessiz): {text}")
            return True

        # 2. Kritik Hata Kontrolü (Spam Korumalı)
        if level == 'critical':
            with self._lock:
                now = datetime.now()
                # 30 dakikada bir sadece 1 kritik hata at
                if (now - self.last_critical_alert) < timedelta(minutes=30):
                    logger.warning("Telegram: Kritik hata spam korumasına takıldı.")
                    return False
                self.last_critical_alert = now
            
            # Kritik Mesaj Tasarımı
            alert_msg = (
                f"🚨 *KRİTİK SİSTEM UYARISI* 🚨\n\n"
                f"{text}\n\n"
                f"⏳ _Zaman: {datetime.now().strftime('%H:%M:%S')}_"
            )
            threading.Thread(target=self._send_raw, args=(alert_msg,)).start()
            return True

        # 3. Günlük Rapor (Report) - Doğrudan gönder
        if level == 'report':
            threading.Thread(target=self._send_raw, args=(text,)).start()
            return True

        return False

    def send_daily_report(self, metrics: Dict[str, Any]):
        """
        🌙 GÜN SONU MODERN RAPORU
        Şekilli şukullu, okunaklı ve özet.
        """
        now = datetime.now()
        date_str = now.strftime("%d.%m.%Y")
        
        # Başarı oranı hesapla
        total = metrics.get('v5', 0) + metrics.get('v4', 0) + metrics.get('v3', 0) + metrics.get('backup', 0)
        success_rate = 100
        if total > 0:
            success_rate = ((total - metrics.get('errors', 0)) / total) * 100

        # İkon Seçimi
        status_icon = "🟢" if success_rate > 95 else "🟡" if success_rate > 80 else "🔴"
        
        report = (
            f"🌙 *GÜN SONU RAPORU* | {date_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            
            f"📊 *GENEL DURUM*\n"
            f"• Durum: {status_icon} *{'Mükemmel' if success_rate > 95 else 'Stabil'}*\n"
            f"• Başarı Oranı: *%{success_rate:.1f}*\n"
            f"• Toplam İşlem: *{total}*\n\n"
            
            f"🔌 *KAYNAK KULLANIMI*\n"
            f"• 🚀 V5 (Hızlı): `{metrics.get('v5', 0)}`\n"
            f"• 🛡️ V4 (Yedek): `{metrics.get('v4', 0)}`\n"
            f"• 📦 Backup: `{metrics.get('backup', 0)}`\n\n"
            
            f"🛡️ *GÜVENLİK & HATALAR*\n"
            f"• Hatalar: `{metrics.get('errors', 0)}`\n"
            f"• Sigorta (CB): `Kapalı (Güvenli)`\n\n"
            
            f"_KuraBak Backend v2.0 • {now.strftime('%H:%M')}_"
        )
        
        # Raporu gönder (level='report' olduğu için filtrelenmez)
        self.send_message(report, level='report')

    # ==========================================
    # BÖLÜM 2: KOMUT SİSTEMİ (🔒 GÜVENLİK EKLENDİ)
    # ==========================================

    def start_command_listener(self):
        """
        Arka planda komutları dinlemeye başlar
        /durum, /online, /temizle, /analiz, /duyuru, /sus, /konus
        /bakim, /alarm, /rapor
        🔒 Sadece yetkili admin'lerden komut kabul eder
        """
        if self.is_listening:
            logger.warning("Komut dinleyici zaten çalışıyor!")
            return
        
        self.is_listening = True
        self.command_thread = threading.Thread(target=self._listen_commands, daemon=True)
        self.command_thread.start()
        logger.info("🤖 Şef Komut Dinleyici başlatıldı! 🔒 Admin Filter: ACTIVE")

    def _is_admin(self, user_id: int) -> bool:
        """
        🔒 GÜVENLİK KONTROLÜ
        Sadece ALLOWED_ADMIN_IDS listesindeki kullanıcılar True döner
        """
        return user_id in ALLOWED_ADMIN_IDS

    def _listen_commands(self):
        """
        Telegram'dan gelen komutları dinler (Long Polling)
        🔒 YENİ: Sadece yetkili admin'lerin komutlarını işler
        """
        offset = 0
        
        while self.is_listening:
            try:
                # Telegram getUpdates API
                url = f"{self.base_url}/getUpdates"
                params = {
                    'offset': offset,
                    'timeout': 30,  # 30 saniye bekle
                    'allowed_updates': ['message']
                }
                
                response = requests.get(url, params=params, timeout=35)
                data = response.json()
                
                if not data.get('ok'):
                    time.sleep(5)
                    continue
                
                # Gelen mesajları işle
                for update in data.get('result', []):
                    offset = update['update_id'] + 1
                    
                    message = update.get('message')
                    if not message:
                        continue
                    
                    # 🔒 GÜVENLİK 1: Sadece yetkili chat'ten gelen mesajları al
                    if str(message.get('chat', {}).get('id')) != str(self.chat_id):
                        continue
                    
                    # 🔒 GÜVENLİK 2: Kullanıcı ID'sini kontrol et
                    user_id = message.get('from', {}).get('id')
                    
                    if not self._is_admin(user_id):
                        # Yetkisiz erişim denemesi logla
                        username = message.get('from', {}).get('username', 'Unknown')
                        logger.warning(f"🚨 Yetkisiz komut denemesi! User ID: {user_id}, Username: @{username}")
                        
                        # Kullanıcıya bilgi ver
                        self._send_raw(
                            "🔒 *ERİŞİM ENGELLENDİ*\n\n"
                            "Bu bot sadece yetkili kullanıcılar tarafından kontrol edilebilir.\n\n"
                            "⚠️ Bu deneme kaydedildi."
                        )
                        continue
                    
                    # ✅ Yetkili kullanıcı - Komutları işle
                    text = message.get('text', '').strip()
                    
                    # Komutları işle
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
                    elif text.startswith('/alarm'):
                        self._handle_alarm(text)
                    elif text.startswith('/rapor'):
                        self._handle_rapor(text)
                    elif text.startswith('/'):
                        self._send_help()
                
            except Exception as e:
                logger.error(f"Komut dinleyici hatası: {e}")
                time.sleep(10)  # Hata durumunda bekle

    def _send_help(self):
        """Yardım Mesajı"""
        self._send_raw(
            "❓ *KOMUT LİSTESİ* 🔒\n\n"
            "📢 *YÖNETİM:*\n"
            "`/duyuru [mesaj]` - Duyuru as\n"
            "`/duyuru 3g [mesaj]` - 3 günlük duyuru\n"
            "`/duyuru sil` - Duyuruyu kaldır\n"
            "`/sus` - 🛑 SİSTEMİ GİZLE\n"
            "`/konus` - 🔊 SİSTEMİ AÇ\n\n"
            "🚧 *BAKIM:*\n"
            "`/bakim 30` - 30 dk Senaryo B (Veri yok)\n"
            "`/bakim 30 tam` - 30 dk Senaryo A (Tam kilit)\n"
            "`/bakim sil` - Bakımı kaldır\n\n"
            "🚨 *ALARM:*\n"
            "`/alarm cpu 80` - CPU %80 uyarısı\n"
            "`/alarm ram 85` - RAM %85 uyarısı\n"
            "`/alarm sil` - Alarmı kapat\n\n"
            "📊 *RAPOR:*\n"
            "`/durum` - Sistem sağlık raporu\n"
            "`/online` - Aktif kullanıcı\n"
            "`/temizle` - Cache temizliği\n"
            "`/analiz` - Versiyon analizi\n"
            "`/rapor detay` - 7 günlük özet\n\n"
            "🔒 _Bu komutlar sadece yetkili admin tarafından kullanılabilir._"
        )

    def _handle_durum(self):
        """Sistem Durumu Raporu"""
        try:
            from utils.cache import get_cache, redis_wrapper
            
            # CPU & RAM
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent
            
            # Worker durumu
            last_worker_run = get_cache("kurabak:last_worker_run")
            worker_icon = "🟢"
            worker_text = "Aktif"
            
            if last_worker_run:
                time_diff = time.time() - float(last_worker_run)
                if time_diff > 600:  # 10 dakika
                    worker_icon = "🔴"
                    worker_text = f"Uyuyor ({int(time_diff/60)} dk)"
                elif time_diff > 300:  # 5 dakika
                    worker_icon = "🟡"
                    worker_text = f"Yavaş ({int(time_diff/60)} dk)"
            else:
                worker_icon = "⚪"
                worker_text = "Henüz Çalışmadı"
            
            # Redis durumu
            redis_status = "🟢 Bağlı" if redis_wrapper.is_enabled() else "🔴 RAM Modu"
            
            # Snapshot durumu
            snapshot_exists = bool(get_cache("kurabak:yesterday_prices"))
            snapshot_icon = "🟢" if snapshot_exists else "🔴"
            
            # Bakım durumu
            maintenance_data = get_cache("system_maintenance")
            maintenance_status = "🔴 Aktif" if maintenance_data else "🟢 Kapalı"
            
            # Alarm durumu
            alarm_data = get_cache("system_alarm")
            alarm_status = "🔔 Aktif" if alarm_data else "🔕 Kapalı"
            
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
                f"• 🟢 Scheduler: `Aktif`\n\n"
                
                f"🚧 *ÖZEL MODLAR*\n"
                f"• Bakım: {maintenance_status}\n"
                f"• Alarm: {alarm_status}\n\n"
                
                f"🔒 *GÜVENLİK*\n"
                f"• Admin Filter: `Aktif`\n"
                f"• Rate Limiting: `60/dakika`\n\n"
                
                f"_Rapor Zamanı: {datetime.now().strftime('%H:%M:%S')}_"
            )
            
            self._send_raw(report)
            
        except Exception as e:
            self._send_raw(f"❌ Durum raporu hatası: {str(e)}")

    def _handle_online(self):
        """Aktif Kullanıcı Sayısı"""
        try:
            from utils.cache import get_cache_keys
            
            # "online_user:" ile başlayan key'leri say
            online_keys = get_cache_keys("online_user:*")
            count = len(online_keys)
            
            # İkon seç
            icon = "🔥" if count > 100 else "📊" if count > 10 else "👤"
            
            self._send_raw(
                f"{icon} *CANLI KULLANICI*\n\n"
                f"Şu an *{count}* kullanıcı aktif Patron!\n\n"
                f"_Son 5 dakika içinde API'ye istek atanlar_"
            )
            
        except Exception as e:
            self._send_raw(f"❌ Online sayım hatası: {str(e)}")

    def _handle_temizle(self):
        """Redis Cache Temizliği"""
        try:
            from utils.cache import flush_all_cache
            
            # Onay mesajı gönder
            self._send_raw(
                "⚠️ *CACHE TEMİZLİĞİ*\n\n"
                "Tüm Redis verileri silinecek!\n"
                "İşlem başlatılıyor..."
            )
            
            # Temizle
            success = flush_all_cache()
            
            if success:
                self._send_raw(
                    "✅ *TEMİZLİK TAMAMLANDI*\n\n"
                    "🧹 Redis tamamen temizlendi!\n"
                    "🔄 Worker 2 dakika içinde yeni veri çekecek."
                )
            else:
                self._send_raw("❌ Temizlik sırasında hata oluştu!")
                
        except Exception as e:
            self._send_raw(f"❌ Temizlik hatası: {str(e)}")

    def _handle_analiz(self):
        """Kullanıcı Versiyon Analizi"""
        try:
            # NOT: Bu özellik için veritabanı gerekli
            # Şu an sadece placeholder
            self._send_raw(
                "📊 *KULLANICI ANALİZİ*\n\n"
                "⚠️ Bu özellik henüz aktif değil.\n"
                "Veritabanı bağlantısı gerekiyor.\n\n"
                "_Yakında eklenecek..._"
            )
            
        except Exception as e:
            self._send_raw(f"❌ Analiz hatası: {str(e)}")

    def _handle_duyuru(self, text):
        """
        🎭 KUKLACI MODU 2.0: Süreli Duyuru Sistemi ⏱️
        Kullanım:
        1. /duyuru [mesaj] -> Süresiz (Sen silene kadar)
        2. /duyuru 30d [mesaj] -> 30 Dakika kalır
        3. /duyuru 5s [mesaj] -> 5 Saat kalır
        4. /duyuru 3g [mesaj] -> 3 Gün kalır
        5. /duyuru sil -> Anında siler
        """
        try:
            from utils.cache import set_cache, delete_cache
            
            # 1. Komutu temizle
            raw_content = text.replace('/duyuru', '').strip()
            
            # 2. Silme Komutu mu?
            if raw_content.lower() == 'sil' or raw_content == '':
                delete_cache("system_banner")
                self._send_raw("🔇 *DUYURU KALDIRILDI* \n\nPatron, mesajı sildim. Uygulama ekranlarından kayboldu.")
                return

            # 3. Süre Analizi (Akıllı Parser)
            parts = raw_content.split(' ', 1)
            
            ttl = 0  # Varsayılan: Süresiz (0)
            message = raw_content
            duration_info = "Süresiz ♾️ (Sen silene kadar kalacak)"

            # Eğer ilk kelime bir süre koduysa (Örn: 30d, 2s, 4g)
            if len(parts) > 1:
                time_code = parts[0].lower()
                potential_msg = parts[1]
                
                multiplier = 0
                unit_name = ""

                if time_code.endswith('d') and time_code[:-1].isdigit(): # Dakika
                    multiplier = 60
                    unit_name = "Dakika"
                elif time_code.endswith('s') and time_code[:-1].isdigit(): # Saat
                    multiplier = 3600
                    unit_name = "Saat"
                elif time_code.endswith('g') and time_code[:-1].isdigit(): # Gün
                    multiplier = 86400
                    unit_name = "Gün"
                
                # Eğer geçerli bir süre bulduysak
                if multiplier > 0:
                    val = int(time_code[:-1])
                    ttl = val * multiplier
                    message = potential_msg # Mesajdan süreyi çıkart
                    
                    # Bitiş tarihini hesapla
                    end_time = datetime.now() + timedelta(seconds=ttl)
                    duration_info = f"{val} {unit_name} ⏳\n🗓️ *Bitiş:* {end_time.strftime('%d.%m %H:%M')}"

            # 4. Redis'e Kaydet (Süreli veya Süresiz)
            set_cache("system_banner", message, ttl=ttl)
            
            self._send_raw(
                f"📢 *DUYURU YAYINDA!* \n"
                f"━━━━━━━━━━━━━━━━\n"
                f"📝 *Mesaj:* \"{message}\"\n"
                f"⏱️ *Süre:* {duration_info}\n\n"
                f"✅ Tamamdır Patron! Uygulama ekranlarında görünüyor."
            )
            
        except Exception as e:
            self._send_raw(f"❌ Duyuru hatası: {str(e)}")

    def _handle_sus(self):
        """🛑 ACİL DURUM: Sistemi Komple Susturur"""
        try:
            from utils.cache import set_cache
            set_cache("system_mute", "true", ttl=0)
            
            self._send_raw(
                "🤫 *SİSTEM SUSTURULDU!* 🛑\n\n"
                "Patron emriyle tüm banner ve duyurular gizlendi.\n"
                "Uygulama artık ekranında hiçbir uyarı göstermeyecek.\n\n"
                "✅ Açmak için: `/konus`"
            )
        except Exception as e:
            self._send_raw(f"❌ Susturma hatası: {str(e)}")

    def _handle_konus(self):
        """🔊 SİSTEMİ AÇ: Normal Akışa Dön"""
        try:
            from utils.cache import delete_cache
            delete_cache("system_mute")
            
            self._send_raw(
                "🔊 *SİSTEM TEKRAR ONLINE* ✅\n\n"
                "Susturma kaldırıldı. Otomatik takvim ve duyurular tekrar görünmeye başlayacak."
            )
        except Exception as e:
            self._send_raw(f"❌ Açma hatası: {str(e)}")

    # ==========================================
    # BÖLÜM 3: BAKIM MODU
    # ==========================================

    def _handle_bakim(self, text):
        """
        🚧 BAKIM MODU SİSTEMİ
        Kullanım:
        1. /bakim 30 -> 30 dakika Senaryo B (Veri yok, kullanıcı kullanabilir)
        2. /bakim 30 tam -> 30 dakika Senaryo A (Tam kilit, hiçbir şey kullanılamaz)
        3. /bakim sil -> Bakımı kaldır
        """
        try:
            from utils.cache import set_cache, delete_cache
            
            # Komutu temizle
            raw_content = text.replace('/bakim', '').strip()
            
            # Silme komutu
            if raw_content.lower() == 'sil' or raw_content == '':
                delete_cache("system_maintenance")
                self._send_raw(
                    "✅ *BAKIM MODU KALDIRILDI*\n\n"
                    "Sistem normal moda döndü. Kullanıcılar tekrar veri alabilir."
                )
                return
            
            # Parametreleri ayır
            parts = raw_content.split()
            
            if len(parts) < 1:
                self._send_raw(
                    "❌ *HATALI KULLANIM*\n\n"
                    "Kullanım:\n"
                    "`/bakim 30` - 30 dk Senaryo B\n"
                    "`/bakim 30 tam` - 30 dk Senaryo A\n"
                    "`/bakim sil` - Bakımı kaldır"
                )
                return
            
            # Süreyi al
            try:
                duration_minutes = int(parts[0])
            except:
                self._send_raw("❌ Geçersiz süre! Örn: `/bakim 30`")
                return
            
            # Mod kontrolü (tam mı yoksa limited mi)
            mode = "full" if len(parts) > 1 and parts[1].lower() == "tam" else "limited"
            
            # Mesajı belirle
            if mode == "full":
                message = "Sistem bakımda. Lütfen daha sonra tekrar deneyin."
                scenario = "A (TAM KİLİT)"
            else:
                message = "Veri akışı durduruldu. Eski veriler gösterilmektedir."
                scenario = "B (VERİ YOK)"
            
            # TTL hesapla
            ttl = duration_minutes * 60
            end_time = time.time() + ttl
            
            # Redis'e kaydet
            maintenance_data = {
                "message": message,
                "mode": mode,
                "end_time": end_time
            }
            set_cache("system_maintenance", maintenance_data, ttl=ttl)
            
            # Bitiş zamanını hesapla
            end_datetime = datetime.now() + timedelta(minutes=duration_minutes)
            
            self._send_raw(
                f"🚧 *BAKIM MODU AKTİF!*\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"📝 *Senaryo:* {scenario}\n"
                f"⏱️ *Süre:* {duration_minutes} dakika\n"
                f"🗓️ *Bitiş:* {end_datetime.strftime('%H:%M')}\n"
                f"💬 *Mesaj:* {message}\n\n"
                f"✅ Kullanıcılar artık bu mesajı görecek.\n"
                f"Bakım bitince otomatik kapanır veya `/bakim sil` yazabilirsin."
            )
            
        except Exception as e:
            self._send_raw(f"❌ Bakım modu hatası: {str(e)}")

    # ==========================================
    # BÖLÜM 4: ALARM SİSTEMİ
    # ==========================================

    def _handle_alarm(self, text):
        """
        🚨 AKILLI ALARM SİSTEMİ
        Kullanım:
        1. /alarm cpu 80 -> CPU %80'i geçerse uyar
        2. /alarm ram 85 -> RAM %85'i geçerse uyar
        3. /alarm sil -> Alarmı kapat
        """
        try:
            from utils.cache import set_cache, delete_cache
            
            # Komutu temizle
            raw_content = text.replace('/alarm', '').strip()
            
            # Silme komutu
            if raw_content.lower() == 'sil' or raw_content == '':
                delete_cache("system_alarm")
                self.is_alarm_active = False
                self._send_raw(
                    "🔕 *ALARM KAPANDI*\n\n"
                    "CPU/RAM izleme durduruldu."
                )
                return
            
            # Parametreleri ayır
            parts = raw_content.split()
            
            if len(parts) != 2:
                self._send_raw(
                    "❌ *HATALI KULLANIM*\n\n"
                    "Kullanım:\n"
                    "`/alarm cpu 80` - CPU %80 uyarısı\n"
                    "`/alarm ram 85` - RAM %85 uyarısı\n"
                    "`/alarm sil` - Alarmı kapat"
                )
                return
            
            alarm_type = parts[0].lower()
            try:
                threshold = int(parts[1])
            except:
                self._send_raw("❌ Geçersiz eşik değeri! Örn: `/alarm cpu 80`")
                return
            
            if alarm_type not in ['cpu', 'ram']:
                self._send_raw("❌ Geçersiz tip! Sadece `cpu` veya `ram` kullanabilirsin.")
                return
            
            # Alarm verisini kaydet
            alarm_data = {
                "type": alarm_type,
                "threshold": threshold,
                "last_alert": 0  # Son uyarı zamanı
            }
            set_cache("system_alarm", alarm_data, ttl=0)
            
            # Alarm thread'ini başlat
            if not self.is_alarm_active:
                self.is_alarm_active = True
                self.alarm_thread = threading.Thread(target=self._alarm_monitor, daemon=True)
                self.alarm_thread.start()
            
            icon = "🧠" if alarm_type == "cpu" else "💾"
            
            self._send_raw(
                f"🚨 *ALARM AKTİF!*\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"{icon} *Tip:* {alarm_type.upper()}\n"
                f"📊 *Eşik:* %{threshold}\n\n"
                f"✅ Eşik aşılırsa sana haber vereceğim Patron!"
            )
            
        except Exception as e:
            self._send_raw(f"❌ Alarm kurma hatası: {str(e)}")

    def _alarm_monitor(self):
        """Arka planda CPU/RAM izler"""
        while self.is_alarm_active:
            try:
                from utils.cache import get_cache
                
                alarm_data = get_cache("system_alarm")
                
                if not alarm_data:
                    self.is_alarm_active = False
                    break
                
                alarm_type = alarm_data.get("type")
                threshold = alarm_data.get("threshold")
                last_alert = alarm_data.get("last_alert", 0)
                
                # Mevcut değerleri al
                current_value = 0
                if alarm_type == "cpu":
                    current_value = psutil.cpu_percent(interval=1)
                elif alarm_type == "ram":
                    current_value = psutil.virtual_memory().percent
                
                # Eşik aşıldı mı ve son uyarıdan 10 dakika geçti mi?
                now = time.time()
                if current_value > threshold and (now - last_alert) > 600:
                    # Uyarı gönder
                    icon = "🧠" if alarm_type == "cpu" else "💾"
                    self._send_raw(
                        f"⚠️ *ALARM TETİKLENDİ!*\n\n"
                        f"{icon} *{alarm_type.upper()}:* %{current_value:.1f}\n"
                        f"📊 *Eşik:* %{threshold}\n\n"
                        f"Patron, sistem yükü arttı!"
                    )
                    
                    # Son uyarı zamanını güncelle
                    alarm_data["last_alert"] = now
                    from utils.cache import set_cache
                    set_cache("system_alarm", alarm_data, ttl=0)
                
                # 60 saniye bekle
                time.sleep(60)
                
            except Exception as e:
                logger.error(f"Alarm monitor hatası: {e}")
                time.sleep(60)

    # ==========================================
    # BÖLÜM 5: HAFTALIK RAPOR
    # ==========================================

    def _handle_rapor(self, text):
        """
        📊 HAFTALIK RAPOR
        Kullanım:
        1. /rapor -> Basit özet
        2. /rapor detay -> Detaylı 7 günlük analiz
        """
        try:
            from utils.cache import get_cache
            
            # Detay istendi mi?
            is_detailed = "detay" in text.lower()
            
            if is_detailed:
                # 7 günlük detaylı rapor
                self._send_detailed_report()
            else:
                # Basit özet
                self._send_simple_report()
                
        except Exception as e:
            self._send_raw(f"❌ Rapor hatası: {str(e)}")

    def _send_simple_report(self):
        """Basit özet rapor"""
        try:
            from utils.cache import get_cache
            
            # Mevcut durum
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent
            
            # Worker durumu
            last_worker = get_cache("kurabak:last_worker_run")
            worker_status = "🟢 Aktif" if last_worker else "🔴 Durmuş"
            
            self._send_raw(
                f"📊 *HIZLI RAPOR*\n"
                f"━━━━━━━━━━━━━━━━\n\n"
                f"⚡ CPU: `%{cpu:.1f}`\n"
                f"💾 RAM: `%{ram:.1f}`\n"
                f"👷 Worker: {worker_status}\n\n"
                f"_Detaylı rapor için `/rapor detay`_"
            )
        except Exception as e:
            self._send_raw(f"❌ Basit rapor hatası: {str(e)}")

    def _send_detailed_report(self):
        """7 günlük detaylı rapor"""
        try:
            from utils.cache import get_cache
            
            # NOT: Bu özellik için günlük metriklerin Redis'te saklanması gerekir
            # Şu an placeholder
            
            self._send_raw(
                f"📊 *HAFTALIK DETAY RAPORU*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📅 *Son 7 Gün*\n\n"
                f"⚠️ Bu özellik henüz aktif değil.\n"
                f"Günlük metriklerin kaydedilmesi gerekiyor.\n\n"
                f"🔜 *Yakında:*\n"
                f"• Ortalama uptime %\n"
                f"• Günlük hata sayısı\n"
                f"• CPU/RAM trendleri\n"
                f"• En yoğun saatler\n\n"
                f"_Bu özellik sonraki güncellemede aktif olacak._"
            )
        except Exception as e:
            self._send_raw(f"❌ Detaylı rapor hatası: {str(e)}")

# ======================================
# SINGLETON BAŞLATICI
# ======================================

telegram_monitor: Optional[TelegramMonitor] = None

def init_telegram_monitor():
    """Botu başlatır (Environment Variable kontrolü ile)"""
    global telegram_monitor
    
    if telegram_monitor:
        return telegram_monitor

    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')

    if token and chat_id:
        telegram_monitor = TelegramMonitor(token, chat_id)
        
        # Komut Dinleyiciyi Başlat
        telegram_monitor.start_command_listener()
        
        logger.info("✅ Telegram Monitor (🔒 Admin Filter + Sessiz + Komut + Duyuru + Death Star + Bakım + Alarm + Rapor) başlatıldı.")
        return telegram_monitor
    else:
        logger.warning("⚠️ Telegram Token/ChatID eksik. Bildirimler kapalı.")
        return None
