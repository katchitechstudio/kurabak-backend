import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
# Yeni tekil servisimizi çağırıyoruz
from services.financial_service import sync_financial_data

logger = logging.getLogger(__name__)

class CircuitBreaker:
    def __init__(self, name, failure_threshold=3, timeout=300): # Eşiği 3'e düşürdük, daha hassas
        self.name = name
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.last_failure_time = None
        self.state = 'CLOSED'
        
    def call(self, func):
        if self.state == 'OPEN':
            if (datetime.now() - self.last_failure_time).total_seconds() > self.timeout:
                logger.info(f"🔄 {self.name} test ediliyor (HALF_OPEN)...")
                self.state = 'HALF_OPEN'
            else:
                return False
        
        try:
            result = func()
            if result:
                self.state = 'CLOSED'
                self.failure_count = 0
                return True
            else:
                self._record_failure()
                return False
        except Exception as e:
            logger.error(f"❌ {self.name} hatası: {e}")
            self._record_failure()
            return False
    
    def _record_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'
            logger.error(f"🔴 {self.name} DEVRE DIŞI (OPEN) - API'ye erişim durduruldu.")

# 🎯 3 ayrı breaker yerine TEK bir breaker kullanıyoruz
financial_breaker = CircuitBreaker("Finans Servisi", failure_threshold=3, timeout=300)

def update_all_data():
    """
    Tüm finansal verileri (Döviz, Altın, Gümüş) 
    tek bir API çağrısıyla günceller.
    """
    logger.info("🔄 Finansal veri senkronizasyonu başlıyor...")
    start_time = datetime.now()
    
    # Tek bir call ile tüm Redis keylerini dolduruyoruz
    success = financial_breaker.call(sync_financial_data)
    
    duration = (datetime.now() - start_time).total_seconds()
    
    if success:
        logger.info(f"✅ Güncelleme tamamlandı - Süre: {duration:.2f}s")
    else:
        logger.error(f"❌ Güncelleme başarısız! - Süre: {duration:.2f}s")
    
    return {"all_financial_data": success}

_scheduler = None

def start_scheduler():
    global _scheduler
    if _scheduler is not None: return _scheduler

    # Tek iş parçacığı yeterli, çünkü artık 3 ayrı işimiz yok
    executors = {'default': ThreadPoolExecutor(max_workers=1)}
    
    _scheduler = BackgroundScheduler(
        executors=executors,
        job_defaults={'coalesce': True, 'max_instances': 1}
    )
    
    # 3 dakikada bir çalıştır
    _scheduler.add_job(
        update_all_data,
        'interval',
        minutes=3,
        id='sync_financial_data',
        name='Finansal Senkronizasyon (3 dk)',
        replace_existing=True
    )
    
    _scheduler.start()
    logger.info("✅ Scheduler aktif: 3 dakikada bir tekil API sorgusu yapılacak.")
    
    # İlk çalıştırma
    update_all_data()
    return _scheduler

def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("🛑 Scheduler durduruldu.")

def fetch_all_data():
    return update_all_data()
