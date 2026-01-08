"""
Maintenance Service - Scheduler & Circuit Breaker
=================================================

Özellikler:
✅ Akıllı Circuit Breaker (kademeli recovery)
✅ Thread-safe scheduler yönetimi
✅ Metrik ve monitoring
✅ Graceful shutdown
✅ Multi-process güvenli
✅ Detaylı loglama
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
# CİRCUİT BREAKER (İYİLEŞTİRİLMİŞ)
# ======================================

class CircuitBreaker:
    """
    Gelişmiş Circuit Breaker Pattern
    
    States:
    - CLOSED: Normal çalışma (başarılı)
    - OPEN: Sistem koruması aktif (çok fazla hata)
    - HALF_OPEN: Test modu (iyileşme kontrolü)
    
    Features:
    - Kademeli recovery (HALF_OPEN'da 3 başarı gerekir)
    - İlk hata zamanı korunur
    - Thread-safe
    """
    
    def __init__(self, name: str, failure_threshold: int = 5, timeout: int = 300, half_open_success_threshold: int = 3):
        self.name = name
        self.failure_threshold = failure_threshold
        self.timeout = timeout  # Saniye cinsinden bekleme süresi
        self.half_open_success_threshold = half_open_success_threshold
        
        # State
        self.state = 'CLOSED'
        self.failure_count = 0
        self.success_count = 0
        
        # Zamanlar
        self.first_failure_time = None  # ✅ İLK hata zamanı (timeout için)
        self.last_failure_time = None
        self.last_success_time = None
        
        # Metrikler
        self.total_calls = 0
        self.total_failures = 0
        self.circuit_opens = 0
        
        # Thread safety
        self._lock = threading.Lock()
    
    def call(self, func):
        """
        Fonksiyonu circuit breaker ile çalıştır
        
        Args:
            func: Çalıştırılacak fonksiyon (sync_financial_data)
        
        Returns:
            bool: Başarı durumu
        """
        with self._lock:
            self.total_calls += 1
            
            # OPEN durumu: Timeout kontrolü
            if self.state == 'OPEN':
                if not self.first_failure_time:
                    # Hata: first_failure_time set edilmemiş
                    logger.error("❌ Circuit breaker OPEN ama first_failure_time yok!")
                    self.state = 'HALF_OPEN'
                    self.success_count = 0
                else:
                    elapsed = (datetime.now() - self.first_failure_time).total_seconds()
                    
                    if elapsed >= self.timeout:
                        # Timeout doldu, test moduna geç
                        logger.info(f"🔄 {self.name} timeout doldu, HALF_OPEN moduna geçiliyor...")
                        self.state = 'HALF_OPEN'
                        self.success_count = 0
                    else:
                        # Hâlâ bekliyoruz
                        remaining = int(self.timeout - elapsed)
                        logger.warning(
                            f"⚠️ {self.name} DEVRE DIŞI (OPEN) - "
                            f"{remaining}s sonra tekrar denenecek"
                        )
                        return False
        
        # Fonksiyonu çalıştır (lock dışında, blocking olmaması için)
        try:
            result = func()
            
            with self._lock:
                if result:
                    self._handle_success()
                    return True
                else:
                    self._handle_failure()
                    return False
        
        except Exception as e:
            logger.error(f"❌ {self.name} exception: {type(e).__name__}: {str(e)}")
            with self._lock:
                self._handle_failure()
            return False
    
    def _handle_success(self):
        """Başarılı çağrı işle"""
        self.last_success_time = datetime.now()
        
        if self.state == 'CLOSED':
            # Zaten normal durumda
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
                # Yeterli başarı, normal moda dön
                logger.info(f"🎉 {self.name} tamamen düzeldi! CLOSED moduna geçiliyor.")
                self.state = 'CLOSED'
                self.failure_count = 0
                self.success_count = 0
                self.first_failure_time = None
    
    def _handle_failure(self):
        """Başarısız çağrı işle"""
        self.total_failures += 1
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        # İlk hatayı kaydet (timeout için)
        if self.first_failure_time is None:
            self.first_failure_time = datetime.now()
        
        if self.state == 'CLOSED':
            # Normal modda hata
            if self.failure_count >= self.failure_threshold:
                # Threshold aşıldı, devre aç
                logger.error(
                    f"🔴 {self.name} KRİTİK HATA! "
                    f"{self.failure_count} başarısızlıktan sonra OPEN moduna geçiliyor. "
                    f"{self.timeout}s boyunca istekler durdurulacak."
                )
                self.state = 'OPEN'
                self.circuit_opens += 1
            else:
                logger.warning(
                    f"⚠️ {self.name} başarısız "
                    f"({self.failure_count}/{self.failure_threshold})"
                )
        
        elif self.state == 'HALF_OPEN':
            # Test modunda hata, geri OPEN'a geç
            logger.error(
                f"🔴 {self.name} HALF_OPEN test başarısız! "
                f"Tekrar OPEN moduna geçiliyor ({self.timeout}s)"
            )
            self.state = 'OPEN'
            self.success_count = 0
            self.first_failure_time = datetime.now()  # Timeout'u sıfırla
            self.circuit_opens += 1
    
    def get_status(self) -> dict:
        """Circuit breaker durumunu döndür"""
        with self._lock:
            uptime = None
            if self.last_success_time:
                uptime = (datetime.now() - self.last_success_time).total_seconds()
            
            return {
                'name': self.name,
                'state': self.state,
                'failure_count': self.failure_count,
                'total_calls': self.total_calls,
                'total_failures': self.total_failures,
                'circuit_opens': self.circuit_opens,
                'success_rate': f"{((self.total_calls - self.total_failures) / max(self.total_calls, 1)) * 100:.2f}%",
                'last_success': self.last_success_time.isoformat() if self.last_success_time else None,
                'last_failure': self.last_failure_time.isoformat() if self.last_failure_time else None,
                'uptime_seconds': uptime
            }

# Global circuit breaker instance
breaker = CircuitBreaker(
    name="Financial API Service",
    failure_threshold=5,  # 5 başarısızlık
    timeout=300,          # 5 dakika bekle
    half_open_success_threshold=3  # 3 başarılı test gerekir
)

# ======================================
# SCHEDULER YÖNETİMİ
# ======================================

_scheduler: Optional[BackgroundScheduler] = None
_scheduler_lock = threading.Lock()

def fetch_all_data() -> bool:
    """
    Ana veri çekme fonksiyonu
    Hem scheduler hem de manuel trigger için kullanılır
    
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
        # Zaten çalışıyorsa
        if _scheduler is not None:
            if _scheduler.running:
                logger.warning("⚠️ Scheduler zaten çalışıyor, yeni instance oluşturulmadı")
                return _scheduler
            else:
                # Ölü scheduler varsa temizle
                logger.warning("⚠️ Ölü scheduler bulundu, yeniden başlatılıyor...")
                _scheduler = None
        
        # Process ID kontrolü (multi-process için)
        pid = os.getpid()
        logger.info(f"🔧 Scheduler başlatılıyor (PID: {pid})...")
        
        # Executor yapılandırması
        executors = {
            'default': ThreadPoolExecutor(max_workers=1)
        }
        
        # Scheduler yapılandırması
        _scheduler = BackgroundScheduler(
            executors=executors,
            job_defaults={
                'coalesce': True,        # Kaçırılan job'ları birleştir
                'max_instances': 1,      # Aynı anda sadece 1 instance
                'misfire_grace_time': 30 # 30 saniye içinde kaçırılan job'ları çalıştır
            }
        )
        
        # Job ekle
        _scheduler.add_job(
            fetch_all_data,
            'interval',
            seconds=Config.UPDATE_INTERVAL,
            id='sync_financial_data',
            name='Financial Data Sync',
            replace_existing=True,
            next_run_time=datetime.now()  # İlk çalıştırma anında
        )
        
        # Başlat
        _scheduler.start()
        
        logger.info(
            f"✅ Scheduler başlatıldı - "
            f"Güncelleme aralığı: {Config.UPDATE_INTERVAL}s "
            f"({Config.UPDATE_INTERVAL / 60:.1f} dakika)"
        )
        
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
    Scheduler ve circuit breaker durumunu döndür
    """
    with _scheduler_lock:
        if _scheduler is None:
            return {
                'scheduler_running': False,
                'jobs': [],
                'circuit_breaker': breaker.get_status()
            }
        
        jobs = []
        for job in _scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger)
            })
        
        return {
            'scheduler_running': _scheduler.running,
            'jobs': jobs,
            'circuit_breaker': breaker.get_status(),
            'financial_service_metrics': get_service_metrics()
        }

# ======================================
# GRACEFUL SHUTDOWN
# ======================================

def cleanup():
    """
    Uygulama kapanırken cleanup
    """
    logger.info("🧹 Maintenance service cleanup başlatıldı...")
    stop_scheduler()
    
    # Final metrikler
    status = breaker.get_status()
    logger.info(f"📊 Final circuit breaker stats: {status}")

# Otomatik cleanup
atexit.register(cleanup)
