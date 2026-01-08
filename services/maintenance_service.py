import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from services.financial_service import sync_financial_data
from config import Config

logger = logging.getLogger(__name__)

class CircuitBreaker:
    """
    API hatalarında sistemi korumaya alan devre kesici.
    Eğer API üst üste hata verirse, belirli bir süre isteği durdurur.
    """
    def __init__(self, name, failure_threshold=3, timeout=300):
        self.name = name
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.last_failure_time = None
        self.state = 'CLOSED' # CLOSED (Çalışıyor), OPEN (Durdu), HALF_OPEN (Deniyor)
        
    def call(self, func):
        if self.state == 'OPEN':
            # Timeout süresi doldu mu kontrol et
            if (datetime.now() - self.last_failure_time).total_seconds() > self.timeout:
                logger.info(f"🔄 {self.name} test ediliyor (HALF_OPEN)...")
                self.state = 'HALF_OPEN'
            else:
                remaining = self.timeout - (datetime.now() - self.last_failure_time).total_seconds()
                logger.warning(f"⚠️ {self.name} devre dışı. {remaining:.0f}s bekliyor...")
                return False
        
        try:
            # Fonksiyonu (sync_financial_data) çalıştır
            result = func()
            
            if result:
                if self.state != 'CLOSED':
                    logger.info(f"✅ {self.name} düzeldi, devre kapatıldı.")
                self.state = 'CLOSED'
                self.failure_count = 0
                return True
            else:
                self._record_failure()
                return False
                
        except Exception as e:
            logger.error(f"❌ {self.name} yürütme hatası: {e}")
            self._record_failure()
            return False
    
    def _record_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            if self.state != 'OPEN':
                logger.error(f"🔴 {self.name} KRİTİK HATA: Devre açıldı! İstekler durduruldu.")
            self.state = 'OPEN'
        else:
            logger.warning(f"⚠️ {self.name} başarısız ({self.failure_count}/{self.failure_threshold})")

# Tekil Breaker Tanımı
breaker = CircuitBreaker("Finans API Servisi", failure_threshold=3, timeout=300)

def fetch_all_data():
    """
    Hem Scheduler hem de manuel istekler (app.py /api/update) 
    tarafından kullanılan ana tetikleyici.
    """
    logger.info("🔄 Veri senkronizasyonu tetiklendi...")
    return breaker.call(sync_financial_data)

_scheduler = None

def start_scheduler():
    """
    Arka planda verileri düzenli çeken zamanlayıcıyı başlatır.
    """
    global _scheduler
    
    if _scheduler is not None:
        logger.warning("⚠️ Scheduler zaten çalışıyor.")
        return _scheduler
    
    # Tek iş parçacığı (Single worker) yeterli
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
    
    # Config.UPDATE_INTERVAL (120 saniye) değerini kullanır
    _scheduler.add_job(
        fetch_all_data,
        'interval',
        seconds=Config.UPDATE_INTERVAL,
        id='sync_financial_data_job',
        name='Finansal Veri Senkronizasyonu',
        replace_existing=True
    )
    
    _scheduler.start()
    logger.info(f"✅ Scheduler başlatıldı - Her {Config.UPDATE_INTERVAL} saniyede bir güncellenecek.")
    
    # Uygulama açılır açılmaz ilk veriyi çekmesi için:
    fetch_all_data()
    
    return _scheduler

def stop_scheduler():
    """
    Uygulama kapanırken (atexit) scheduler'ı güvenli durdurur.
    """
    global _scheduler
    if _scheduler is not None:
        logger.info("🛑 Scheduler durduruluyor...")
        _scheduler.shutdown(wait=False)
        _scheduler = None
