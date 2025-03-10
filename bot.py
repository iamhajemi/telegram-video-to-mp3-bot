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
import threading
import aiohttp
import time
import signal

# Conversation states
WAITING_FOR_FILENAME = 1

# Logging ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout  # Render için stdout'a log
)

logger = logging.getLogger(__name__)

# Environment variables
TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    logger.error("TELEGRAM_TOKEN environment variable bulunamadı!")
    sys.exit(1)
PORT = int(os.getenv('PORT', 10000))

# Global değişkenler
application = None
web_app = None
shutdown_event = asyncio.Event()

# Web sunucusu için route'lar
routes = web.RouteTableDef()

@routes.get('/health')
async def health_check(request):
    return web.Response(text='Bot is running!')

@routes.get('/')
async def home(request):
    return web.Response(text='Video to MP3 Bot is running!')

# Web uygulamasını oluştur
app = web.Application()
app.add_routes(routes)

async def shutdown(signal, loop):
    """Graceful shutdown"""
    logger.info(f"Received exit signal {signal.name}...")
    shutdown_event.set()
    
    # Stop web server
    if web_app:
        await web_app.cleanup()
    
    # Stop bot
    if application:
        await application.stop()
        await application.shutdown()
    
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    logger.info(f"Cancelling {len(tasks)} outstanding tasks")
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()

def handle_exception(loop, context):
    msg = context.get("exception", context["message"])
    logger.error(f"Caught exception: {msg}")

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
        
        # Eğer caption varsa, direkt işleme başla
        if update.message.caption:
            # Kullanıcı bilgilerini logla
            user = update.message.from_user
            logger.info(f"Video ve caption alındı - Kullanıcı: {user.id} ({user.username})")
            logger.info(f"Video boyutu: {update.message.video.file_size} bytes")
            logger.info(f"Caption: {update.message.caption}")
            
            # Process filename'i direkt çağır
            return await process_filename(update, context, update.message.caption)
        
        # Caption yoksa, isim iste
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

async def process_filename(update: Update, context: ContextTypes.DEFAULT_TYPE, caption_filename: str = None):
    temp_video = None
    temp_audio = None
    video_clip = None
    
    try:
        # Dosya adını al ve .mp3 uzantısını ekle
        filename = caption_filename if caption_filename else update.message.text.strip()
        if not filename:
            await update.message.reply_text("Geçerli bir dosya adı girmelisiniz. Lütfen tekrar deneyin.")
            return WAITING_FOR_FILENAME
            
        mp3_filename = f"{filename}.mp3"
        
        # İşlem başladı mesajını gönder veya güncelle
        if caption_filename:
            processing_message = await update.message.reply_text("Video işleniyor...")
        else:
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

async def keep_alive():
    """Her 5 dakikada bir /health endpoint'ini ping eder"""
    while not shutdown_event.is_set():
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/health"
                async with session.get(url) as response:
                    if response.status == 200:
                        logger.info("Keep-alive ping başarılı")
                    else:
                        logger.warning(f"Keep-alive ping başarısız: {response.status}")
        except Exception as e:
            logger.error(f"Keep-alive ping hatası: {str(e)}")
        await asyncio.sleep(300)  # 5 dakika bekle

async def start_bot():
    global application
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

    # Keep-alive task'ı başlat
    asyncio.create_task(keep_alive())

    # Botu başlat
    logger.info("Bot başlatılıyor...")
    await application.initialize()
    await application.start()
    
    try:
        logger.info("Bot polling başlatılıyor...")
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        await application.updater.start_polling()
    except Exception as e:
        logger.error(f"Polling hatası: {str(e)}")
        raise

async def start_web_server():
    global web_app
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    web_app = runner
    logger.info(f"Web sunucusu başlatıldı - Port: {PORT}")

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Hata yakalama
    loop.set_exception_handler(handle_exception)
    
    # Linux için sinyal yönetimi
    if sys.platform != 'win32':
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(shutdown(s, loop))
            )
    
    try:
        # Web sunucusu ve botu başlat
        loop.run_until_complete(start_web_server())
        loop.create_task(start_bot())
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Kapatma sinyali alındı, bot kapatılıyor...")
        loop.run_until_complete(shutdown(signal.SIGINT, loop))
    except Exception as e:
        logger.error(f"Beklenmeyen hata: {str(e)}")
    finally:
        try:
            pending = asyncio.all_tasks(loop)
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
        except Exception as e:
            logger.error(f"Kapatma hatası: {str(e)}")
        logger.info("Bot başarıyla kapatıldı")

if __name__ == '__main__':
    main() 