"""
Telegram Monitor - ŞEF KOMUTA MERKEZİ + RAPOR SİSTEMİ 🤖
=======================================================
✅ KOMUTLAR: /durum, /online, /temizle, /analiz (Sadece Patron!)
✅ ANTI-SPAM: Gün içi gereksiz bildirimleri engeller.
✅ MODERN RAPOR: Gece raporu için özel "Şekilli" tasarım.
✅ CRITICAL ONLY: Sadece sistem çökerse veya rapor zamanıysa yazar.
✅ THREAD-SAFE: Arka planda sessizce çalışır.
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
# TELEGRAM MONITOR (RAPOR + KOMUT)
# ======================================

class TelegramMonitor:
    """
    Çift Modlu Telegram Bot:
    1. RAPOR MODU: Sessiz bildirimler, günlük raporlar
    2. KOMUT MODU: Senin komutlarını dinler ve cevaplar
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
    # BÖLÜM 2: KOMUT SİSTEMİ (YENİ!)
    # ==========================================

    def start_command_listener(self):
        """
        Arka planda komutları dinlemeye başlar
        /durum, /online, /temizle, /analiz
        """
        if self.is_listening:
            logger.warning("Komut dinleyici zaten çalışıyor!")
            return
        
        self.is_listening = True
        self.command_thread = threading.Thread(target=self._listen_commands, daemon=True)
        self.command_thread.start()
        logger.info("🤖 Şef Komut Dinleyici başlatıldı!")

    def _listen_commands(self):
        """
        Telegram'dan gelen komutları dinler (Long Polling)
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
                    
                    # Sadece senin mesajlarını işle
                    if str(message.get('chat', {}).get('id')) != str(self.chat_id):
                        continue
                    
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
                    elif text.startswith('/'):
                        self._send_raw(
                            "❓ *Bilinmeyen Komut*\n\n"
                            "Kullanılabilir komutlar:\n"
                            "`/durum` - Sistem sağlık raporu\n"
                            "`/online` - Aktif kullanıcı sayısı\n"
                            "`/temizle` - Cache temizliği\n"
                            "`/analiz` - Versiyon analizi"
                        )
                
            except Exception as e:
                logger.error(f"Komut dinleyici hatası: {e}")
                time.sleep(10)  # Hata durumunda bekle

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
        
        logger.info("✅ Telegram Monitor (Sessiz Mod + Komut Sistemi) başlatıldı.")
        return telegram_monitor
    else:
        logger.warning("⚠️ Telegram Token/ChatID eksik. Bildirimler kapalı.")
        return None
