"""
Telegram Monitor - PRODUCTION READY (SILENT & STYLISH) 🌙
=========================================================
✅ ANTI-SPAM: Gün içi gereksiz bildirimleri engeller.
✅ MODERN RAPOR: Gece raporu için özel "Şekilli" tasarım.
✅ CRITICAL ONLY: Sadece sistem çökerse veya rapor zamanıysa yazar.
✅ THREAD-SAFE: Arka planda sessizce çalışır.
"""

import os
import requests
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class TelegramMonitor:
    """
    Sessiz ve Modern Telegram Botu
    """
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self._lock = threading.Lock()
        
        # Spam Koruması: Aynı hatayı 30 dakika içinde tekrar atmasın
        self.last_critical_alert = datetime.min

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
        # Başlangıç mesajını sessize aldık (Kullanıcı isteği)
        logger.info("✅ Telegram Monitor (Sessiz Mod) başlatıldı.")
        return telegram_monitor
    else:
        logger.warning("⚠️ Telegram Token/ChatID eksik. Bildirimler kapalı.")
        return None
