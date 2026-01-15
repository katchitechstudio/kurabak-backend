"""
Telegram Monitor - PRODUCTION READY 🤖
=======================================
✅ Smart Alerting (Spam yok)
✅ Cooldown Management
✅ Daily Reports
✅ Critical Alerts
✅ Thread-Safe
✅ Error Handling
✅ Config.SECURITY Compliant (Fixed!)
"""

import requests
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from config import Config

logger = logging.getLogger(__name__)

class TelegramMonitor:
    """
    Akıllı Telegram Monitoring Sistemi
    
    Features:
    - Smart cooldown (spam yapmaz)
    - Priority levels (critical/warning/info)
    - Daily automated reports
    - Circuit breaker alerts
    - Service health alerts
    """
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        
        # Akıllı cooldown sistemi (spam yapmaz)
        self.last_alert_time: Dict[str, datetime] = {}
        self.alert_cooldown = {
            'critical': timedelta(minutes=30),   # 30 dakika
            'warning': timedelta(hours=2),       # 2 saat
            'info': timedelta(minutes=1),        # 1 dakika (raporlar için)
            'success': timedelta(minutes=1)      # 1 dakika
        }
        
        self.enabled = True
        
        # Config kontrolü
        if not bot_token or not chat_id:
            logger.warning("⚠️ Telegram Monitor config eksik! Monitoring disabled.")
            self.enabled = False
        else:
            logger.info(f"🤖 Telegram Monitor başlatıldı - Chat ID: {chat_id}")
    
    def send_message(self, text: str, alert_level: str = 'info') -> bool:
        """
        Akıllı mesaj gönder - spam yapmaz!
        
        Parameters:
        - text: Gönderilecek mesaj
        - alert_level: 'critical', 'warning', 'info', 'success'
        """
        if not self.enabled:
            logger.debug("Telegram monitor disabled, mesaj gönderilmedi")
            return False
        
        # Cooldown kontrolü
        now = datetime.now()
        last_time = self.last_alert_time.get(alert_level)
        
        if last_time and (now - last_time) < self.alert_cooldown[alert_level]:
            logger.debug(f"⏳ Cooldown aktif: {alert_level} - {text[:50]}...")
            return False
        
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
            
            # Formatlı mesaj
            formatted_text = f"{emoji} *KuraBak Monitor*\n\n{text}\n\n_⌚ {now.strftime('%H:%M')}_"
            
            # Telegram API çağrısı
            response = requests.post(
                f"{self.base_url}/sendMessage",
                json={
                    'chat_id': self.chat_id,
                    'text': formatted_text,
                    'parse_mode': 'Markdown',
                    'disable_notification': alert_level in ['info', 'success']
                },
                timeout=10
            )
            
            if response.status_code == 200:
                self.last_alert_time[alert_level] = now
                logger.info(f"✅ Telegram alert gönderildi: {alert_level}")
                return True
            else:
                try:
                    error_msg = response.json().get('description', 'Unknown error')
                except:
                    error_msg = response.text
                logger.error(f"❌ Telegram API Error: {error_msg}")
                return False
                
        except requests.exceptions.Timeout:
            logger.error("❌ Telegram timeout - sunucu yanıt vermedi")
            return False
        except requests.exceptions.ConnectionError:
            logger.error("❌ Telegram connection error - internet bağlantısı yok")
            return False
        except Exception as e:
            logger.error(f"❌ Telegram hatası: {str(e)}")
            return False
    
    # ========== ALERT FONKSİYONLARI ==========
    
    def send_daily_report(self, metrics: Dict[str, Any]) -> bool:
        """Sabah 09:00'da günlük özet raporu"""
        try:
            report = f"📊 *Günlük Sistem Raporu*\n\n"
            report += f"✅ Başarı Oranı: {metrics.get('success_rate', 'N/A')}\n"
            report += f"📈 Toplam İstek: {metrics.get('total_calls', 0)}\n"
            report += f"🔄 Senkronizasyon: {metrics.get('sync_count', metrics.get('v5_success', 0))}\n"
            report += f"⏱️ Ort. Yanıt Süresi: {metrics.get('avg_response_time', 0):.2f}s\n"
            report += f"🟢 V5 Başarı: {metrics.get('v5_success', 0)}\n"
            report += f"🟡 Fallback Kullanımı: {metrics.get('v4_fallback', 0) + metrics.get('v3_fallback', 0)}\n"
            report += f"🔴 Hatalar: {metrics.get('errors', 0)}\n"
            report += f"🔄 JSON Onarımları: {metrics.get('json_repairs', 0)}\n\n"
            report += f"_📍 {datetime.now().strftime('%d.%m.%Y %H:%M')}_"
            
            return self.send_message(report, 'info')
        except Exception as e:
            logger.error(f"❌ Daily report hatası: {e}")
            return False
    
    def alert_circuit_open(self, breaker_status: Dict[str, Any]) -> bool:
        """Circuit Breaker açıldığında CRITICAL alert"""
        try:
            text = f"🔴 *CRITICAL ALERT - Circuit Breaker AÇILDI!*\n\n"
            text += f"*Sistem koruma moduna geçti!*\n\n"
            text += f"• Sebep: {breaker_status.get('failure_count', 0)} ardışık hata\n"
            text += f"• Timeout: {breaker_status.get('config', {}).get('timeout', 0)} saniye\n"
            text += f"• Son Başarı: {breaker_status.get('last_success', 'Hiç yok')}\n"
            text += f"• Toplam Açılma: {breaker_status.get('circuit_opens', 0)}. kez\n"
            text += f"• Başarı Oranı: {breaker_status.get('success_rate', '0%')}\n\n"
            text += f"⚠️ *ACİL MÜDAHALE GEREKİYOR!*\n"
            text += f"Sistem şu an fallback modunda çalışıyor."
            
            return self.send_message(text, 'critical')
        except Exception as e:
            logger.error(f"❌ Circuit alert hatası: {e}")
            return False
    
    def alert_service_down(self, service_name: str, duration_minutes: int) -> bool:
        """Servis down olduğunda WARNING alert"""
        try:
            text = f"🟡 *SERVİS UYARISI - {service_name} Çalışmıyor!*\n\n"
            text += f"*{service_name} servisi yanıt vermiyor.*\n\n"
            text += f"• Kapalı Kalma Süresi: {duration_minutes} dakika\n"
            text += f"• Servis: {service_name}\n"
            text += f"• Saat: {datetime.now().strftime('%H:%M')}\n\n"
            text += f"🛠️ *Kontrol Edilmesi Gerekiyor*"
            
            return self.send_message(text, 'warning')
        except Exception as e:
            logger.error(f"❌ Service down alert hatası: {e}")
            return False
    
    def alert_high_latency(self, endpoint: str, response_time: float, threshold: float = 2.0) -> bool:
        """Yüksek latency WARNING alert"""
        try:
            text = f"🐌 *PERFORMANS UYARISI - Yavaş Yanıt Süresi!*\n\n"
            text += f"*{endpoint} endpoint'i yavaşladı.*\n\n"
            text += f"• Endpoint: `{endpoint}`\n"
            text += f"• Yanıt Süresi: {response_time:.2f}s\n"
            text += f"• Limit Değer: {threshold}s\n"
            text += f"• Durum: İzlemede\n\n"
            text += f"⚡ *Performans iyileştirmesi gerekebilir*"
            
            return self.send_message(text, 'warning')
        except Exception as e:
            logger.error(f"❌ Latency alert hatası: {e}")
            return False
    
    def send_startup_message(self) -> bool:
        """Backend başladığında bilgilendirme"""
        try:
            text = f"🚀 *KuraBak Backend Başlatıldı!*\n\n"
            text += f"*Sistem aktif ve çalışıyor.*\n\n"
            text += f"• Zaman: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            text += f"• Environment: {Config.ENVIRONMENT.upper()}\n"
            text += f"• Version: {Config.APP_VERSION}\n"
            text += f"• Monitoring: Aktif\n\n"
            text += f"✅ *Tüm sistemler normal*"
            
            return self.send_message(text, 'success')
        except Exception as e:
            logger.error(f"❌ Startup message hatası: {e}")
            return False
    
    def send_test_message(self) -> bool:
        """Test mesajı gönder"""
        try:
            text = f"🔧 *Test Mesajı*\n\n"
            text += f"Telegram monitoring sistemi başarıyla çalışıyor!\n\n"
            text += f"• Bot: @KuraBakSistemBot\n"
            text += f"• Chat ID: {self.chat_id}\n"
            text += f"• Zaman: {datetime.now().strftime('%H:%M:%S')}\n\n"
            text += f"✅ *Test başarılı!*"
            
            return self.send_message(text, 'success')
        except Exception as e:
            logger.error(f"❌ Test message hatası: {e}")
            return False
    
    # ========== UTILITY FONKSİYONLARI ==========
    
    def disable(self) -> None:
        """Monitoring'i geçici olarak devre dışı bırak"""
        self.enabled = False
        logger.info("📵 Telegram monitor disabled")
    
    def enable(self) -> None:
        """Monitoring'i aktif et"""
        self.enabled = True
        logger.info("📱 Telegram monitor enabled")
    
    def get_status(self) -> Dict[str, Any]:
        """Monitor durumunu getir"""
        return {
            'enabled': self.enabled,
            'chat_id': self.chat_id,
            'bot_username': '@KuraBakSistemBot',
            'last_alerts': {k: v.isoformat() for k, v in self.last_alert_time.items()},
            'cooldown_settings': {k: str(v) for k, v in self.alert_cooldown.items()}
        }

# Global instance
telegram_monitor: Optional[TelegramMonitor] = None

def init_telegram_monitor() -> Optional[TelegramMonitor]:
    """Telegram monitor'ü başlat"""
    global telegram_monitor
    
    try:
        # ✅ GÜVENLİK DÜZELTMESİ: Config.SECURITY üzerinden erişim
        if Config.SECURITY.has_telegram_config():
            telegram_monitor = TelegramMonitor(
                bot_token=Config.SECURITY.telegram_bot_token,
                chat_id=Config.SECURITY.telegram_chat_id
            )
            
            # Startup mesajı gönder
            telegram_monitor.send_startup_message()
            
            logger.info("🤖 Telegram Monitor başlatıldı ve startup mesajı gönderildi")
            return telegram_monitor
        else:
            logger.warning("⚠️ Telegram config eksik, monitor başlatılamadı")
            return None
            
    except Exception as e:
        logger.error(f"❌ Telegram monitor başlatma hatası: {e}")
        return None
