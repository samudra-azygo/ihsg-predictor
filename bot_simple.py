import os
import pandas as pd
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")

async def start(update, ctx):
    await update.message.reply_text("Selamat datang di IHSG Bot! Ketik /help")

async def lampu(update, ctx):
    await update.message.reply_text("LAMPU: HIJAU - Kondisi pasar normal.")

async def status(update, ctx):
    await update.message.reply_text("Status: Online - Bot berjalan 24 jam!")

async def ranking(update, ctx):
    teks = "TOP 5 SAHAM HARI INI:

"
    teks += "1. BMRI | Skor: 51 | SKIP | Proba: 65%
"
    teks += "2. PTBA | Skor: 51 | SKIP | Proba: 47%
"
    teks += "3. ITMG | Skor: 50 | SKIP | Proba: 47%
"
    teks += "4. ADRO | Skor: 48 | SKIP | Proba: 47%
"
    teks += "5. ASII | Skor: 46 | SKIP | Proba: 48%
"
    teks += "
Data: 2026-03-25"
    await update.message.reply_text(teks)

async def help_cmd(update, ctx):
    await update.message.reply_text("/start /lampu /ranking /status /help")

async def tombol(update, ctx):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("OK")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("lampu", lampu))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("ranking", ranking))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(tombol))
    print("Bot siap!")
    app.run_polling()

if __name__ == "__main__":
    main()