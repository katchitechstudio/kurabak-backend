import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from services.currency_service import fetch_currencies_to_cache
from services.gold_service import fetch_golds_to_cache
from services.silver_service import fetch_silvers_to_cache

logger = logging.getLogger(__name__)


class CircuitBreaker:
    def __init__(self, name, failure_threshold=5, timeout=300):
        self.name = name
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.last_failure_time = None
        self.state = 'CLOSED'
        
    def call(self, func):
        if self.state == 'OPEN':
            if (datetime.now() - self.last_failure_time).total_seconds() > self.timeout:
                logger.info(f"🔄 {self.name} circuit breaker HALF_OPEN - Test ediliyor...")
                self.state = 'HALF_OPEN'
            else:
                remaining = self.timeout - (datetime.now() - self.last_failure_time).total_seconds()
                logger.warning(
                    f"⚠️ {self.name} circuit breaker OPEN - "
                    f"{remaining:.0f}s sonra tekrar denenecek"
                )
                return False
        
        try:
            result = func()
            
            if result:
                if self.state != 'CLOSED':
                    logger.info(f"✅ {self.name} circuit breaker CLOSED - Servis iyileşti")
                self.state = 'CLOSED'
                self.failure_count = 0
                return True
            else:
                self._record_failure()
                return False
                
        except Exception as e:
            logger.error(f"❌ {self.name} exception: {e}")
            self._record_failure()
            return False
    
    def _record_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            if self.state != 'OPEN':
                logger.error(
                    f"🔴 {self.name} circuit breaker OPEN - "
                    f"{self.failure_threshold} başarısızlıktan sonra devre dışı bırakıldı"
                )
            self.state = 'OPEN'
        else:
            logger.warning(
                f"⚠️ {self.name} başarısız "
                f"({self.failure_count}/{self.failure_threshold})"
            )


currency_breaker = CircuitBreaker("Döviz Servisi", failure_threshold=5, timeout=300)
gold_breaker = CircuitBreaker("Altın Servisi", failure_threshold=5, timeout=300)
silver_breaker = CircuitBreaker("Gümüş Servisi", failure_threshold=5, timeout=300)


def update_all_data():
    logger.info("🔄 Periyodik veri güncelleme başlıyor...")
    start_time = datetime.now()
    
    results = {
        'currency': False,
        'gold': False,
        'silver': False
    }
    
    try:
        results['currency'] = currency_breaker.call(fetch_currencies_to_cache)
    except Exception as e:
        logger.error(f"❌ Döviz güncelleme hatası: {e}")
    
    try:
        results['gold'] = gold_breaker.call(fetch_golds_to_cache)
    except Exception as e:
        logger.error(f"❌ Altın güncelleme hatası: {e}")
    
    try:
        results['silver'] = silver_breaker.call(fetch_silvers_to_cache)
    except Exception as e:
        logger.error(f"❌ Gümüş güncelleme hatası: {e}")
    
    success_count = sum(results.values())
    duration = (datetime.now() - start_time).total_seconds()
    
    if success_count == 3:
        logger.info(
            f"✅ Tüm veriler başarıyla güncellendi "
            f"(Döviz ✓, Altın ✓, Gümüş ✓) - {duration:.2f}s"
        )
    elif success_count == 0:
        logger.error(
            f"❌ Hiçbir veri güncellenemedi! "
            f"(Döviz ✗, Altın ✗, Gümüş ✗) - {duration:.2f}s"
        )
    else:
        status_msg = []
        for name, success in results.items():
            status_msg.append(f"{name.title()} {'✓' if success else '✗'}")
        
        logger.warning(
            f"⚠️ Kısmi güncelleme ({success_count}/3 başarılı): "
            f"{', '.join(status_msg)} - {duration:.2f}s"
        )
    
    return results


_scheduler = None


def start_scheduler():
    global _scheduler
    
    if _scheduler is not None:
        logger.warning("⚠️ Scheduler zaten çalışıyor")
        return _scheduler
    
    executors = {
        'default': ThreadPoolExecutor(max_workers=1)
    }
    
    _scheduler = BackgroundScheduler(
        executors=executors,
        job_defaults={
            'coalesce': True,
            'max_instances': 1
        }
    )
    
    _scheduler.add_job(
        update_all_data,
        'interval',
        minutes=3,
        id='update_all_data',
        name='Periyodik Veri Güncelleme (3 dk)',
        replace_existing=True
    )
    
    _scheduler.start()
    logger.info("✅ Scheduler başlatıldı - 3 dakikada bir otomatik güncelleme yapılacak")
    
    logger.info("🚀 İlk güncelleme başlatılıyor...")
    update_all_data()
    
    return _scheduler


def stop_scheduler():
    global _scheduler
    
    if _scheduler is not None:
        logger.info("🛑 Scheduler durduruluyor...")
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("✅ Scheduler durduruldu")
    else:
        logger.warning("⚠️ Scheduler zaten durmuş")


def fetch_all_data():
    logger.info("🔄 Manuel veri güncelleme tetiklendi")
    return update_all_data()
