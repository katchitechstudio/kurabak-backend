"""
Maintenance Service - PRODUCTION READY (ULTIMATE EDITION) 🚀
===========================================================
✅ SCHEDULER: Otomatik güncelleme motoru (APScheduler)
✅ CIRCUIT BREAKER: Hata durumunda sistemi koruyan sigorta
✅ MANUAL TRIGGER: Admin/API tetiklemeleri için güvenli kapı
✅ DAILY REPORT: Günlük özet raporlama sistemi (Circuit Breaker dahil)
✅ THREAD-SAFE: Çoklu işlem (Worker) uyumlu yapı
✅ TELEGRAM INTEGRATION: Kritik durumlarda bildirim gönderir
"""

import logging
import threading
import time
import atexit
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

# Servisler ve Config
from services.financial_service import sync_financial_data, get_service_metrics
from config import Config

logger = logging.getLogger(__name__)

# ======================================
# GLOBAL DEĞİŞKENLER & KİLİTLER
# ======================================

_scheduler: Optional[BackgroundScheduler] = None
_scheduler_lock = threading.Lock()

# Manuel tetikleme için cooldown
_last_manual_time = 0
_manual_lock = threading.Lock()

# ======================================
# CIRCUIT BREAKER (SİGORTA)
# ======================================

class CircuitBreaker:
    """
    Sistem üst üste hata alırsa 'Açık' duruma geçer.
    Belirli süre sonra 'Yarı Açık' olup tekrar dener.
    """
    def __init__(self):
        self.failure_count = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.last_failure_time = 0
        self.lock = threading.Lock()
        
        # Config'den limitleri al
        self.threshold = Config.CIRCUIT_BREAKER_FAILURE_THRESHOLD
        self.timeout = Config.CIRCUIT_BREAKER_TIMEOUT

    def can_execute(self) -> bool:
        """İşlem yapılabilir mi?"""
        with self.lock:
            if self.state == "CLOSED":
                return True
            
            # Sigorta açıksa, süre doldu mu?
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.timeout:
                    self.state = "HALF_OPEN"
                    logger.info("🟡 Circuit Breaker: HALF_OPEN (İyileşme testi)")
                    return True
                return False
                
            # Yarı açıksa izin ver
            return True

    def record_success(self):
        """Başarılı işlem kaydı"""
        with self.lock:
            if self.state != "CLOSED":
                logger.info("🟢 Circuit Breaker: CLOSED (Sistem iyileşti)")
                
                # Telegram import (Circular import önlemek için)
                try:
                    from utils.telegram_monitor import telegram_monitor
                    if telegram_monitor:
                        telegram_monitor.send_message(
                            "✅ *SİSTEM İYİLEŞTİ*\n\n"
                            "Circuit Breaker normale döndü.\n"
                            "Tüm servisler çalışıyor.",
                            "success"
                        )
                except:
                    pass
            
            self.failure_count = 0
            self.state = "CLOSED"

    def record_failure(self):
        """Hata kaydı"""
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.threshold and self.state == "CLOSED":
                self.state = "OPEN"
                logger.error(
                    f"🔴 Circuit Breaker: OPEN "
                    f"(Sistem korumaya alındı. {self.timeout}s bekleme)"
                )
                
                # Telegram alert
                try:
                    from utils.telegram_monitor import telegram_monitor
                    if telegram_monitor:
                        telegram_monitor.send_message(
                            f"🔴 *SİGORTA ATTI!*\n\n"
                            f"Üst üste {self.failure_count} hata alındı.\n"
                            f"Sistem {self.timeout}s korumada.",
                            "critical"
                        )
                except:
                    pass

breaker = CircuitBreaker()

# ======================================
# GÖREVLER (JOBS)
# ======================================

def fetch_all_data_safe():
    """
    Zamanlayıcının çağırdığı ana fonksiyon.
    Sigortayı kontrol eder -> Veriyi çeker.
    """
    if not breaker.can_execute():
        logger.warning("🛡️ İşlem engellendi (Circuit Breaker Aktif)")
        return False

    try:
        success = sync_financial_data()
        
        if success:
            breaker.record_success()
        else:
            breaker.record_failure()
            
        return success
    except Exception as e:
        logger.error(f"❌ Kritik Hata (Scheduler): {e}")
        breaker.record_failure()
        return False

def daily_report_job():
    """Her sabah 09:00'da çalışan rapor job'u"""
    # Telegram import
    try:
        from utils.telegram_monitor import telegram_monitor
    except:
        telegram_monitor = None
    
    if not telegram_monitor:
        return

    # Metrikleri al
    metrics = get_service_metrics()
    
    # 🔥 Circuit Breaker Durumunu Ekle
    cb_status = "🟢 Normal" if breaker.state == "CLOSED" else f"🔴 {breaker.state}"
    
    # Başarı oranı hesapla
    total = metrics.get('v5', 0) + metrics.get('v4', 0) + metrics.get('v3', 0) + metrics.get('backup', 0)
    success_rate = 100
    if total > 0:
        success_rate = ((total - metrics.get('errors', 0)) / total) * 100
    
    # Rapor mesajı
    msg = (
        f"🌙 *GÜNLÜK RAPOR* | {datetime.now().strftime('%d.%m.%Y')}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        
        f"📊 *GENEL DURUM*\n"
        f"• Başarı Oranı: *%{success_rate:.1f}*\n"
        f"• Toplam İşlem: *{total}*\n\n"
        
        f"🔌 *KAYNAK KULLANIMI*\n"
        f"• 🚀 V5 (Hızlı): `{metrics.get('v5', 0)}`\n"
        f"• 🛡️ V4 (Yedek): `{metrics.get('v4', 0)}`\n"
        f"• ⚠️ V3 (Son Çare): `{metrics.get('v3', 0)}`\n"
        f"• 📦 Backup Kullanımı: `{metrics.get('backup', 0)}`\n\n"
        
        f"🛡️ *GÜVENLİK & HATALAR*\n"
        f"• Hatalar: `{metrics.get('errors', 0)}`\n"
        f"• Circuit Breaker: {cb_status}\n\n"  # 🔥 YENİ EKLEME
        
        f"_KuraBak Backend v2.0 • {datetime.now().strftime('%H:%M')}_"
    )
    
    telegram_monitor.send_message(msg, level='report')

# ======================================
# SCHEDULER YÖNETİMİ
# ======================================

def start_scheduler():
    """Zamanlayıcıyı başlatır (Singleton)"""
    global _scheduler
    
    with _scheduler_lock:
        if _scheduler and _scheduler.running:
            logger.info("⚠️ Scheduler zaten çalışıyor.")
            return _scheduler

        logger.info("⏳ Scheduler başlatılıyor...")
        
        _scheduler = BackgroundScheduler(timezone=Config.DEFAULT_TIMEZONE)
        
        # 1. Ana Veri Çekme Görevi (2 dakikada bir)
        _scheduler.add_job(
            fetch_all_data_safe,
            trigger=IntervalTrigger(seconds=Config.UPDATE_INTERVAL),
            id="sync_financial_data",
            name="Finansal Veri Senkronizasyonu",
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        # 2. Günlük Rapor Görevi (Sabah 09:00)
        _scheduler.add_job(
            daily_report_job,
            trigger=CronTrigger(hour=Config.TELEGRAM_DAILY_REPORT_HOUR, minute=0),
            id="daily_report",
            name="Günlük Rapor",
            replace_existing=True
        )
        
        _scheduler.start()
        
        logger.info("✅ Scheduler başlatıldı. İlk güncelleme tetikleniyor...")
        
        # Uygulama açılır açılmaz bir kere çalıştır
        threading.Thread(target=fetch_all_data_safe, daemon=True).start()
        
        return _scheduler

def stop_scheduler():
    """Zamanlayıcıyı durdurur"""
    global _scheduler
    
    with _scheduler_lock:
        if _scheduler and _scheduler.running:
            logger.info("🛑 Scheduler durduruluyor...")
            _scheduler.shutdown(wait=False)
            _scheduler = None
            logger.info("✅ Scheduler durduruldu.")

# ======================================
# MANUEL TETİKLEME
# ======================================

def manual_trigger() -> Dict[str, Any]:
    """
    API üzerinden manuel güncelleme.
    60 saniyelik cooldown uygular.
    """
    global _last_manual_time
    
    with _manual_lock:
        current_time = time.time()
        
        # Cooldown kontrolü
        if current_time - _last_manual_time < 60:
            remaining = 60 - int(current_time - _last_manual_time)
            return {
                "success": False,
                "message": f"Çok sık güncelleme yapamazsınız. {remaining}sn bekleyin.",
                "circuit_breaker": breaker.state
            }
            
        _last_manual_time = current_time

    # İşlemi başlat
    logger.info("👆 Manuel güncelleme tetiklendi.")
    success = fetch_all_data_safe()
    
    return {
        "success": success,
        "message": "Güncelleme başarılı" if success else "Güncelleme başarısız (Logları kontrol et)",
        "circuit_breaker": breaker.state,
        "timestamp": datetime.now().isoformat()
    }

def get_scheduler_status():
    """Scheduler durumunu döndürür"""
    with _scheduler_lock:
        return {
            "running": _scheduler.running if _scheduler else False,
            "circuit_breaker": {
                "state": breaker.state,
                "failure_count": breaker.failure_count,
                "threshold": breaker.threshold
            },
            "jobs": [job.id for job in _scheduler.get_jobs()] if _scheduler else [],
            "metrics": get_service_metrics()
        }

# Uygulama kapanırken scheduler'ı kapat
atexit.register(stop_scheduler)
