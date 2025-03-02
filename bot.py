import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, ConversationHandler
from moviepy.editor import VideoFileClip
import yt_dlp
from dotenv import load_dotenv
import tempfile
import sys
import asyncio
from aiohttp import web

# Conversation states
WAITING_FOR_FILENAME = 1

# Logging ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout  # Render için stdout'a log
)

logger = logging.getLogger(__name__)

# Sadece development ortamında .env dosyasını yükle
if os.path.exists('.env'):
    load_dotenv()

TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN bulunamadı!")

# Web sunucusu için route'lar
routes = web.RouteTableDef()

@routes.get('/health')
async def health_check(request):
    return web.Response(text='Healthy')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Merhaba! Ben video dosyalarını MP3\'e dönüştüren bir botum. '
        'Bana bir video dosyası gönder, ben de sana MP3 olarak geri göndereyim.'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Kullanım:\n'
        '1. Bana bir video dosyası gönder\n'
        '2. MP3 dosyası için bir isim gir\n'
        '3. Ben onu MP3\'e dönüştürüp sana göndereceğim'
    )

async def ask_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Video bilgilerini context'e kaydet
        context.user_data['video'] = await update.message.video.get_file()
        context.user_data['processing_message'] = await update.message.reply_text("Lütfen MP3 dosyası için bir isim girin (örnek: muzik)")
        
        # Kullanıcı bilgilerini logla
        user = update.message.from_user
        logger.info(f"Video alındı - Kullanıcı: {user.id} ({user.username})")
        logger.info(f"Video boyutu: {update.message.video.file_size} bytes")
        
        return WAITING_FOR_FILENAME
    except Exception as e:
        logger.error(f"Video alınırken hata: {str(e)}")
        await update.message.reply_text("Video işlenirken bir hata oluştu. Lütfen tekrar deneyin.")
        return ConversationHandler.END

async def process_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    temp_video = None
    temp_audio = None
    video_clip = None
    
    try:
        # Dosya adını al ve .mp3 uzantısını ekle
        filename = update.message.text.strip()
        if not filename:
            await update.message.reply_text("Geçerli bir dosya adı girmelisiniz. Lütfen tekrar deneyin.")
            return WAITING_FOR_FILENAME
            
        mp3_filename = f"{filename}.mp3"
        
        # İşlem başladı mesajını güncelle
        processing_message = context.user_data.get('processing_message')
        await processing_message.edit_text("Video işleniyor...")
        
        # Video dosyasını al
        video = context.user_data.get('video')
        if not video:
            await update.message.reply_text("Video bulunamadı. Lütfen videoyu tekrar gönderin.")
            return ConversationHandler.END
        
        # Geçici dosyaları oluştur
        temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
        temp_audio = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
        
        # Video'yu indir
        await video.download_to_drive(temp_video.name)
        logger.info("Video başarıyla indirildi")
        
        # Dosyaları kapat
        temp_video.close()
        temp_audio.close()
        
        # Video'yu MP3'e dönüştür
        video_clip = VideoFileClip(temp_video.name)
        video_clip.audio.write_audiofile(temp_audio.name)
        logger.info("Video MP3'e dönüştürüldü")
        
        # VideoFileClip'i kapat
        video_clip.close()
        
        # MP3 dosyasını gönder
        with open(temp_audio.name, 'rb') as audio_file:
            await update.message.reply_audio(
                audio=audio_file,
                filename=mp3_filename,
                caption=f"İşte MP3 dosyanız: {mp3_filename}"
            )
        logger.info("MP3 dosyası gönderildi")
        
        # İşlem tamamlandı mesajını güncelle
        await processing_message.edit_text("Dönüştürme işlemi tamamlandı!")
        
    except Exception as e:
        error_message = f"Bir hata oluştu: {str(e)}"
        logger.error(error_message)
        await update.message.reply_text(error_message)
        return ConversationHandler.END
        
    finally:
        # Tüm kaynakları temizle
        if video_clip is not None:
            try:
                video_clip.close()
            except:
                pass
        
        # Geçici dosyaları temizle
        try:
            if temp_video is not None and os.path.exists(temp_video.name):
                os.unlink(temp_video.name)
            if temp_audio is not None and os.path.exists(temp_audio.name):
                os.unlink(temp_audio.name)
            logger.info("Geçici dosyalar temizlendi")
        except Exception as e:
            logger.error(f"Dosya temizleme hatası: {str(e)}")
        
        # Kullanıcı verilerini temizle
        context.user_data.clear()
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("İşlem iptal edildi.")
    context.user_data.clear()
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.message:
        await update.message.reply_text("Bir hata oluştu. Lütfen tekrar deneyin.")

async def run_bot():
    # Bot uygulamasını başlat
    application = Application.builder().token(TOKEN).build()

    # Conversation handler'ı oluştur
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.VIDEO, ask_filename)],
        states={
            WAITING_FOR_FILENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_filename)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # Komut işleyicilerini ekle
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(conv_handler)

    # Hata işleyici ekle
    application.add_error_handler(error_handler)

    # Botu başlat
    logger.info("Bot başlatılıyor...")
    await application.initialize()
    await application.start()
    await application.run_polling(allowed_updates=Update.ALL_TYPES)

async def run_web_server():
    # Web sunucusunu başlat
    app = web.Application()
    app.add_routes(routes)
    
    # Port numarasını Render'dan al
    port = int(os.environ.get('PORT', 10000))
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Web sunucusu {port} portunda başlatıldı")

async def main():
    # Bot ve web sunucusunu aynı anda çalıştır
    await asyncio.gather(
        run_bot(),
        run_web_server()
    )

if __name__ == '__main__':
    asyncio.run(main()) 