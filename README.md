# Video to MP3 Telegram Bot

Bu Telegram botu, gönderilen video dosyalarını MP3 formatına dönüştürüp geri gönderir.

## Render Deployment

1. Render.com hesabınıza giriş yapın
2. "New +" butonuna tıklayın ve "Web Service" seçin
3. GitHub repository'nizi bağlayın
4. Aşağıdaki ayarları yapın:
   - Name: telegram-video-to-mp3-bot
   - Environment: Docker
   - Region: Tercihinize göre seçin
5. "Environment Variables" bölümünde:
   - TELEGRAM_TOKEN: Telegram bot token'ınızı ekleyin
6. "Create Web Service" butonuna tıklayın

## Lokal Geliştirme

1. Python 3.8 veya daha yüksek bir sürümü yükleyin
2. FFmpeg'i yükleyin:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install ffmpeg

   # Windows
   # https://ffmpeg.org/download.html adresinden indirip PATH'e ekleyin
   ```
3. Gerekli paketleri yükleyin:
   ```bash
   pip install -r requirements.txt
   ```
4. `.env` dosyasını oluşturun ve Telegram bot token'ınızı ekleyin:
   ```
   TELEGRAM_TOKEN=your_telegram_bot_token_here
   ```
5. Botu başlatın:
   ```bash
   python bot.py
   ```

## Kullanım

1. Botu başlatmak için:
   ```bash
   python bot.py
   ```
2. Telegram'da botu başlatın ve `/start` komutunu gönderin
3. Bota bir video dosyası gönderin
4. Bot videoyu MP3'e dönüştürüp size gönderecektir

## Özellikler

- Video dosyalarını MP3'e dönüştürme
- Kolay kullanım
- Otomatik dosya temizleme
- Hata yönetimi
- Detaylı loglama
- Docker desteği
- Render.com uyumluluğu 