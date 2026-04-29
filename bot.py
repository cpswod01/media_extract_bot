import os
import asyncio
import re
import shutil
import subprocess
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, ConversationHandler, CommandHandler

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WORK_DIR = os.path.expanduser("~/BOT/baekbot/tmp")
TRANSCRIPT_DIR = os.path.expanduser("~/BOT/baekbot/transcripts")

YT_DLP = os.getenv("YT_DLP", "/opt/homebrew/bin/yt-dlp")
FFMPEG = os.getenv("FFMPEG", "/opt/homebrew/bin/ffmpeg")
WHISPER = os.getenv("WHISPER", "/opt/homebrew/bin/whisper")
COOKIES_FROM_BROWSER = os.getenv("COOKIES_FROM_BROWSER", "chrome")

WAITING_FILENAME = 1
WAITING_MODEL = 2

pending_data = {}

def is_executable(command):
    if os.path.sep in command:
        return os.path.isfile(command) and os.access(command, os.X_OK)
    return shutil.which(command) is not None

def validate_startup():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN이 .env에 설정되어 있지 않아요.")

    missing = [
        path for path in (YT_DLP, FFMPEG, WHISPER)
        if not is_executable(path)
    ]
    if missing:
        raise RuntimeError("실행 파일을 찾을 수 없거나 실행 권한이 없어요: " + ", ".join(missing))

def sanitize_filename(filename):
    name = os.path.basename(filename.strip())
    name = os.path.splitext(name)[0]
    name = re.sub(r"[^\w가-힣 ._-]", "_", name)
    name = re.sub(r"\s+", " ", name).strip(" ._-")
    return name[:120] or "transcript"

def unique_transcript_path(filename):
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(TRANSCRIPT_DIR, filename)
    counter = 2

    while os.path.exists(candidate):
        candidate = os.path.join(TRANSCRIPT_DIR, f"{base}_{counter}{ext}")
        counter += 1

    return candidate

async def run_command(command, **kwargs):
    return await asyncio.to_thread(
        subprocess.run,
        command,
        check=True,
        **kwargs
    )

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

    if response.startswith("http"):
        pending_data[chat_id] = {"url": response}
        reply_keyboard = [["기본 파일명", "직접 입력"]]
        await update.message.reply_text(
            "파일명 설정할까요?",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return WAITING_FILENAME

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

    reply_keyboard = [["tiny", "base", "small"]]
    await update.message.reply_text(
        "Whisper 모델을 선택해주세요.\ntiny: 빠름 / base: 보통 / small: 정확",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return WAITING_MODEL

async def handle_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    response = update.message.text.strip().lower()
    chat_id = update.effective_chat.id

    if chat_id not in pending_data:
        await update.message.reply_text("먼저 링크를 보내주세요.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    if response not in ("tiny", "base", "small"):
        await update.message.reply_text("tiny, base, small 중에 선택해주세요.")
        return WAITING_MODEL

    pending_data[chat_id]["model"] = response
    await update.message.reply_text("다운로드 시작할게요...", reply_markup=ReplyKeyboardRemove())
    return await process_audio(update, context)

async def process_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    url = pending_data[chat_id]["url"]
    custom_name = pending_data[chat_id].get("filename")
    model = pending_data[chat_id].get("model", "tiny")

    os.makedirs(WORK_DIR, exist_ok=True)
    os.makedirs(TRANSCRIPT_DIR, exist_ok=True)

    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    request_id = now.strftime("%Y%m%d_%H%M%S_%f")
    request_dir = os.path.join(WORK_DIR, f"{chat_id}_{request_id}")
    os.makedirs(request_dir, exist_ok=True)
    raw_path = os.path.join(request_dir, "raw_audio")
    mp3_path = os.path.join(request_dir, "summary.mp3")
    whisper_output_path = os.path.join(request_dir, "summary.txt")

    try:
        await update.message.reply_text("다운로드 중...")
        download_command = [
            YT_DLP, "-x", "--audio-format", "mp3",
            "-o", raw_path + ".%(ext)s", url
        ]
        if COOKIES_FROM_BROWSER:
            download_command[4:4] = ["--cookies-from-browser", COOKIES_FROM_BROWSER]
        await run_command(download_command, timeout=300)

        await update.message.reply_text("변환 중...")
        raw_files = [f for f in os.listdir(request_dir) if f.startswith("raw_audio")]
        if not raw_files:
            raise Exception("다운로드된 파일을 찾을 수 없어요.")
        raw_file = os.path.join(request_dir, raw_files[0])
        await run_command([
            FFMPEG, "-i", raw_file,
            "-ar", "16000", "-ac", "1", "-b:a", "32k",
            mp3_path, "-y"
        ])

        await update.message.reply_text(f"Whisper({model})가 듣고 있어요...")
        await run_command([
            WHISPER, mp3_path,
            "--language", "ko",
            "--model", model,
            "--output_format", "txt",
            "--output_dir", request_dir
        ])

        if custom_name:
            filename = f"{sanitize_filename(custom_name)}.txt"
        else:
            filename = f"transcript_{timestamp}.txt"
        transcript_path = unique_transcript_path(filename)
        filename = os.path.basename(transcript_path)

        if not os.path.exists(whisper_output_path):
            raise Exception("Whisper 결과 파일을 찾을 수 없어요.")

        with open(whisper_output_path, "r", encoding="utf-8") as f:
            transcript = f.read()

        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(f"URL: {url}\n")
            f.write(f"날짜: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"모델: {model}\n")
            f.write("-" * 50 + "\n\n")
            f.write(transcript)

        await update.message.reply_text(f"대본 저장 완료!\n파일: {filename}")
        with open(transcript_path, "rb") as transcript_file:
            await update.message.reply_document(
                document=transcript_file,
                filename=filename,
                caption="전사 대본 파일이에요."
            )

    except Exception as e:
        await update.message.reply_text(f"오류 발생: {str(e)}")

    finally:
        if os.path.exists(request_dir):
            shutil.rmtree(request_dir)

    pending_data.pop(chat_id, None)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending_data.pop(update.effective_chat.id, None)
    await update.message.reply_text("취소했어요.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link)],
    states={
        WAITING_FILENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_filename)],
        WAITING_MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_model)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

validate_startup()
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(conv_handler)
print("봇 시작! 텔레그램에서 링크를 보내보세요")
app.run_polling()
