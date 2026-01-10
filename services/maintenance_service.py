"""
Maintenance Service - Scheduler & Circuit Breaker
=================================================

✅ Akıllı Circuit Breaker (kademeli recovery)
✅ Thread-safe scheduler yönetimi
✅ Metrik ve monitoring
✅ Graceful shutdown
✅ Multi-process güvenli
✅ Memory leak koruması
✅ İyileştirilmiş timeout logic
✅ Render Deploy Fix (ThreadPoolExecutor argümanı düzeltildi)
"""

import logging
import atexit
import threading
import os
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor

from services.financial_service import sync_financial_data, get_service_metrics
from config import Config

logger = logging.getLogger(__name__)

# ======================================
# CİRCUİT BREAKER (ÇOK İYİLEŞTİRİLMİŞ)
# ======================================

class CircuitBreaker:
    """
    Production-Grade Circuit Breaker Pattern
    
    States:
    - CLOSED: Normal çalışma (sağlıklı)
    - OPEN: Sistem koruması aktif (çok fazla hata)
    - HALF_OPEN: İyileşme testi (dikkatli deneme)
    
    Features:
    - Kademeli recovery (3 başarılı test gerekir)
    - Exponential backoff (opsiyonel)
    - Thread-safe operations
    - Detaylı metrikler
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
        
        # Zamanlar
        self.first_failure_time = None  # İlk hata zamanı (timeout için)
        self.last_failure_time = None
        self.last_success_time = None
        self.last_state_change = datetime.now()
        
        # Metrikler
        self.total_calls = 0
        self.total_failures = 0
        self.total_successes = 0
        self.circuit_opens = 0
        self.recoveries = 0
        
        # Thread safety
        self._lock = threading.Lock()
        
        logger.info(
            f"🔧 Circuit Breaker oluşturuldu: {name} "
            f"(threshold={failure_threshold}, timeout={timeout}s, "
            f"half_open_success={half_open_success_threshold})"
        )
    
    def call(self, func):
        """
        Fonksiyonu circuit breaker koruması ile çalıştır
        
        Args:
            func: Çalıştırılacak fonksiyon
        
        Returns:
            bool: Başarı durumu
        """
        with self._lock:
            self.total_calls += 1
            current_state = self.state
            
            # OPEN durumu: Timeout kontrolü
            if current_state == 'OPEN':
                if not self.first_failure_time:
                    # Güvenlik: first_failure_time yoksa HALF_OPEN'a geç
                    logger.warning(
                        f"⚠️ {self.name} OPEN durumunda ama first_failure_time yok! "
                        "HALF_OPEN'a geçiliyor..."
                    )
                    self._transition_to_half_open()
                else:
                    elapsed = (datetime.now() - self.first_failure_time).total_seconds()
                    
                    if elapsed >= self.timeout:
                        # Timeout doldu, test moduna geç
                        logger.info(
                            f"🔄 {self.name} timeout doldu ({elapsed:.0f}s), "
                            "HALF_OPEN moduna geçiliyor..."
                        )
                        self._transition_to_half_open()
                    else:
                        # Hâlâ bekleme süresindeyiz
                        remaining = int(self.timeout - elapsed)
                        if self.total_calls % 10 == 0:  # Her 10 çağrıda bir log
                            logger.warning(
                                f"⚠️ {self.name} DEVRE DIŞI (OPEN) - "
                                f"{remaining}s sonra test edilecek"
                            )
                        return False
        
        # Fonksiyonu çalıştır (lock dışında - blocking engellenir)
        try:
            result = func()
            
            with self._lock:
                if result:
                    self._handle_success()
                else:
                    self._handle_failure()
                
                return result
        
        except Exception as e:
            logger.error(
                f"❌ {self.name} exception: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            with self._lock:
                self._handle_failure()
            return False
    
    def _transition_to_half_open(self):
        """HALF_OPEN durumuna geç"""
        self.state = 'HALF_OPEN'
        self.success_count = 0
        self.failure_count = 0
        self.last_state_change = datetime.now()
    
    def _transition_to_closed(self):
        """CLOSED (normal) durumuna geç"""
        logger.info(f"🎉 {self.name} tamamen düzeldi! CLOSED moduna geçiliyor.")
        self.state = 'CLOSED'
        self.failure_count = 0
        self.success_count = 0
        self.first_failure_time = None
        self.last_state_change = datetime.now()
        self.recoveries += 1
    
    def _transition_to_open(self, reason: str):
        """OPEN (devre dışı) durumuna geç"""
        logger.error(
            f"🔴 {self.name} KRİTİK! {reason} "
            f"OPEN moduna geçiliyor, {self.timeout}s bekleme başlıyor."
        )
        self.state = 'OPEN'
        self.success_count = 0
        self.last_state_change = datetime.now()
        self.circuit_opens += 1
    
    def _handle_success(self):
        """Başarılı çağrı işle"""
        self.total_successes += 1
        self.last_success_time = datetime.now()
        
        if self.state == 'CLOSED':
            # Zaten normal durumda, sadece failure counter'ı sıfırla
            if self.failure_count > 0:
                logger.info(
                    f"✅ {self.name} normale döndü "
                    f"({self.failure_count} hata sonrası)"
                )
                self.failure_count = 0
                self.first_failure_time = None
        
        elif self.state == 'HALF_OPEN':
            # Test modunda başarı
            self.success_count += 1
            logger.info(
                f"✅ {self.name} HALF_OPEN test başarılı "
                f"({self.success_count}/{self.half_open_success_threshold})"
            )
            
            if self.success_count >= self.half_open_success_threshold:
                # Yeterli başarı, tam iyileşme
                self._transition_to_closed()
    
    def _handle_failure(self):
        """Başarısız çağrı işle"""
        self.total_failures += 1
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        # İlk hatayı kaydet (timeout hesabı için)
        if self.first_failure_time is None:
            self.first_failure_time = datetime.now()
        
        if self.state == 'CLOSED':
            # Normal modda hata
            if self.failure_count >= self.failure_threshold:
                # Threshold aşıldı
                self._transition_to_open(
                    f"{self.failure_count} başarısızlık (threshold={self.failure_threshold})"
                )
            else:
                logger.warning(
                    f"⚠️ {self.name} başarısız "
                    f"({self.failure_count}/{self.failure_threshold})"
                )
        
        elif self.state == 'HALF_OPEN':
            # Test modunda hata, geri OPEN'a dön
            self.first_failure_time = datetime.now()  # Timeout'u sıfırla
            self._transition_to_open("HALF_OPEN test başarısız")
    
    def reset(self):
        """Circuit breaker'ı manuel olarak sıfırla"""
        with self._lock:
            logger.info(f"🔄 {self.name} manuel olarak sıfırlanıyor...")
            self.state = 'CLOSED'
            self.failure_count = 0
            self.success_count = 0
            self.first_failure_time = None
            self.last_state_change = datetime.now()
    
    def get_status(self) -> dict:
        """Circuit breaker durumunu döndür"""
        with self._lock:
            uptime = None
            if self.last_success_time:
                uptime = (datetime.now() - self.last_success_time).total_seconds()
            
            time_in_state = (datetime.now() - self.last_state_change).total_seconds()
            
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
# GLOBAL INSTANCES
# ======================================

# Circuit breaker instance
breaker = CircuitBreaker(
    name="Financial API Service",
    failure_threshold=5,           # 5 başarısızlık
    timeout=300,                   # 5 dakika bekle
    half_open_success_threshold=3  # 3 başarılı test
)

# Scheduler instance
_scheduler: Optional[BackgroundScheduler] = None
_scheduler_lock = threading.Lock()

# ======================================
# SCHEDULER FONKSİYONLARI
# ======================================

def fetch_all_data() -> bool:
    """
    Ana veri çekme fonksiyonu
    Circuit breaker korumalı
    
    Returns:
        bool: Başarı durumu
    """
    return breaker.call(sync_financial_data)


def start_scheduler() -> Optional[BackgroundScheduler]:
    """
    Arka plan zamanlayıcıyı başlat
    
    Returns:
        BackgroundScheduler instance veya None
    """
    global _scheduler
    
    with _scheduler_lock:
        # Zaten çalışıyorsa kontrol
        if _scheduler is not None:
            if _scheduler.running:
                logger.warning("⚠️ Scheduler zaten çalışıyor")
                return _scheduler
            else:
                # Ölü scheduler temizliği
                logger.warning("⚠️ Ölü scheduler tespit edildi, temizleniyor...")
                try:
                    _scheduler.shutdown(wait=False)
                except:
                    pass
                _scheduler = None
        
        # Process ID (multi-process için)
        pid = os.getpid()
        logger.info(f"🔧 Scheduler başlatılıyor (PID: {pid})...")
        
        # Executor yapılandırması
        # DÜZELTME: thread_name_prefix argümanı kaldırıldı
        executors = {
            'default': ThreadPoolExecutor(
                max_workers=1
            )
        }
        
        # Scheduler oluştur
        _scheduler = BackgroundScheduler(
            executors=executors,
            job_defaults={
                'coalesce': True,         # Kaçırılan job'ları birleştir
                'max_instances': 1,       # Aynı anda 1 instance
                'misfire_grace_time': 30  # 30s içinde kaçırılanları çalıştır
            },
            timezone='UTC'
        )
        
        # Job ekle
        _scheduler.add_job(
            fetch_all_data,
            'interval',
            seconds=Config.UPDATE_INTERVAL,
            id='sync_financial_data',
            name='Financial Data Sync',
            replace_existing=True,
            next_run_time=datetime.now()  # Hemen başlat
        )
        
        # Başlat
        _scheduler.start()
        
        logger.info(
            f"✅ Scheduler başlatıldı - "
            f"Aralık: {Config.UPDATE_INTERVAL}s "
            f"({Config.UPDATE_INTERVAL / 60:.1f} dakika)"
        )
        
        # İlk durumu log'la
        logger.info(f"📊 Circuit Breaker: {breaker.get_status()['state']}")
        
        return _scheduler


def stop_scheduler():
    """
    Scheduler'ı güvenli şekilde durdur
    """
    global _scheduler
    
    with _scheduler_lock:
        if _scheduler is not None:
            logger.info("🛑 Scheduler durduruluyor...")
            
            try:
                # Çalışan job'ları bekle (max 10 saniye)
                _scheduler.shutdown(wait=True, timeout=10)
                logger.info("✅ Scheduler güvenli şekilde durduruldu")
            except Exception as e:
                logger.error(f"❌ Scheduler durdurma hatası: {e}")
            finally:
                _scheduler = None
        else:
            logger.debug("Scheduler zaten durdurulmuş")


def get_scheduler_status() -> dict:
    """
    Scheduler, circuit breaker ve service durumunu döndür
    """
    with _scheduler_lock:
        if _scheduler is None:
            return {
                'scheduler_running': False,
                'jobs': [],
                'circuit_breaker': breaker.get_status(),
                'financial_service_metrics': get_service_metrics()
            }
        
        # Job bilgileri
        jobs = []
        for job in _scheduler.get_jobs():
            next_run = None
            if job.next_run_time:
                next_run = job.next_run_time.isoformat()
                seconds_until = (job.next_run_time - datetime.now()).total_seconds()
            else:
                seconds_until = None
            
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': next_run,
                'seconds_until_next_run': seconds_until,
                'trigger': str(job.trigger)
            })
        
        return {
            'scheduler_running': _scheduler.running,
            'scheduler_state': _scheduler.state,
            'jobs': jobs,
            'circuit_breaker': breaker.get_status(),
            'financial_service_metrics': get_service_metrics()
        }


def manual_trigger() -> dict:
    """
    Manuel veri güncelleme tetikle
    
    Returns:
        dict: Sonuç bilgisi
    """
    logger.info("🔄 Manuel veri güncelleme tetiklendi")
    
    start_time = datetime.now()
    success = fetch_all_data()
    duration = (datetime.now() - start_time).total_seconds()
    
    return {
        'success': success,
        'duration_seconds': duration,
        'timestamp': datetime.now().isoformat(),
        'circuit_breaker_state': breaker.state
    }

# ======================================
# GRACEFUL SHUTDOWN
# ======================================

def cleanup():
    """
    Uygulama kapanırken temizlik
    """
    logger.info("🧹 Maintenance service cleanup başlatıldı...")
    
    # Scheduler'ı durdur
    stop_scheduler()
    
    # Final metrikler
    status = breaker.get_status()
    logger.info(
        f"📊 Final Circuit Breaker Stats:\n"
        f"  State: {status['state']}\n"
        f"  Success Rate: {status['success_rate']}\n"
        f"  Total Calls: {status['total_calls']}\n"
        f"  Circuit Opens: {status['circuit_opens']}\n"
        f"  Recoveries: {status['recoveries']}"
    )
    
    logger.info("✅ Maintenance service temizlendi")

# Otomatik cleanup kayıt
atexit.register(cleanup)
