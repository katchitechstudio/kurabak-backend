"""
Test Runner - OTOMATİK TEST SİSTEMİ + STRES TESTİ 🧪💪
=======================================================
✅ Telegram'dan /test komutu ile çalışır
✅ 3 mod: basit, detay, mobil
✅ 5 saniyede rapor hazır
✅ STRES TESTİ: Google Play Store hazırlığı - Gerçekçi yük simülasyonu 🔥
✅ SUNUCU KORUMASI: Maksimum limitler ile çökme önleme
"""

import logging
import time
import requests
import threading
from typing import Dict, Any
from datetime import datetime, timedelta
import random

logger = logging.getLogger(__name__)

MAX_STRESS_THREADS = 5
MAX_STRESS_REQUESTS_PER_MINUTE = 60


class TestRunner:
    """Sistem testlerini çalıştırır ve rapor üretir"""
    
    def __init__(self, base_url: str = "http://localhost:10000"):
        self.base_url = base_url
        self.results = {}
        
        self.stress_active = False
        self.stress_stats = {
            'total_requests': 0,
            'successful': 0,
            'failed': 0,
            'total_time': 0,
            'min_response': 999999,
            'max_response': 0,
            'errors': []
        }
    
    def run_basic_test(self) -> str:
        """
        🧪 BASIT TEST (5 saniye)
        API endpoint'leri + Cache + Worker kontrolü
        """
        start_time = time.time()
        report_lines = ["🧪 *TEST RAPORU*\n━━━━━━━━━━━━━━━━━━━━\n"]
        
        report_lines.append("✅ *API ENDPOINTS:*")
        
        endpoints = [
            ("/api/currency/all", "Tüm Dövizler"),
            ("/api/currency/summary", "Özet"),
            ("/api/currency/gold/all", "Altınlar"),
            ("/api/currency/silver/all", "Gümüş")
        ]
        
        api_ok = 0
        for endpoint, name in endpoints:
            try:
                resp = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    
                    count = len(data.get('data', []))
                    
                    banner = data.get('meta', {}).get('banner')
                    banner_status = f"Banner: ✅" if banner else "Banner: ❌"
                    
                    report_lines.append(f"   ✅ {name}: 200 OK ({count} öğe) {banner_status}")
                    api_ok += 1
                else:
                    report_lines.append(f"   ❌ {name}: {resp.status_code}")
            except Exception as e:
                report_lines.append(f"   ❌ {name}: Hata ({str(e)[:30]})")
        
        report_lines.append("")
        
        report_lines.append("✅ *CACHE SİSTEMİ:*")
        try:
            from utils.cache import get_cache, redis_wrapper
            from config import Config
            
            redis_status = "Bağlı" if redis_wrapper.is_enabled() else "RAM Modu"
            report_lines.append(f"   🔌 Redis: {redis_status}")
            
            currencies = get_cache(Config.CACHE_KEYS['currencies_all'])
            banner = get_cache(Config.CACHE_KEYS['banner'])
            
            if currencies:
                report_lines.append(f"   ✅ Currencies: Mevcut")
            else:
                report_lines.append(f"   ❌ Currencies: Yok")
            
            if banner:
                report_lines.append(f"   ✅ Banner: \"{banner[:30]}...\"")
            else:
                report_lines.append(f"   ℹ️ Banner: Yok")
                
        except Exception as e:
            report_lines.append(f"   ❌ Cache hatası: {str(e)[:30]}")
        
        report_lines.append("")
        
        report_lines.append("✅ *WORKER:*")
        try:
            from utils.cache import get_cache
            from config import Config
            
            last_run = get_cache(Config.CACHE_KEYS['last_worker_run'])
            if last_run:
                diff = int(time.time() - float(last_run))
                if diff < 180:
                    report_lines.append(f"   ✅ Son çalışma: {diff} saniye önce")
                else:
                    report_lines.append(f"   ⚠️ Son çalışma: {diff//60} dakika önce")
            else:
                report_lines.append(f"   ⚪ Henüz çalışmadı")
            
            active_source = get_cache(Config.CACHE_KEYS['active_source']) or "v5"
            report_lines.append(f"   🔌 Kaynak: {active_source.upper()}")
            
        except Exception as e:
            report_lines.append(f"   ❌ Worker hatası: {str(e)[:30]}")
        
        report_lines.append("")
        
        report_lines.append("✅ *BİLEŞENLER:*")
        try:
            from services.maintenance_service import get_scheduler_status
            from utils.cache import get_cache
            from config import Config
            
            scheduler = get_scheduler_status()
            report_lines.append(f"   {'✅' if scheduler['running'] else '❌'} Scheduler: {'Çalışıyor' if scheduler['running'] else 'Durdu'}")
            
            # V5.5 — güncel snapshot key
            snapshot = get_cache(Config.CACHE_KEYS['daily_snapshot'])
            report_lines.append(f"   {'✅' if snapshot else '❌'} Snapshot: {'Mevcut' if snapshot else 'Kayıp'}")
            
        except Exception as e:
            report_lines.append(f"   ❌ Bileşen hatası: {str(e)[:30]}")
        
        elapsed = time.time() - start_time
        report_lines.append("\n━━━━━━━━━━━━━━━━━━━━")
        
        if api_ok == len(endpoints):
            report_lines.append(f"🎯 *SONUÇ: TÜM SİSTEMLER SAĞLIKLI* ✅")
        else:
            report_lines.append(f"⚠️ *SONUÇ: {api_ok}/{len(endpoints)} ENDPOINT ÇALIŞIYOR*")
        
        report_lines.append(f"⏱ Test süresi: {elapsed:.1f} saniye")
        
        return "\n".join(report_lines)
    
    def run_mobile_test(self) -> str:
        """
        📱 MOBİL UYUMLULUK TESTİ
        Banner ve response formatı kontrolü
        """
        start_time = time.time()
        report_lines = ["📱 *MOBİL UYUMLULUK TESTİ*\n━━━━━━━━━━━━━━━━━━━━\n"]
        
        report_lines.append("✅ *API RESPONSE FORMAT:*")
        
        try:
            resp = requests.get(f"{self.base_url}/api/currency/all", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                
                has_success = 'success' in data
                has_data = 'data' in data
                has_meta = 'meta' in data
                has_timestamp = 'timestamp' in data
                
                if all([has_success, has_data, has_meta, has_timestamp]):
                    report_lines.append("   ✅ Format doğru: {success, data, meta, timestamp}")
                else:
                    report_lines.append(f"   ⚠️ Format eksik: {data.keys()}")
                
        except Exception as e:
            report_lines.append(f"   ❌ Format kontrolü hatası: {str(e)[:30]}")
        
        report_lines.append("")
        
        report_lines.append("✅ *BANNER TESTİ:*")
        
        endpoints_to_check = [
            ("/api/currency/all", "Dövizler"),
            ("/api/currency/summary", "Özet")
        ]
        
        banner_ok = 0
        for endpoint, name in endpoints_to_check:
            try:
                resp = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    banner = data.get('meta', {}).get('banner')
                    
                    if banner:
                        report_lines.append(f"   ✅ {name}: \"{banner[:40]}...\"")
                        banner_ok += 1
                    else:
                        report_lines.append(f"   ℹ️ {name}: Banner yok")
            except Exception as e:
                report_lines.append(f"   ❌ {name}: Hata")
        
        report_lines.append("")
        
        report_lines.append("✅ *VERİ KALİTESİ:*")
        
        try:
            resp = requests.get(f"{self.base_url}/api/currency/all", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                currencies = data.get('data', [])
                
                important = ['USD', 'EUR', 'GBP']
                for code in important:
                    curr = next((c for c in currencies if c.get('code') == code), None)
                    if curr:
                        selling = curr.get('selling', 0)
                        if selling > 0:
                            report_lines.append(f"   ✅ {code}: {selling:.2f} ₺")
                        else:
                            report_lines.append(f"   ❌ {code}: Geçersiz fiyat")
                    else:
                        report_lines.append(f"   ❌ {code}: Bulunamadı")
        except Exception as e:
            report_lines.append(f"   ❌ Veri kalitesi hatası: {str(e)[:30]}")
        
        elapsed = time.time() - start_time
        report_lines.append("\n━━━━━━━━━━━━━━━━━━━━")
        
        if banner_ok > 0:
            report_lines.append(f"🎯 *MOBİL UYGULAMA BANNER'I GÖRECEKTİR* ✅")
        else:
            report_lines.append(f"⚠️ *BANNER YOK - KONTROL ET!*")
        
        report_lines.append(f"⏱ Test süresi: {elapsed:.1f} saniye")
        
        return "\n".join(report_lines)
    
    def run_detailed_test(self) -> str:
        """
        🔬 DETAYLI TEST
        Tüm bileşenlerin derinlemesine kontrolü
        """
        start_time = time.time()
        report_lines = ["🔬 *DETAYLI TEST RAPORU*\n━━━━━━━━━━━━━━━━━━━━\n"]
        
        basic = self.run_basic_test()
        
        report_lines.append(basic)
        report_lines.append("\n" + "="*30 + "\n")
        
        mobile = self.run_mobile_test()
        report_lines.append(mobile)
        
        report_lines.append("\n" + "="*30 + "\n")
        report_lines.append("🔍 *EK DETAYLAR:*\n")
        
        try:
            from services.financial_service import get_service_metrics
            metrics = get_service_metrics()
            
            report_lines.append(f"📊 *Metrikler:*")
            for key, val in metrics.items():
                report_lines.append(f"   • {key}: {val}")
        except Exception as e:
            report_lines.append(f"   ❌ Metrik hatası: {str(e)[:30]}")
        
        elapsed = time.time() - start_time
        report_lines.append(f"\n⏱ Toplam test süresi: {elapsed:.1f} saniye")
        
        return "\n".join(report_lines)

    def _make_stress_request(self, endpoint: str) -> Dict[str, Any]:
        """Tek bir stres test isteği yapar"""
        start = time.time()
        try:
            resp = requests.get(f"{self.base_url}{endpoint}", timeout=10)
            elapsed = time.time() - start
            
            return {
                'success': resp.status_code == 200,
                'status_code': resp.status_code,
                'response_time': elapsed
            }
        except Exception as e:
            elapsed = time.time() - start
            return {
                'success': False,
                'status_code': 0,
                'response_time': elapsed,
                'error': str(e)[:50]
            }

    def _stress_worker_thread(self, endpoints: list, duration_minutes: int, requests_per_minute: int, thread_id: int):
        """Stres testi worker thread'i"""
        end_time = time.time() + (duration_minutes * 60)
        request_interval = 60.0 / requests_per_minute
        
        logger.info(f"🔥 [STRESS-{thread_id}] Thread başladı: {requests_per_minute} req/min, {duration_minutes} dakika")
        
        while self.stress_active and time.time() < end_time:
            endpoint = random.choice(endpoints)
            
            result = self._make_stress_request(endpoint)
            
            self.stress_stats['total_requests'] += 1
            
            if result['success']:
                self.stress_stats['successful'] += 1
            else:
                self.stress_stats['failed'] += 1
                if result.get('error'):
                    self.stress_stats['errors'].append(result['error'])
            
            self.stress_stats['total_time'] += result['response_time']
            self.stress_stats['min_response'] = min(self.stress_stats['min_response'], result['response_time'])
            self.stress_stats['max_response'] = max(self.stress_stats['max_response'], result['response_time'])
            
            time.sleep(request_interval)
        
        logger.info(f"✅ [STRESS-{thread_id}] Thread tamamlandı")

    def run_stress_test(self, level: str) -> str:
        """
        💪 STRES TESTİ - GOOGLE PLAY STORE HAZIRLIGI
        
        Seviyeler:
        - light: 10 dakika, hafif yük (3 thread, 30 req/min = ~300 istek)
        - medium: 20 dakika, orta yük (5 thread, 50 req/min = ~1000 istek)
        - hard: 30 dakika, yüksek yük (5 thread, 60 req/min = ~1500 istek)
        
        NOT: Sunucu koruması için maksimum 5 thread ve 60 req/min sınırı var.
        """
        
        stress_configs = {
            'light': {
                'duration': 10,
                'threads': 3,
                'requests_per_minute': 30,
                'description': '10dk hafif yük (~300 istek)'
            },
            'medium': {
                'duration': 20,
                'threads': 5,
                'requests_per_minute': 50,
                'description': '20dk orta yük (~1000 istek)'
            },
            'hard': {
                'duration': 30,
                'threads': 5,
                'requests_per_minute': 60,
                'description': '30dk yüksek yük (~1500 istek)'
            }
        }
        
        if level not in stress_configs:
            return (
                f"❌ *GEÇERSIZ SEVİYE!*\n\n"
                f"Kullanılabilir seviyeler:\n"
                f"• `light` - 10dk hafif yük\n"
                f"• `medium` - 20dk orta yük\n"
                f"• `hard` - 30dk yüksek yük"
            )
        
        config = stress_configs[level]
        
        if config['threads'] > MAX_STRESS_THREADS:
            return (
                f"❌ *GÜVENLİK SINIRI!*\n\n"
                f"Maksimum {MAX_STRESS_THREADS} thread kullanılabilir.\n"
                f"Sunucuyu korumak için bu sınır vardır."
            )
        
        if config['requests_per_minute'] > MAX_STRESS_REQUESTS_PER_MINUTE:
            return (
                f"❌ *GÜVENLİK SINIRI!*\n\n"
                f"Maksimum {MAX_STRESS_REQUESTS_PER_MINUTE} req/min kullanılabilir.\n"
                f"Sunucuyu korumak için bu sınır vardır."
            )
        
        endpoints = [
            '/api/currency/all',
            '/api/currency/gold/all',
            '/api/currency/silver/all',
            '/api/currency/regional'
        ]
        
        self.stress_stats = {
            'total_requests': 0,
            'successful': 0,
            'failed': 0,
            'total_time': 0,
            'min_response': 999999,
            'max_response': 0,
            'errors': []
        }
        
        self.stress_active = True
        
        start_msg = (
            f"💪 *STRES TESTİ BAŞLIYOR!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎯 *Seviye:* `{level.upper()}`\n"
            f"📝 *Açıklama:* {config['description']}\n"
            f"⏱️ *Süre:* {config['duration']} dakika\n"
            f"🔥 *Thread Sayısı:* {config['threads']}\n"
            f"📊 *Hedef:* {config['requests_per_minute']} req/min/thread\n"
            f"📈 *Toplam:* ~{config['threads'] * config['requests_per_minute'] * config['duration']} istek\n\n"
            f"🛡️ *Google Play Store gerçekçi simülasyonu*\n\n"
            f"Test başladı... Sonuçlar {config['duration']} dakika sonra gelecek."
        )
        
        logger.info(f"🚀 Stres testi başlıyor: {level}")
        
        threads = []
        start_time = time.time()
        
        for i in range(config['threads']):
            thread = threading.Thread(
                target=self._stress_worker_thread,
                args=(endpoints, config['duration'], config['requests_per_minute'], i+1),
                daemon=True
            )
            thread.start()
            threads.append(thread)
            time.sleep(0.1)
        
        def progress_reporter():
            """Her 5 dakikada bir ilerleme raporu gönder"""
            report_interval = 300
            next_report = time.time() + report_interval
            
            while self.stress_active and any(t.is_alive() for t in threads):
                if time.time() >= next_report:
                    elapsed = int((time.time() - start_time) / 60)
                    remaining = config['duration'] - elapsed
                    
                    total = self.stress_stats['total_requests']
                    success_rate = 0
                    if total > 0:
                        success_rate = (self.stress_stats['successful'] / total) * 100
                    
                    avg_response = 0
                    if total > 0:
                        avg_response = self.stress_stats['total_time'] / total
                    
                    progress_msg = (
                        f"⏳ *İLERLEME RAPORU*\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"⏱️ *Geçen:* {elapsed} dakika\n"
                        f"⏳ *Kalan:* {remaining} dakika\n"
                        f"📊 *Toplam İstek:* {total}\n"
                        f"✅ *Başarılı:* {self.stress_stats['successful']} (%{success_rate:.1f})\n"
                        f"❌ *Başarısız:* {self.stress_stats['failed']}\n"
                        f"⚡ *Ort. Yanıt:* {avg_response*1000:.0f}ms\n"
                        f"📈 *Min/Max:* {self.stress_stats['min_response']*1000:.0f}ms / {self.stress_stats['max_response']*1000:.0f}ms\n\n"
                        f"💪 Test devam ediyor..."
                    )
                    
                    try:
                        from utils.telegram_monitor import get_telegram_monitor
                        telegram = get_telegram_monitor()
                        if telegram:
                            telegram._send_raw(progress_msg)
                    except:
                        pass
                    
                    logger.info(f"📊 İlerleme: {elapsed}/{config['duration']} dakika, {total} istek")
                    
                    next_report = time.time() + report_interval
                
                time.sleep(10)
        
        reporter_thread = threading.Thread(target=progress_reporter, daemon=True)
        reporter_thread.start()
        
        for thread in threads:
            thread.join()
        
        self.stress_active = False
        
        elapsed_total = time.time() - start_time
        total_requests = self.stress_stats['total_requests']
        success_rate = 0
        if total_requests > 0:
            success_rate = (self.stress_stats['successful'] / total_requests) * 100
        
        avg_response = 0
        if total_requests > 0:
            avg_response = self.stress_stats['total_time'] / total_requests
        
        if success_rate >= 99:
            performance = "🟢 MÜKEMMEL"
            emoji = "🎉"
        elif success_rate >= 95:
            performance = "🟡 İYİ"
            emoji = "👍"
        elif success_rate >= 85:
            performance = "🟠 ORTA"
            emoji = "⚠️"
        else:
            performance = "🔴 ZAYIF"
            emoji = "😰"
        
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent
            
            system_status = (
                f"\n💻 *SİSTEM KAYNAKLARI:*\n"
                f"• CPU: %{cpu:.1f}\n"
                f"• RAM: %{ram:.1f}\n"
            )
        except:
            system_status = ""
        
        error_samples = ""
        if self.stress_stats['errors']:
            unique_errors = list(set(self.stress_stats['errors'][:5]))
            error_samples = "\n\n❌ *HATA ÖRNEKLERİ:*\n"
            for i, err in enumerate(unique_errors[:3], 1):
                error_samples += f"{i}. {err}\n"
        
        final_report = (
            f"{emoji} *STRES TESTİ TAMAMLANDI!* {emoji}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎯 *Seviye:* `{level.upper()}`\n"
            f"⏱️ *Süre:* {elapsed_total/60:.1f} dakika\n"
            f"📊 *Performans:* {performance}\n\n"
            f"📈 *İSTATİSTİKLER:*\n"
            f"• Toplam İstek: *{total_requests:,}*\n"
            f"• ✅ Başarılı: *{self.stress_stats['successful']:,}* (%{success_rate:.2f})\n"
            f"• ❌ Başarısız: *{self.stress_stats['failed']:,}*\n"
            f"• ⚡ Ort. Yanıt: *{avg_response*1000:.0f}ms*\n"
            f"• 📉 Min Yanıt: *{self.stress_stats['min_response']*1000:.0f}ms*\n"
            f"• 📈 Max Yanıt: *{self.stress_stats['max_response']*1000:.0f}ms*\n"
            f"• 🔥 İstek/Saniye: *{total_requests/elapsed_total:.1f}*\n"
            f"{system_status}"
            f"{error_samples}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ Google Play Store hazırlığı: {self._get_play_store_status(success_rate, avg_response)}\n\n"
            f"_Tavsiye: {self._get_recommendation(success_rate, avg_response)}_"
        )
        
        logger.info(f"✅ Stres testi tamamlandı: {level} - {total_requests} istek, %{success_rate:.2f} başarı")
        
        return final_report

    def _get_play_store_status(self, success_rate: float, avg_response: float) -> str:
        if success_rate >= 99 and avg_response < 0.5:
            return "HAZIR 🚀"
        elif success_rate >= 95 and avg_response < 1.0:
            return "NEREDEYSE HAZIR 👍"
        elif success_rate >= 85:
            return "İYİLEŞTİRME GEREKLİ ⚠️"
        else:
            return "HAZIR DEĞİL ❌"

    def _get_recommendation(self, success_rate: float, avg_response: float) -> str:
        if success_rate >= 99 and avg_response < 0.5:
            return "Sistem mükemmel durumda! Google Play'e çıkabilirsin. 🚀"
        elif success_rate >= 95 and avg_response < 1.0:
            return "Sistem stabil. Cache optimizasyonu yapabilirsin."
        elif success_rate >= 85:
            return "Rate limiting veya cache stratejisini gözden geçir."
        else:
            return "Ciddi performans sorunları var! Circuit breaker ve cache'i kontrol et."


test_runner = TestRunner(base_url="http://localhost:10000")


def run_test(test_type: str = "basic") -> str:
    if test_type == "basic":
        return test_runner.run_basic_test()
    elif test_type == "mobile" or test_type == "mobil":
        return test_runner.run_mobile_test()
    elif test_type == "detailed" or test_type == "detay":
        return test_runner.run_detailed_test()
    else:
        return "❌ Geçersiz test tipi! Kullanım: /test, /test mobil, /test detay"


def run_stress_test(level: str = "light") -> str:
    return test_runner.run_stress_test(level)
