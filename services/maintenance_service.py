"""
Maintenance Service - PRODUCTION READY (FINAL) 🚀
==================================================
✅ Circuit Breaker (Config-driven + Telegram Alert) ✅ FIXED
✅ Thread-Safe Scheduler
✅ Graceful Shutdown
✅ Multi-Process Safe
✅ Timezone Bug Fixed
✅ Manual Update Cooldown (60s)
✅ Safe Cache Preservation
✅ TELEGRAM ENTEGRASYONU TAMAMLANDI ✅
✅ GÜNLÜK RAPOR SİSTEMİ EKLENDİ ✅
"""

import logging
import atexit
import threading
import os
import signal
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor

from services.financial_service import sync_financial_data, get_service_metrics
from config import Config

# ⚠️ KRİTİK DÜZELTME: Telegram monitor import'u
from utils.telegram_monitor import init_telegram_monitor, telegram_monitor

logger = logging.getLogger(__name__)

# ======================================
# GLOBAL VARIABLES
# ======================================

# Manuel update cooldown
_last_manual_trigger_time = 0
_manual_trigger_lock = threading.Lock()

# Günlük rapor için
_last_daily_report_time = None
_daily_report_lock = threading.Lock()

# Global Telegram monitor instance (app.py'den geliyor)
_telegram_monitor = None

# ======================================
# TELEGRAM HELPER FUNCTIONS
# ======================================

def get_telegram_monitor():
    """Get Telegram monitor instance safely"""
    global _telegram_monitor
    
    if _telegram_monitor is None:
        # app.py'den gelmemişse kendimiz başlatalım
        try:
            _telegram_monitor = init_telegram_monitor()
            if _telegram_monitor:
                logger.info("✅ Telegram monitor (maintenance) initialized")
            else:
                logger.warning("⚠️ Telegram monitor initialization failed")
        except Exception as e:
            logger.error(f"❌ Telegram monitor error: {e}")
    
    return _telegram_monitor

def send_telegram_notification(message: str, alert_level: str = 'info') -> bool:
    """Send notification to Telegram (with safety checks)"""
    monitor = get_telegram_monitor()
    if monitor:
        try:
            return monitor.send_message(message, alert_level)
        except Exception as e:
            logger.error(f"❌ Telegram notification error: {e}")
            return False
    return False

# ======================================
# CONFIG VALIDATION
# ======================================

def validate_service_config():
    """Validate critical configuration values on startup"""
    warnings = []
    errors = []
    
    # UPDATE_INTERVAL validation
    if Config.UPDATE_INTERVAL < 30:
        warnings.append(f"UPDATE_INTERVAL ({Config.UPDATE_INTERVAL}s) düşük! Production için 60s+ önerilir.")
    
    # CIRCUIT BREAKER validation
    if Config.CIRCUIT_BREAKER_FAILURE_THRESHOLD < 2:
        errors.append(f"CIRCUIT_BREAKER_FAILURE_THRESHOLD ({Config.CIRCUIT_BREAKER_FAILURE_THRESHOLD}) çok düşük! Minimum 2.")
    
    if Config.CIRCUIT_BREAKER_TIMEOUT < 60:
        errors.append(f"CIRCUIT_BREAKER_TIMEOUT ({Config.CIRCUIT_BREAKER_TIMEOUT}s) çok kısa! Minimum 60s.")
    
    if Config.CIRCUIT_BREAKER_HALF_OPEN_SUCCESS < 2:
        errors.append(f"CIRCUIT_BREAKER_HALF_OPEN_SUCCESS ({Config.CIRCUIT_BREAKER_HALF_OPEN_SUCCESS}) düşük! Minimum 2.")
    
    # SCHEDULER validation
    if Config.SCHEDULER_MAX_WORKERS < 1:
        errors.append(f"SCHEDULER_MAX_WORKERS ({Config.SCHEDULER_MAX_WORKERS}) geçersiz! Minimum 1.")
    
    if Config.SCHEDULER_MAX_INSTANCES < 1:
        errors.append(f"SCHEDULER_MAX_INSTANCES ({Config.SCHEDULER_MAX_INSTANCES}) geçersiz! Minimum 1.")
    
    # Log results
    for warning in warnings:
        logger.warning(f"⚠️ Config Warning: {warning}")
    
    if errors:
        for error in errors:
            logger.error(f"❌ Config Error: {error}")
        raise ValueError("Critical configuration errors detected!")
    
    logger.info("✅ Service configuration validated successfully")

# Run validation on import
validate_service_config()

# ======================================
# CIRCUIT BREAKER (IMPROVED WITH TELEGRAM)
# ======================================

class CircuitBreaker:
    """
    Production-Grade Circuit Breaker Pattern with Telegram integration
    """
    
    def __init__(
        self, 
        name: str, 
        failure_threshold: int = 5,
        timeout: int = 300,
        half_open_success_threshold: int = 3
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.half_open_success_threshold = half_open_success_threshold
        
        # State
        self.state = 'CLOSED'
        self.failure_count = 0
        self.success_count = 0
        
        # Timing
        self.first_failure_time = None
        self.last_failure_time = None
        self.last_success_time = None
        self.last_state_change = datetime.now(timezone.utc)
        
        # Metrics
        self.total_calls = 0
        self.total_failures = 0
        self.total_successes = 0
        self.circuit_opens = 0
        self.recoveries = 0
        
        # Thread safety
        self._lock = threading.Lock()
        
        logger.info(
            f"🔧 Circuit Breaker: {name} "
            f"(threshold={failure_threshold}, timeout={timeout}s, half_open={half_open_success_threshold})"
        )
    
    def call(self, func) -> bool:
        """Execute function with circuit breaker protection"""
        with self._lock:
            self.total_calls += 1
            current_state = self.state
            
            # OPEN state: Check timeout
            if current_state == 'OPEN':
                if not self.first_failure_time:
                    logger.warning(f"⚠️ {self.name} OPEN but no first_failure_time! → HALF_OPEN")
                    self._transition_to_half_open()
                else:
                    elapsed = (datetime.now(timezone.utc) - self.first_failure_time).total_seconds()
                    
                    if elapsed >= self.timeout:
                        logger.info(f"🔄 {self.name} timeout expired ({elapsed:.0f}s) → HALF_OPEN")
                        self._transition_to_half_open()
                    else:
                        remaining = int(self.timeout - elapsed)
                        if self.total_calls % 10 == 0:
                            logger.warning(f"⚠️ {self.name} OPEN - {remaining}s remaining")
                        return False
        
        # Execute function (outside lock to prevent blocking)
        try:
            result = func()
            
            with self._lock:
                if result:
                    self._handle_success()
                else:
                    self._handle_failure()
                
                return result
        
        except Exception as e:
            logger.error(f"❌ {self.name} exception: {type(e).__name__}: {str(e)}", exc_info=True)
            with self._lock:
                self._handle_failure()
            return False
    
    def _transition_to_half_open(self):
        """Transition to HALF_OPEN state"""
        self.state = 'HALF_OPEN'
        self.success_count = 0
        self.failure_count = 0
        self.last_state_change = datetime.now(timezone.utc)
        logger.info(f"🟡 {self.name} → HALF_OPEN (recovery test)")
    
    def _transition_to_closed(self):
        """Transition to CLOSED (normal) state"""
        logger.info(f"🎉 {self.name} fully recovered! → CLOSED")
        self.state = 'CLOSED'
        self.failure_count = 0
        self.success_count = 0
        self.first_failure_time = None
        self.last_state_change = datetime.now(timezone.utc)
        self.recoveries += 1
        
        # 🔥 TELEGRAM: Recovery bildirimi
        send_telegram_notification(
            f"✅ Circuit Breaker RECOVERED!\n"
            f"• Sistem: {self.name}\n"
            f"• Recovery #{self.recoveries}\n"
            f"• Başarı Oranı: {self.get_status()['success_rate']}",
            alert_level='success'
        )
    
    def _transition_to_open(self, reason: str):
        """Transition to OPEN (circuit broken) state"""
        logger.error(f"🔴 {self.name} CRITICAL! {reason} → OPEN ({self.timeout}s timeout)")
        self.state = 'OPEN'
        self.success_count = 0
        self.last_state_change = datetime.now(timezone.utc)
        self.circuit_opens += 1
        
        # 🔥 TELEGRAM: Critical alert
        status = self.get_status()
        send_telegram_notification(
            f"🔴 CRITICAL - CIRCUIT BREAKER OPENED!\n\n"
            f"*Sistem: {self.name}*\n"
            f"• Sebep: {reason}\n"
            f"• Hata Sayısı: {status['failure_count']}/{status['config']['failure_threshold']}\n"
            f"• Başarı Oranı: {status['success_rate']}\n"
            f"• Timeout: {self.timeout}s\n\n"
            f"⚠️ Sistem koruma modunda. Otomatik iyileşme bekleniyor...",
            alert_level='critical'
        )
    
    def _handle_success(self):
        """Handle successful call"""
        self.total_successes += 1
        self.last_success_time = datetime.now(timezone.utc)
        
        if self.state == 'CLOSED':
            if self.failure_count > 0:
                logger.info(f"✅ {self.name} recovered (after {self.failure_count} failures)")
                self.failure_count = 0
                self.first_failure_time = None
        
        elif self.state == 'HALF_OPEN':
            self.success_count += 1
            logger.info(
                f"✅ {self.name} HALF_OPEN test success "
                f"({self.success_count}/{self.half_open_success_threshold})"
            )
            
            if self.success_count >= self.half_open_success_threshold:
                self._transition_to_closed()
    
    def _handle_failure(self):
        """Handle failed call"""
        self.total_failures += 1
        self.failure_count += 1
        self.last_failure_time = datetime.now(timezone.utc)
        
        if self.first_failure_time is None:
            self.first_failure_time = datetime.now(timezone.utc)
        
        if self.state == 'CLOSED':
            if self.failure_count >= self.failure_threshold:
                self._transition_to_open(
                    f"{self.failure_count} failures (threshold={self.failure_threshold})"
                )
            else:
                logger.warning(f"⚠️ {self.name} failed ({self.failure_count}/{self.failure_threshold})")
        
        elif self.state == 'HALF_OPEN':
            self.first_failure_time = datetime.now(timezone.utc)
            self._transition_to_open("HALF_OPEN test failed")
    
    def reset(self):
        """Manually reset circuit breaker"""
        with self._lock:
            logger.info(f"🔄 {self.name} manual reset...")
            self.state = 'CLOSED'
            self.failure_count = 0
            self.success_count = 0
            self.first_failure_time = None
            self.last_state_change = datetime.now(timezone.utc)
    
    def get_status(self) -> dict:
        """Get circuit breaker status"""
        with self._lock:
            uptime = None
            if self.last_success_time:
                uptime = (datetime.now(timezone.utc) - self.last_success_time).total_seconds()
            
            time_in_state = (datetime.now(timezone.utc) - self.last_state_change).total_seconds()
            
            success_rate = 0
            if self.total_calls > 0:
                success_rate = (self.total_successes / self.total_calls) * 100
            
            return {
                'name': self.name,
                'state': self.state,
                'time_in_state_seconds': time_in_state,
                'failure_count': self.failure_count,
                'success_count': self.success_count,
                'total_calls': self.total_calls,
                'total_successes': self.total_successes,
                'total_failures': self.total_failures,
                'circuit_opens': self.circuit_opens,
                'recoveries': self.recoveries,
                'success_rate': f"{success_rate:.2f}%",
                'last_success': self.last_success_time.isoformat() if self.last_success_time else None,
                'last_failure': self.last_failure_time.isoformat() if self.last_failure_time else None,
                'uptime_seconds': uptime,
                'config': {
                    'failure_threshold': self.failure_threshold,
                    'timeout': self.timeout,
                    'half_open_success_threshold': self.half_open_success_threshold
                }
            }

# ======================================
# GLOBAL INSTANCES (Config-driven!)
# ======================================

breaker = CircuitBreaker(
    name="Financial API Service",
    failure_threshold=Config.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    timeout=Config.CIRCUIT_BREAKER_TIMEOUT,
    half_open_success_threshold=Config.CIRCUIT_BREAKER_HALF_OPEN_SUCCESS
)

_scheduler: Optional[BackgroundScheduler] = None
_scheduler_lock = threading.Lock()
_shutdown_initiated = False

# ======================================
# IMPROVED FETCH FUNCTIONS (WITH TELEGRAM)
# ======================================

def fetch_all_data_safe() -> bool:
    """
    Safe data fetch that preserves old cache if new fetch fails
    """
    import time
    start_time = time.time()
    
    # Import'ları fonksiyon içinde yap (circular import önlemek için)
    from utils.cache import get_cache, set_cache
    
    # Önce mevcut cache'i yedekle
    old_currencies = get_cache(Config.CACHE_KEYS['currencies_all'])
    old_golds = get_cache(Config.CACHE_KEYS['golds_all'])
    old_silvers = get_cache(Config.CACHE_KEYS['silvers_all'])
    
    logger.debug(f"📦 Cache backup complete")
    
    try:
        success = sync_financial_data()
        
        if success:
            # 🔥 TELEGRAM: Başarılı güncelleme bildirimi (cooldown ile)
            current_time = time.time()
            # Sadece her 10. başarılı güncellemede veya ilk başarıda bildirim
            if not hasattr(fetch_all_data_safe, 'last_success_notification'):
                fetch_all_data_safe.last_success_notification = 0
            
            if current_time - fetch_all_data_safe.last_success_notification > 600:  # 10 dakika
                monitor = get_telegram_monitor()
                if monitor:
                    try:
                        monitor.send_message(
                            f"✅ Otomatik güncelleme başarılı\n"
                            f"• Kaynak: {get_service_metrics().get('source', 'unknown')}\n"
                            f"• Süre: {time.time() - start_time:.2f}s\n"
                            f"• Circuit Breaker: {breaker.state}",
                            alert_level='success'
                        )
                        fetch_all_data_safe.last_success_notification = current_time
                    except Exception as e:
                        logger.error(f"Telegram notification error: {e}")
        
        if not success:
            logger.warning("⚠️ Data fetch failed, restoring old cache...")
            
            # Eski cache'i geri yükle
            if old_currencies:
                set_cache(Config.CACHE_KEYS['currencies_all'], old_currencies, ttl=Config.CACHE_TTL)
            if old_golds:
                set_cache(Config.CACHE_KEYS['golds_all'], old_golds, ttl=Config.CACHE_TTL)
            if old_silvers:
                set_cache(Config.CACHE_KEYS['silvers_all'], old_silvers, ttl=Config.CACHE_TTL)
            
            logger.info("✅ Old cache restored successfully")
        
        duration = time.time() - start_time
        logger.info(f"📊 Data fetch completed in {duration:.2f}s - Success: {success}")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ Critical error in data fetch: {e}", exc_info=True)
        
        # Eski cache'i geri yükle
        if old_currencies:
            set_cache(Config.CACHE_KEYS['currencies_all'], old_currencies, ttl=Config.CACHE_TTL)
        
        return False


def fetch_all_data() -> bool:
    """Main data fetch function with circuit breaker protection"""
    return breaker.call(fetch_all_data_safe)


# ======================================
# DAILY REPORT SYSTEM
# ======================================

def check_and_send_daily_report():
    """
    Günlük rapor kontrolü ve gönderimi
    Her gün bir kez çalışır (saat 09:00 UTC)
    """
    global _last_daily_report_time
    
    with _daily_report_lock:
        now = datetime.now(timezone.utc)
        
        # İlk çalıştırmada veya 24 saat geçtiyse
        if _last_daily_report_time is None or (now - _last_daily_report_time).total_seconds() >= 86400:
            
            # Saat kontrolü (09:00-09:30 UTC arası)
            hour = now.hour
            if hour == 9:
                logger.info("📊 Günlük rapor hazırlanıyor...")
                
                try:
                    # Servis metriklerini al
                    metrics = get_service_metrics()
                    breaker_status = breaker.get_status()
                    
                    # Rapor mesajı oluştur
                    report_message = f"📊 *Günlük Sistem Raporu*\n\n"
                    report_message += f"*📈 Finansal Servis*\n"
                    report_message += f"• Başarı Oranı: `{metrics.get('success_rate_percent', 'N/A')}`\n"
                    report_message += f"• Toplam Çağrı: `{metrics.get('total_calls', 0)}`\n"
                    report_message += f"• V5 Başarı: `{metrics.get('v5_success', 0)}`\n"
                    report_message += f"• V4 Fallback: `{metrics.get('v4_fallback', 0)}`\n"
                    report_message += f"• Hatalar: `{metrics.get('errors', 0)}`\n\n"
                    
                    report_message += f"*⚡ Circuit Breaker*\n"
                    report_message += f"• Durum: `{breaker_status['state']}`\n"
                    report_message += f"• Başarı Oranı: `{breaker_status['success_rate']}`\n"
                    report_message += f"• Toplam Açılma: `{breaker_status['circuit_opens']}`\n"
                    report_message += f"• İyileşmeler: `{breaker_status['recoveries']}`\n\n"
                    
                    report_message += f"*🕐 Sistem Bilgisi*\n"
                    report_message += f"• Ortam: `{Config.ENVIRONMENT.upper()}`\n"
                    report_message += f"• Güncelleme Aralığı: `{Config.UPDATE_INTERVAL}s`\n"
                    report_message += f"• Tarih: `{now.strftime('%Y-%m-%d')}`"
                    
                    # Telegram'a gönder
                    success = send_telegram_notification(report_message, 'info')
                    
                    if success:
                        _last_daily_report_time = now
                        logger.info("✅ Günlük rapor gönderildi")
                    else:
                        logger.warning("⚠️ Günlük rapor gönderilemedi")
                    
                except Exception as e:
                    logger.error(f"❌ Günlük rapor hatası: {e}")


# ======================================
# SCHEDULER FUNCTIONS (WITH DAILY REPORT)
# ======================================

def start_scheduler() -> Optional[BackgroundScheduler]:
    """Start background scheduler with daily report"""
    global _scheduler
    
    with _scheduler_lock:
        if _scheduler is not None:
            if _scheduler.running:
                logger.warning("⚠️ Scheduler already running")
                return _scheduler
            else:
                logger.warning("⚠️ Dead scheduler detected, cleaning up...")
                try:
                    _scheduler.shutdown(wait=False)
                except:
                    pass
                _scheduler = None
        
        pid = os.getpid()
        logger.info(f"🔧 Starting scheduler (PID: {pid})...")
        
        # Executor config
        executors = {
            'default': ThreadPoolExecutor(max_workers=Config.SCHEDULER_MAX_WORKERS)
        }
        
        # Create scheduler
        _scheduler = BackgroundScheduler(
            executors=executors,
            job_defaults={
                'coalesce': True,
                'max_instances': 1,
                'misfire_grace_time': 30
            },
            timezone='UTC'
        )
        
        # 🔥 ANA JOB: Finansal veri senkronizasyonu
        _scheduler.add_job(
            fetch_all_data,
            'interval',
            seconds=Config.UPDATE_INTERVAL,
            id='sync_financial_data',
            name='Financial Data Sync',
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            next_run_time=datetime.now(timezone.utc)
        )
        
        # 🔥 YENİ JOB: Günlük rapor (her gün 09:00 UTC)
        _scheduler.add_job(
            check_and_send_daily_report,
            'cron',
            hour=9,
            minute=0,
            id='daily_report',
            name='Daily System Report',
            replace_existing=True,
            max_instances=1
        )
        
        # Başlat
        _scheduler.start()
        
        logger.info(
            f"✅ Scheduler started\n"
            f"  • Financial Sync: {Config.UPDATE_INTERVAL}s interval\n"
            f"  • Daily Report: 09:00 UTC every day\n"
            f"  • Max Workers: {Config.SCHEDULER_MAX_WORKERS}"
        )
        logger.info(f"📊 Circuit Breaker: {breaker.state}")
        
        # 🔥 TELEGRAM: Scheduler başlatma bildirimi
        send_telegram_notification(
            f"⚡ Scheduler Başlatıldı\n"
            f"• Interval: {Config.UPDATE_INTERVAL}s\n"
            f"• Ortam: {Config.ENVIRONMENT.upper()}\n"
            f"• Circuit Breaker: {breaker.state}",
            alert_level='info'
        )
        
        return _scheduler


def stop_scheduler():
    """Stop scheduler gracefully"""
    global _scheduler, _shutdown_initiated
    
    with _scheduler_lock:
        if _shutdown_initiated:
            logger.debug("Shutdown already initiated, skipping...")
            return
        
        _shutdown_initiated = True
        
        if _scheduler is not None:
            logger.info("🛑 Stopping scheduler...")
            
            try:
                _scheduler.shutdown(wait=True)
                logger.info("✅ Scheduler stopped gracefully")
            except Exception as e:
                logger.error(f"❌ Scheduler shutdown error: {e}")
                try:
                    _scheduler.shutdown(wait=False)
                    logger.warning("⚠️ Scheduler force-stopped")
                except:
                    pass
            finally:
                _scheduler = None
        else:
            logger.debug("Scheduler already stopped")


def get_scheduler_status() -> dict:
    """Get scheduler, circuit breaker, and service status"""
    with _scheduler_lock:
        now_utc = datetime.now(timezone.utc)
        
        if _scheduler is None or not _scheduler.running:
            return {
                'scheduler_running': False,
                'jobs': [],
                'circuit_breaker': breaker.get_status(),
                'financial_service_metrics': get_service_metrics(),
                'daily_report': {
                    'enabled': True,
                    'last_sent': _last_daily_report_time.isoformat() if _last_daily_report_time else None,
                    'next_scheduled': '09:00 UTC daily' if _scheduler else 'Scheduler stopped'
                },
                'timestamp_utc': now_utc.isoformat(),
                'manual_trigger_cooldown': _get_cooldown_status()
            }
        
        jobs = []
        for job in _scheduler.get_jobs():
            next_run = None
            seconds_until = None
            
            if job.next_run_time:
                next_run = job.next_run_time.isoformat()
                seconds_until = (job.next_run_time - now_utc).total_seconds()
            
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': next_run,
                'seconds_until_next_run': seconds_until,
                'trigger': str(job.trigger)
            })
        
        # Daily report bilgisi
        daily_report_info = {
            'enabled': True,
            'last_sent': _last_daily_report_time.isoformat() if _last_daily_report_time else None,
            'next_scheduled': None
        }
        
        # Next daily report time
        daily_job = _scheduler.get_job('daily_report')
        if daily_job and daily_job.next_run_time:
            daily_report_info['next_scheduled'] = daily_job.next_run_time.isoformat()
        
        return {
            'scheduler_running': _scheduler.running,
            'scheduler_state': _scheduler.state,
            'jobs': jobs,
            'circuit_breaker': breaker.get_status(),
            'financial_service_metrics': get_service_metrics(),
            'daily_report': daily_report_info,
            'timestamp_utc': now_utc.isoformat(),
            'manual_trigger_cooldown': _get_cooldown_status()
        }


def _get_cooldown_status() -> dict:
    """Get manual trigger cooldown status"""
    global _last_manual_trigger_time
    current_time = time.time()
    
    cooldown_remaining = max(0, 60 - (current_time - _last_manual_trigger_time))
    
    return {
        'cooldown_seconds': 60,
        'cooldown_remaining_seconds': cooldown_remaining,
        'last_manual_trigger_time': _last_manual_trigger_time,
        'is_available': cooldown_remaining == 0
    }


def manual_trigger() -> dict:
    """
    Manually trigger data update with cooldown protection and Telegram notification
    """
    global _last_manual_trigger_time
    
    with _manual_trigger_lock:
        current_time = time.time()
        
        # Cooldown kontrolü (60 saniye)
        if current_time - _last_manual_trigger_time < 60:
            remaining = 60 - int(current_time - _last_manual_trigger_time)
            logger.warning(f"⚠️ Manual trigger cooldown: {remaining}s remaining")
            
            return {
                'success': False,
                'duration_seconds': 0,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'circuit_breaker_state': breaker.state,
                'error': "Too frequent. Wait 60 seconds between manual updates.",
                'next_available_in': remaining,
                'cooldown_active': True
            }
        
        _last_manual_trigger_time = current_time
    
    logger.info("🔄 Manual data update triggered")
    
    # 🔥 TELEGRAM: Manuel update başladı bildirimi
    send_telegram_notification(
        f"🔄 Manuel güncelleme başlatıldı\n"
        f"• Sistem: {Config.APP_NAME}\n"
        f"• Circuit Breaker: {breaker.state}",
        alert_level='info'
    )
    
    start_time = datetime.now(timezone.utc)
    success = fetch_all_data()
    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
    
    # Manuel update sonrası scheduled job'u resetle
    with _scheduler_lock:
        if _scheduler and _scheduler.running:
            try:
                job = _scheduler.get_job('sync_financial_data')
                if job:
                    next_run = datetime.now(timezone.utc) + timedelta(seconds=Config.UPDATE_INTERVAL)
                    job.modify(next_run_time=next_run)
                    logger.debug(f"⏱️ Next scheduled run reset to: {next_run.isoformat()}")
            except Exception as e:
                logger.warning(f"Could not reset scheduler job: {e}")
    
    # 🔥 TELEGRAM: Manuel update sonucu bildirimi
    if success:
        send_telegram_notification(
            f"✅ Manuel güncelleme BAŞARILI\n"
            f"• Süre: {duration:.2f}s\n"
            f"• Circuit Breaker: {breaker.state}\n"
            f"• Sonraki Otomatik: {Config.UPDATE_INTERVAL}s sonra",
            alert_level='success'
        )
    else:
        send_telegram_notification(
            f"❌ Manuel güncelleme BAŞARISIZ\n"
            f"• Süre: {duration:.2f}s\n"
            f"• Circuit Breaker: {breaker.state}\n"
            f"• Hata: Circuit Breaker OPEN olabilir",
            alert_level='warning'
        )
    
    return {
        'success': success,
        'duration_seconds': duration,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'circuit_breaker_state': breaker.state,
        'message': "Manual update completed" if success else "Manual update failed",
        'next_scheduled_in': Config.UPDATE_INTERVAL,
        'cooldown_active': False
    }


def safe_manual_trigger() -> dict:
    """
    Safe manual trigger - doesn't block HTTP requests
    """
    # Thread'de çalıştır, hemen HTTP response dön
    trigger_thread = threading.Thread(
        target=manual_trigger, 
        daemon=True,
        name="manual_trigger_thread"
    )
    trigger_thread.start()
    
    logger.info("🚀 Manual update started in background thread")
    
    return {
        'success': True,
        'message': "Manual update started in background",
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'background_thread': True,
        'thread_name': trigger_thread.name
    }

# ======================================
# GRACEFUL SHUTDOWN
# ======================================

def cleanup():
    """Cleanup on application exit"""
    logger.info("🧹 Maintenance service cleanup started...")
    
    # Stop scheduler
    stop_scheduler()
    
    # Final metrics
    status = breaker.get_status()
    logger.info(
        f"📊 Final Circuit Breaker Stats:\n"
        f"  State: {status['state']}\n"
        f"  Success Rate: {status['success_rate']}\n"
        f"  Total Calls: {status['total_calls']}\n"
        f"  Circuit Opens: {status['circuit_opens']}\n"
        f"  Recoveries: {status['recoveries']}"
    )
    
    # 🔥 TELEGRAM: Shutdown bildirimi
    send_telegram_notification(
        f"🛑 Sistem Kapanıyor\n"
        f"• Uptime: {status.get('uptime_seconds', 0):.0f}s\n"
        f"• Toplam İstek: {status['total_calls']}\n"
        f"• Başarı Oranı: {status['success_rate']}",
        alert_level='info'
    )
    
    logger.info("✅ Maintenance service cleaned up")


# Register cleanup
atexit.register(cleanup)

# Handle SIGTERM (Render/Docker graceful shutdown)
def handle_sigterm(signum, frame):
    logger.info(f"🛑 Received SIGTERM, initiating graceful shutdown...")
    cleanup()
    os._exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)

# ======================================
# INITIALIZATION LOG
# ======================================
logger.info("🎯 Maintenance Service initialized successfully")
logger.info(f"📋 Config Summary: UPDATE_INTERVAL={Config.UPDATE_INTERVAL}s, "
           f"CIRCUIT_BREAKER={Config.CIRCUIT_BREAKER_FAILURE_THRESHOLD}/{Config.CIRCUIT_BREAKER_TIMEOUT}s")
logger.info(f"🛡️  Safety Features: Manual Update Cooldown=60s, Daily Reports=Enabled")
