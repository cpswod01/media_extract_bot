import os
import subprocess
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, ConversationHandler, CommandHandler

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WORK_DIR = os.path.expanduser("~/BOT/baekbot/tmp")
TRANSCRIPT_DIR = os.path.expanduser("~/BOT/baekbot/transcripts")

YT_DLP = "/opt/homebrew/bin/yt-dlp"
FFMPEG = "/opt/homebrew/bin/ffmpeg"
WHISPER = "/opt/homebrew/bin/whisper"

WAITING_FILENAME = 1

pending_data = {}

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not url.startswith("http"):
        return

    pending_data[update.effective_chat.id] = {"url": url}

    reply_keyboard = [["기본 파일명", "직접 입력"]]
    await update.message.reply_text(
        "파일명 설정할까요?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return WAITING_FILENAME

async def handle_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    response = update.message.text.strip()
    chat_id = update.effective_chat.id

    if chat_id not in pending_data:
        await update.message.reply_text("먼저 링크를 보내주세요.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    if pending_data[chat_id].get("waiting_name"):
        pending_data[chat_id]["filename"] = response
        pending_data[chat_id]["waiting_name"] = False
    elif response == "직접 입력":
        await update.message.reply_text("파일명을 입력해주세요:", reply_markup=ReplyKeyboardRemove())
        pending_data[chat_id]["waiting_name"] = True
        return WAITING_FILENAME
    elif response == "기본 파일명":
        pending_data[chat_id]["filename"] = None
    else:
        pending_data[chat_id]["filename"] = response

    await update.message.reply_text("다운로드 시작할게요...", reply_markup=ReplyKeyboardRemove())
    return await process_audio(update, context)

async def process_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    url = pending_data[chat_id]["url"]
    custom_name = pending_data[chat_id].get("filename")

    os.makedirs(WORK_DIR, exist_ok=True)
    os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
    raw_path = os.path.join(WORK_DIR, "raw_audio")
    mp3_path = os.path.join(WORK_DIR, "summary.mp3")

    try:
        await update.message.reply_text("다운로드 중...")
        subprocess.run([
            YT_DLP, "-x", "--audio-format", "mp3",
            "--cookies-from-browser", "chrome",
            "-o", raw_path + ".%(ext)s", url
        ], check=True, timeout=300)

        await update.message.reply_text("변환 중...")
        raw_files = [f for f in os.listdir(WORK_DIR) if f.startswith("raw_audio")]
        if not raw_files:
            raise Exception("다운로드된 파일을 찾을 수 없어요.")
        raw_file = os.path.join(WORK_DIR, raw_files[0])
        subprocess.run([
            FFMPEG, "-i", raw_file,
            "-ar", "16000", "-ac", "1", "-b:a", "32k",
            mp3_path, "-y"
        ], check=True)

        await update.message.reply_text("Whisper가 듣고 있어요...")
        subprocess.run([
            WHISPER, mp3_path,
            "--language", "ko",
            "--model", "base",
            "--output_format", "txt",
            "--output_dir", TRANSCRIPT_DIR
        ], check=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if custom_name:
            filename = f"{custom_name}.txt"
        else:
            filename = f"transcript_{timestamp}.txt"
        transcript_path = os.path.join(TRANSCRIPT_DIR, filename)

        whisper_files = sorted([
            f for f in os.listdir(TRANSCRIPT_DIR)
            if f.endswith(".txt") and not f.startswith("transcript_") and f != filename
        ])

        transcript = ""
        if whisper_files:
            latest = os.path.join(TRANSCRIPT_DIR, whisper_files[-1])
            with open(latest, "r", encoding="utf-8") as f:
                transcript = f.read()
            with open(transcript_path, "w", encoding="utf-8") as f:
                f.write(f"URL: {url}\n")
                f.write(f"날짜: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("-" * 50 + "\n\n")
                f.write(transcript)
            os.remove(latest)

        await update.message.reply_text(f"대본 저장 완료!\n파일: {filename}")
        await update.message.reply_document(
            document=open(transcript_path, "rb"),
            filename=filename,
            caption="전사 대본 파일이에요."
        )

    except Exception as e:
        await update.message.reply_text(f"오류 발생: {str(e)}")

    finally:
        if os.path.exists(WORK_DIR):
            for f in os.listdir(WORK_DIR):
                os.remove(os.path.join(WORK_DIR, f))

    pending_data.pop(chat_id, None)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("취소했어요.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link)],
    states={
        WAITING_FILENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_filename)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(conv_handler)
print("봇 시작! 텔레그램에서 링크를 보내보세요")
app.run_polling()