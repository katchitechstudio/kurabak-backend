import requests
import json

def test_endpoint(url, name):
    print(f"\n{'='*80}")
    print(f"🔍 TEST: {name}")
    print(f"📡 URL: {url}")
    print('='*80)
    
    try:
        r = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://bigpara.hurriyet.com.tr/",
            "Accept": "application/json"
        })
        
        if r.status_code != 200:
            print(f"❌ HTTP {r.status_code}")
            return
        
        data = r.json()
        
        # Veri yapısını analiz et
        if isinstance(data, dict):
            if "data" in data:
                items = data["data"]
                print(f"✅ {len(items)} adet veri bulundu")
                
                # Döviz, Altın, Gümüş say
                currencies = [x for x in items if "TRY" in x.get("SEMBOL", "") and x.get("SEMBOL") not in ["EURTRY", "USDTRY", "GBPTRY"]]
                golds = [x for x in items if "ALTIN" in x.get("ACIKLAMA", "").upper() or x.get("SEMBOL") == "GLDGR"]
                silvers = [x for x in items if "GÜMÜŞ" in x.get("ACIKLAMA", "").upper() or "SILVER" in x.get("ACIKLAMA", "").upper()]
                
                print(f"  💰 Döviz: {len([x for x in items if 'TRY' in x.get('SEMBOL', '')])} adet")
                print(f"  🥇 Altın: {len(golds)} adet")
                print(f"  🥈 Gümüş: {len(silvers)} adet")
                
                # İlk 10 veriyi göster
                print(f"\n📋 İlk 10 Veri:")
                for i, item in enumerate(items[:10], 1):
                    print(f"  {i}. {item.get('SEMBOL'):15} - {item.get('ACIKLAMA')}")
                
                # Altınları özel göster
                if golds:
                    print(f"\n🥇 Bulunan Altınlar:")
                    for gold in golds:
                        print(f"  - {gold.get('SEMBOL'):10} {gold.get('ACIKLAMA')}")
                
                # Gümüşü özel göster
                if silvers:
                    print(f"\n🥈 Bulunan Gümüşler:")
                    for silver in silvers:
                        print(f"  - {silver.get('SEMBOL'):10} {silver.get('ACIKLAMA')}")
                        
        print(f"\n✅ TEST BAŞARILI")
        
    except Exception as e:
        print(f"❌ HATA: {e}")

# Test edilecek endpoint'ler
endpoints = [
    ("https://api.bigpara.hurriyet.com.tr/doviz/headerlist/anasayfa", "Anasayfa (Mevcut)"),
    ("https://api.bigpara.hurriyet.com.tr/doviz/headerlist/altin", "Altınlar"),
    ("https://api.bigpara.hurriyet.com.tr/doviz/headerlist/gumus", "Gümüş"),
    ("https://api.bigpara.hurriyet.com.tr/doviz/headerlist/all", "Tümü"),
    ("https://api.bigpara.hurriyet.com.tr/doviz/headerlist/TUM", "Tümü (Büyük Harf)"),
    ("https://api.bigpara.hurriyet.com.tr/doviz/list", "Döviz Listesi"),
    ("https://api.bigpara.hurriyet.com.tr/altin/list", "Altın Listesi"),
    ("https://api.bigpara.hurriyet.com.tr/gumus/list", "Gümüş Listesi"),
    ("https://bigpara.hurriyet.com.tr/api/v1/doviz/list", "API v1 Döviz"),
    ("https://bigpara.hurriyet.com.tr/api/v1/altin/list", "API v1 Altın"),
]

print("🚀 Bigpara API Endpoint Testi Başlatılıyor...")
print("="*80)

for url, name in endpoints:
    test_endpoint(url, name)
    
print("\n" + "="*80)
print("✅ TÜM TESTLER TAMAMLANDI")
print("="*80)
