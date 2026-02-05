# Railway Deployment Guide - Trading Signal Dashboard

## 🚀 Railway'e Deploy Adımları

### 1. GitHub Repository Oluştur

**Terminal'de:**
```bash
cd c:\Users\yasin\Desktop\scalp_trade
git init
git add .
git commit -m "Initial commit - Dashboard deployment"
```

**GitHub'da:**
- [github.com](https://github.com) → New Repository
- Repository adı: `trading-dashboard` (veya istediğin ad)
- **Public veya Private** seçebilirsin
- Create repository

**Kodu GitHub'a yükle:**
```bash
git remote add origin https://github.com/KULLANICI_ADIN/trading-dashboard.git
git branch -M main
git push -u origin main
```

---

### 2. Railway'e Deploy

1. **Railway.app'a Git**: [railway.app](https://railway.app)

2. **GitHub ile Login**

3. **New Project** → **Deploy from GitHub repo**

4. **Repository'ni seç**: `trading-dashboard`

5. **Deploy**! 🎉

Railway otomatik olarak:
- ✅ `requirements.txt` yükler
- ✅ `Procfile` okur
- ✅ Dashboard'u başlatır

---

### 3. Canlı URL'ni Bul

Deploy tamamlanınca (2-3 dakika):

1. **Settings** → **Networking** → **Generate Domain**

2. Domain göreceksin:
   ```
   https://trading-dashboard-production.up.railway.app
   ```

3. **Bu linki her yerden açabilirsin!** 🌐

---

## ⚠️ Önemli Notlar

### Bot Verilerini Nasıl Göndereceksin?

Railway'de sadece **dashboard** çalışacak. Bot'u kendi bilgisayarında çalıştırmalısın çünkü:
- Bot sürekli piyasayı taramak zorunda
- Railway ücretsiz plan sürekli çalışan bot için yetersiz

**Çözüm: İki Yol:**

#### **Yol 1: Bot Railway'de Dashboard Aynı Sunucuda (Önerilen)**

`dashboard.py` ve `main.py` birlikte çalışır:

**Procfile'ı değiştir:**
```
bot: python main.py
web: python dashboard.py
```

Ama bu durumda Railway ücretsiz limitleri aşabilir.

#### **Yol 2: Bot Bilgisayarında, Dashboard Railway'de (Daha İyi)**

1. Bot kendi bilgisayarında çalışır
2. JSON dosyasını **FTP/S3/Database** ile Railway'e yükler
3. Dashboard Railway'de JSON'u okur

Bu durumda `signal_manager.py`'de JSON dosyası yerine **remote database** kullanmalısın.

---

## 🔧 Railway Ücretsiz Limitler

- ⏱️ **500 saat/ay** çalışma süresi
- 💾 **512 MB RAM**
- 💽 **1 GB disk**

**Dashboard için yeterli**, ama bot + dashboard için yetersiz olabilir.

---

## 💡 Tavsiye

En iyi çözüm:
1. **Dashboard** → Railway'de (7/24 online)
2. **Bot** → Kendi bilgisayarında (ccxt, telegram botun çalışır)
3. **Veri transferi** → PostgreSQL veya MongoDB (Railway ücretsiz veriyor)

Bunu da ayarlamamı ister misin? 🚀
