"""
Telegram Monitor - PRODUCTION READY (Final) 🚀
==============================================
✅ Smart Alerting (Spam Koruması)
✅ Cooldown Management
✅ Daily Reports & Critical Alerts
✅ Asynchronous Startup Message (Non-blocking)
✅ Environment Variable Priority
✅ Thread-Safe Operations
"""

import os
import requests
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from config import Config

logger = logging.getLogger(__name__)

class TelegramMonitor:
    """
    Akıllı Telegram Monitoring Sistemi
    Features: Smart cooldown, Priority levels, Automated reports
    """
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        
        # Akıllı cooldown sistemi (spam yapmaz)
        self.last_alert_time: Dict[str, datetime] = {}
        self.alert_cooldown = {
            'critical': timedelta(minutes=15),   # Critical: 15 dk bekle
            'warning': timedelta(hours=1),       # Warning: 1 saat bekle
            'info': timedelta(minutes=5),        # Info: 5 dk bekle
            'success': timedelta(minutes=1)      # Success: 1 dk bekle
        }
        
        self.enabled = True
        self._lock = threading.Lock()
        
        logger.info(f"🤖 Telegram Monitor başlatıldı - Chat ID: {chat_id}")
    
    def send_message(self, text: str, alert_level: str = 'info') -> bool:
        """
        Akıllı mesaj gönder - spam yapmaz!
        """
        if not self.enabled:
            return False
        
        # Cooldown kontrolü (Thread-safe)
        with self._lock:
            now = datetime.now(timezone.utc)
            last_time = self.last_alert_time.get(alert_level)
            
            # Eğer cooldown süresi dolmadıysa gönderme
            if last_time and (now - last_time) < self.alert_cooldown.get(alert_level, timedelta(minutes=1)):
                logger.debug(f"⏳ Cooldown aktif: {alert_level}")
                return False
            
            # Zamanı güncelle
            self.last_alert_time[alert_level] = now
        
        try:
            # Emoji mapping
            emoji_map = {
                'critical': '🔴',
                'warning': '🟡',
                'info': '🔵',
                'success': '🟢',
                'system': '⚙️'
            }
            emoji = emoji_map.get(alert_level, '⚪')
            
            # Formatlı mesaj (UTC+3 Türkiye Saati ile gösterim için)
            tr_time = datetime.now(timezone.utc) + timedelta(hours=3)
            formatted_text = f"{emoji} *KuraBak Monitor*\n\n{text}\n\n_⌚ {tr_time.strftime('%H:%M:%S')}_"
            
            # Telegram API çağrısı
            response = requests.post(
                f"{self.base_url}/sendMessage",
                json={
                    'chat_id': self.chat_id,
                    'text': formatted_text,
                    'parse_mode': 'Markdown',
                    'disable_web_page_preview': True,
                    'disable_notification': alert_level in ['info', 'success']
                },
                timeout=10
            )
            
            if response.status_code == 200:
                return True
            else:
                logger.error(f"❌ Telegram API Error: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Telegram hatası: {e}")
            return False

    # ==========================================
    # ALERT FONKSİYONLARI
    # ==========================================
    
    def alert_circuit_open(self, breaker_status: Dict[str, Any]) -> bool:
        """Circuit Breaker açıldığında CRITICAL alert"""
        try:
            text = f"*🔴 CRITICAL - SİGORTA ATTI!*\n\n"
            text += f"*Sistem koruma moduna geçti (OPEN State)*\n\n"
            text += f"• Hata Sayısı: `{breaker_status.get('failure_count', 0)}`\n"
            text += f"• Toplam Çağrı: `{breaker_status.get('total_calls', 0)}`\n"
            text += f"• Başarı Oranı: `{breaker_status.get('success_rate', '0%')}`\n"
            text += f"• Timeout: `{Config.CIRCUIT_BREAKER_TIMEOUT}s`\n\n"
            text += f"⚠️ *Otomatik iyileşme bekleniyor...*"
            
            return self.send_message(text, 'critical')
        except Exception as e:
            logger.error(f"Alert error: {e}")
            return False

    def send_startup_message(self) -> bool:
        """Backend başladığında bildirim"""
        try:
            text = f"🚀 *Sistem Başlatıldı*\n\n"
            text += f"• Ortam: `{Config.ENVIRONMENT.upper()}`\n"
            text += f"• Versiyon: `{Config.APP_VERSION}`\n"
            text += f"• Zamanlayıcı: `{Config.UPDATE_INTERVAL}s`\n"
            
            return self.send_message(text, 'success')
        except Exception:
            return False

    def send_daily_report(self, metrics: Dict[str, Any]) -> bool:
        """Günlük özet raporu"""
        try:
            text = f"📊 *Günlük Rapor*\n\n"
            text += f"✅ Başarı: `{metrics.get('success_rate', 'N/A')}`\n"
            text += f"📉 Toplam İstek: `{metrics.get('total_calls', 0)}`\n"
            text += f"⚡ Ort. Süre: `{metrics.get('avg_response_time', 0):.2f}s`\n"
            text += f"🔴 Hatalar: `{metrics.get('errors', 0)}`"
            
            return self.send_message(text, 'info')
        except Exception:
            return False

# ======================================
# GLOBAL INSTANCE & INIT
# ======================================

telegram_monitor: Optional[TelegramMonitor] = None

def init_telegram_monitor() -> Optional[TelegramMonitor]:
    """Telegram monitor'ü başlat"""
    global telegram_monitor
    
    try:
        # 1. Önce Environment Variable'a bak (En güvenli)
        token = os.environ.get('TELEGRAM_BOT_TOKEN')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        
        # 2. Yoksa Config'den bak
        if not token:
            token = getattr(Config, 'TELEGRAM_BOT_TOKEN', None)
        if not chat_id:
            chat_id = getattr(Config, 'TELEGRAM_CHAT_ID', None)
            
        # 3. Config.SECURITY yapısı varsa oradan da dene (Geriye dönük uyumluluk)
        if not token and hasattr(Config, 'SECURITY'):
            token = getattr(Config.SECURITY, 'telegram_bot_token', None)
            chat_id = getattr(Config.SECURITY, 'telegram_chat_id', None)

        if token and chat_id:
            telegram_monitor = TelegramMonitor(bot_token=token, chat_id=chat_id)
            
            # Startup mesajını ayrı thread'de gönder (Boot süresini etkilemesin)
            threading.Thread(
                target=lambda: telegram_monitor.send_startup_message(),
                daemon=True
            ).start()
            
            return telegram_monitor
        else:
            logger.warning("⚠️ Telegram config eksik (TOKEN veya CHAT_ID yok)")
            return None
            
    except Exception as e:
        logger.error(f"❌ Telegram monitor başlatma hatası: {e}")
        return None
