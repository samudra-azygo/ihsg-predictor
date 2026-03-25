import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")

async def start(update, ctx):
    await update.message.reply_text("👋

async def lampu(update, ctx):
    await update.message.reply_text("🟢 *LAMPU: HIJAU*", parse_mode="Markdown")

async def status(update, ctx):
    await update.message.reply_text("🤖

async def ranking(update, ctx):
    await update.message.reply_text("📊 Model belum ditraining.")

async def help_cmd(update, ctx):
    await update.message.reply_text("/start /lampu /ranking /status /help")

async def tombol(update, ctx):
    q = update.callback_query
    await q.answer()

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("lampu", lampu))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("ranking", ranking))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(tombol))
    app.run_polling()

if __name__ == "__main__":
    main()
