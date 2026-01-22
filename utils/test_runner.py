"""
Test Runner - OTOMATİK TEST SİSTEMİ 🧪
=====================================
✅ Telegram'dan /test komutu ile çalışır
✅ 3 mod: basit, detay, mobil
✅ 5 saniyede rapor hazır
"""

import logging
import time
import requests
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class TestRunner:
    """Sistem testlerini çalıştırır ve rapor üretir"""
    
    def __init__(self, base_url: str = "http://localhost:10000"):
        self.base_url = base_url
        self.results = {}
    
    def run_basic_test(self) -> str:
        """
        🧪 BASIT TEST (5 saniye)
        API endpoint'leri + Cache + Worker kontrolü
        """
        start_time = time.time()
        report_lines = ["🧪 *TEST RAPORU*\n━━━━━━━━━━━━━━━━━━━━\n"]
        
        # 1. API Endpoint Testleri
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
                    
                    # Veri sayısını kontrol et
                    count = len(data.get('data', []))
                    
                    # Banner kontrolü
                    banner = data.get('meta', {}).get('banner')
                    banner_status = f"Banner: ✅" if banner else "Banner: ❌"
                    
                    report_lines.append(f"   ✅ {name}: 200 OK ({count} öğe) {banner_status}")
                    api_ok += 1
                else:
                    report_lines.append(f"   ❌ {name}: {resp.status_code}")
            except Exception as e:
                report_lines.append(f"   ❌ {name}: Hata ({str(e)[:30]})")
        
        report_lines.append("")
        
        # 2. Cache Kontrolü
        report_lines.append("✅ *CACHE SİSTEMİ:*")
        try:
            from utils.cache import get_cache, redis_wrapper
            from config import Config
            
            # Redis bağlantısı
            redis_status = "Bağlı" if redis_wrapper.is_enabled() else "RAM Modu"
            report_lines.append(f"   🔌 Redis: {redis_status}")
            
            # Cache verileri
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
        
        # 3. Worker Durumu
        report_lines.append("✅ *WORKER:*")
        try:
            from utils.cache import get_cache
            from config import Config
            
            last_run = get_cache(Config.CACHE_KEYS['last_worker_run'])
            if last_run:
                diff = int(time.time() - float(last_run))
                if diff < 180:  # 3 dakikadan az
                    report_lines.append(f"   ✅ Son çalışma: {diff} saniye önce")
                else:
                    report_lines.append(f"   ⚠️ Son çalışma: {diff//60} dakika önce")
            else:
                report_lines.append(f"   ⚪ Henüz çalışmadı")
            
            # Aktif kaynak
            active_source = get_cache(Config.CACHE_KEYS['active_source']) or "v5"
            report_lines.append(f"   🔌 Kaynak: {active_source.upper()}")
            
        except Exception as e:
            report_lines.append(f"   ❌ Worker hatası: {str(e)[:30]}")
        
        report_lines.append("")
        
        # 4. Bileşenler
        report_lines.append("✅ *BİLEŞENLER:*")
        try:
            from services.maintenance_service import get_scheduler_status
            from utils.cache import get_cache
            from config import Config
            
            scheduler = get_scheduler_status()
            report_lines.append(f"   {'✅' if scheduler['running'] else '❌'} Scheduler: {'Çalışıyor' if scheduler['running'] else 'Durdu'}")
            
            snapshot = get_cache(Config.CACHE_KEYS['yesterday_prices'])
            report_lines.append(f"   {'✅' if snapshot else '❌'} Snapshot: {'Mevcut' if snapshot else 'Kayıp'}")
            
        except Exception as e:
            report_lines.append(f"   ❌ Bileşen hatası: {str(e)[:30]}")
        
        # Süre ve Sonuç
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
        
        # 1. Response Format Kontrolü
        report_lines.append("✅ *API RESPONSE FORMAT:*")
        
        try:
            resp = requests.get(f"{self.base_url}/api/currency/all", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                
                # Format kontrolü
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
        
        # 2. Banner Testi
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
        
        # 3. Veri Kalitesi
        report_lines.append("✅ *VERİ KALİTESİ:*")
        
        try:
            resp = requests.get(f"{self.base_url}/api/currency/all", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                currencies = data.get('data', [])
                
                # Önemli dövizleri kontrol et
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
        
        # Sonuç
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
        
        # Basit testi çalıştır
        basic = self.run_basic_test()
        
        # Mobil testi ekle
        report_lines.append(basic)
        report_lines.append("\n" + "="*30 + "\n")
        
        mobile = self.run_mobile_test()
        report_lines.append(mobile)
        
        # Ek detaylar
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


# Global instance
test_runner = TestRunner(base_url="http://localhost:10000")


def run_test(test_type: str = "basic") -> str:
    """
    Test çalıştırıcı (Telegram'dan çağrılır)
    
    Args:
        test_type: "basic", "mobile", "detailed"
    
    Returns:
        str: Test raporu (Markdown formatında)
    """
    if test_type == "basic":
        return test_runner.run_basic_test()
    elif test_type == "mobile" or test_type == "mobil":
        return test_runner.run_mobile_test()
    elif test_type == "detailed" or test_type == "detay":
        return test_runner.run_detailed_test()
    else:
        return "❌ Geçersiz test tipi! Kullanım: /test, /test mobil, /test detay"
