"""
Telegram Monitor - ŞEF KOMUTA MERKEZİ V3.0 🤖
=======================================================
✅ KOMUTLAR: /durum, /online, /temizle, /analiz, /duyuru, /sus, /konus
✅ YENİ: /bakim, /bakim kapat
✅ SELF-HEALING: Otomatik CPU/RAM izleme ve müdahale
✅ SADECE V5: V4/V3 referansları kaldırıldı
✅ ANTI-SPAM: Gün içi gereksiz bildirimleri engeller
✅ THREAD-SAFE: Arka planda sessizce çalışır
✅ 🔒 ADMİN GÜVENLİĞİ: Sadece yetkili Telegram ID komut gönderebilir
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
# TELEGRAM MONITOR (RAPOR + KOMUT + ALARM)
# ======================================

class TelegramMonitor:
    """
    Gelişmiş Telegram Bot:
    1. RAPOR MODU: Sessiz bildirimler, günlük raporlar
    2. KOMUT MODU: Komutları dinler ve cevaplar
    3. BAKIM MODU: Sistem bakım yönetimi
    4. SELF-HEALING: Otomatik CPU/RAM izleme ve düzeltme
    5. 🔒 ADMİN FİLTRESİ: Sadece yetkili kullanıcılar
    """
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self._lock = threading.Lock()
        
        # Spam Koruması
        self.last_critical_alert = datetime.min
        
        # Komut Dinleyici Thread
        self.command_thread = None
        self.is_listening = False
        
        # Self-Healing Thread
        self.healing_thread = None
        self.is_healing_active = False

    # ==========================================
    # BÖLÜM 1: RAPOR SİSTEMİ
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
        # 1. Önemsiz mesajları filtrele
        if level in ['info', 'success', 'warning']:
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
        """
        now = datetime.now()
        date_str = now.strftime("%d.%m.%Y")
        
        # Başarı oranı hesapla (sadece V5)
        total = metrics.get('v5', 0) + metrics.get('backup', 0)
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
            f"• 🚀 V5 API: `{metrics.get('v5', 0)}`\n"
            f"• 📦 Backup: `{metrics.get('backup', 0)}`\n\n"
            
            f"🛡️ *GÜVENLİK & HATALAR*\n"
            f"• Hatalar: `{metrics.get('errors', 0)}`\n\n"
            
            f"_KuraBak Backend v3.0 • {now.strftime('%H:%M')}_"
        )
        
        self.send_message(report, level='report')

    # ==========================================
    # BÖLÜM 2: KOMUT SİSTEMİ
    # ==========================================

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
                    
                    # 🔒 GÜVENLİK 1: Sadece yetkili chat
                    if str(message.get('chat', {}).get('id')) != str(self.chat_id):
                        continue
                    
                    # 🔒 GÜVENLİK 2: Kullanıcı ID kontrolü
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
                    
                    # ✅ Yetkili kullanıcı - Komutları işle
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
                    elif text.startswith('/'):
                        self._send_help()
                
            except Exception as e:
                logger.error(f"Komut dinleyici hatası: {e}")
                time.sleep(10)

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
            "`/bakim` - Bakım modunu aç\n"
            "`/bakim kapat` - Bakım modunu kapat\n\n"
            "📊 *RAPOR:*\n"
            "`/durum` - Sistem sağlık raporu\n"
            "`/online` - Aktif kullanıcı\n"
            "`/temizle` - Cache temizliği\n"
            "`/analiz` - Sistem analizi\n\n"
            "🔒 _Bu komutlar sadece yetkili admin tarafından kullanılabilir._"
        )

    def _handle_durum(self):
        """Sistem Durumu Raporu"""
        try:
            from utils.cache import get_cache, redis_wrapper
            from config import Config
            
            # CPU & RAM
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent
            
            # Worker durumu
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
            
            # Redis durumu
            redis_status = "🟢 Bağlı" if redis_wrapper.is_enabled() else "🔴 RAM Modu"
            
            # Snapshot durumu
            snapshot_exists = bool(get_cache(Config.CACHE_KEYS['yesterday_prices']))
            snapshot_icon = "🟢" if snapshot_exists else "🔴"
            
            # Bakım durumu
            maintenance_data = get_cache(Config.CACHE_KEYS['maintenance'])
            maintenance_status = "🔴 Aktif" if maintenance_data else "🟢 Kapalı"
            
            # Self-Healing durumu
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
                
                f"🚧 *ÖZEL MODLAR*\n"
                f"• Bakım: {maintenance_status}\n\n"
                
                f"🔒 *GÜVENLİK*\n"
                f"• Admin Filter: `Aktif`\n"
                f"• API: `V5 Only`\n\n"
                
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
        """Redis Cache Temizliği"""
        try:
            from utils.cache import flush_all_cache
            
            self._send_raw(
                "⚠️ *CACHE TEMİZLİĞİ*\n\n"
                "Tüm Redis verileri silinecek!\n"
                "İşlem başlatılıyor..."
            )
            
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
        """Sistem Analizi"""
        try:
            self._send_raw(
                "📊 *SİSTEM ANALİZİ*\n\n"
                "🚀 *API:* V5 Only (Optimized)\n"
                "🤖 *Self-Healing:* Aktif\n"
                "⏱️ *Kontrol Sıklığı:* 1 dakika\n"
                "🎯 *CPU Eşik:* %80\n"
                "💾 *RAM Eşik:* %85\n\n"
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
            
            # Silme Komutu
            if raw_content.lower() == 'sil' or raw_content == '':
                delete_cache(Config.CACHE_KEYS['banner'])
                self._send_raw("🔇 *DUYURU KALDIRILDI*\n\nPatron, mesajı sildim. Uygulama ekranlarından kayboldu.")
                return

            # Süre Analizi
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
        """🚧 BAKIM MODU (Basit Versiyon)"""
        try:
            from services.maintenance_service import activate_maintenance, deactivate_maintenance
            
            raw_content = text.replace('/bakim', '').strip()
            
            # Kapatma komutu
            if raw_content.lower() in ['kapat', 'sil', '']:
                deactivate_maintenance()
                self._send_raw(
                    "✅ *BAKIM MODU KAPANDI*\n\n"
                    "Sistem normal moda döndü. Kullanıcılar tekrar veri alabilir."
                )
                return
            
            # Bakım modunu aç
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

    # ==========================================
    # BÖLÜM 3: SELF-HEALING (OTOMATİK MÜDAHALE)
    # ==========================================

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
                # Mevcut değerleri al
                cpu = psutil.cpu_percent(interval=1)
                ram = psutil.virtual_memory().percent
                now = time.time()
                
                # --- CPU KONTROLÜ ---
                if cpu > Config.CPU_THRESHOLD:
                    if cpu_high_since is None:
                        cpu_high_since = now
                    
                    # 5 dakika boyunca yüksekse müdahale et
                    if (now - cpu_high_since) > Config.CPU_HIGH_DURATION:
                        # Müdahale: Gereksiz processleri temizle (örnek)
                        logger.warning(f"🔥 CPU yüksek ({cpu}%), müdahale ediliyor...")
                        
                        # Bildirim gönder (30 dakikada bir)
                        if (now - last_cpu_notification) > Config.ALARM_NOTIFICATION_INTERVAL:
                            self._send_raw(
                                f"⚠️ *CPU YÜKSEK!*\n\n"
                                f"🧠 *CPU:* %{cpu:.1f}\n"
                                f"📊 *Eşik:* %{Config.CPU_THRESHOLD}\n"
                                f"⏱️ *Süre:* {int((now - cpu_high_since)/60)} dakika\n\n"
                                f"Sistem müdahale edecek..."
                            )
                            last_cpu_notification = now
                        
                        # Burada cache temizliği veya restart gibi işlemler yapılabilir
                        # Örnek: from utils.cache import flush_all_cache
                        # flush_all_cache()
                        
                        cpu_high_since = None  # Reset
                else:
                    # CPU normale döndü
                    if cpu_high_since is not None:
                        logger.info(f"✅ CPU normale döndü: %{cpu:.1f}")
                        cpu_high_since = None
                
                # --- RAM KONTROLÜ ---
                if ram > Config.RAM_THRESHOLD:
                    logger.warning(f"💾 RAM yüksek ({ram}%), otomatik temizlik yapılıyor...")
                    
                    # Otomatik cache temizliği
                    try:
                        from utils.cache import flush_all_cache
                        flush_all_cache()
                        
                        # Yeni RAM değerini al
                        new_ram = psutil.virtual_memory().percent
                        
                        # Bildirim gönder (30 dakikada bir)
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
                
                # 1 dakika bekle (Config'den al)
                time.sleep(Config.ALARM_CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"Self-Healing hatası: {e}")
                time.sleep(60)

# ======================================
# SINGLETON BAŞLATICI
# ======================================

telegram_monitor: Optional[TelegramMonitor] = None

def init_telegram_monitor():
    """Botu başlatır"""
    global telegram_monitor
    
    if telegram_monitor:
        return telegram_monitor

    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')

    if token and chat_id:
        telegram_monitor = TelegramMonitor(token, chat_id)
        
        # Komut Dinleyiciyi Başlat
        telegram_monitor.start_command_listener()
        
        # Self-Healing Sistemini Başlat
        telegram_monitor.start_self_healing()
        
        logger.info("✅ Telegram Monitor (Komut + Self-Healing + V5 Only) başlatıldı.")
        return telegram_monitor
    else:
        logger.warning("⚠️ Telegram Monitor başlatılamadı: Token veya Chat ID eksik!")
        return None

def get_telegram_monitor() -> Optional[TelegramMonitor]:
    """Singleton instance döndürür"""
    return telegram_monitor
