# 💰 KuraBak Backend

KuraBak uygulaması için döviz, altın ve gümüş fiyatlarını yöneten backend servisi.

## 🚀 Özellikler

- 💱 15 farklı döviz kuru takibi
- 🥇 9 farklı altın formatı
- 🥈 Gümüş fiyatları
- 📊 Değişim yüzdeleri ve geçmiş veriler
- ⚡ RAM cache ile hızlı yanıtlar
- 🔄 Otomatik 1 saatlik güncellemeler

## 📡 API Endpoints

### Döviz
- `GET /api/currency/all` - Tüm dövizler
- `GET /api/currency/<code>` - Tek döviz (örn: USD)
- `GET /api/currency/history/<code>` - Geçmiş veriler

### Altın
- `GET /api/currency/gold/all` - Tüm altın formatları
- `GET /api/currency/gold/<name>` - Tek altın (örn: Gram Altın)
- `GET /api/currency/gold/history/<name>` - Geçmiş veriler

### Gümüş
- `GET /api/currency/silver/all` - Gümüş fiyatı
- `GET /api/currency/silver/<name>` - Tek gümüş
- `GET /api/currency/silver/history/<name>` - Geçmiş veriler

### Sistem
- `GET /` - Ana sayfa
- `GET /health` - Sağlık kontrolü
- `POST /api/update` - Manuel güncelleme

## 🔧 Kurulum

### Lokal Geliştirme
```bash
# Bağımlılıkları yükle
pip install -r requirements.txt

# Çevre değişkenlerini ayarla (.env)
DATABASE_URL=postgresql://user:pass@host:5432/kurabak
COLLECTAPI_TOKEN=your_token_here

# Çalıştır
python app.py
```

### Render Deployment

1. GitHub'a push edin
2. Render'da "New Web Service" oluşturun
3. Environment Variables ekleyin:
   - `DATABASE_URL`
   - `COLLECTAPI_TOKEN`
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `gunicorn app:app`

## 📦 Veritabanı

PostgreSQL kullanır. Tablolar otomatik oluşturulur:
- `currencies` - Döviz verileri
- `currency_history` - Döviz geçmişi
- `golds` - Altın verileri
- `gold_history` - Altın geçmişi
- `silvers` - Gümüş verileri
- `silver_history` - Gümüş geçmişi

## 🔑 Gerekli API Keys

- **CollectAPI Token**: https://collectapi.com/
  - Economy API'leri için gerekli

## 📝 Lisans

Developed by Katchi Tech Studio
