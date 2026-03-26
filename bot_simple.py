import os
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")

async def start(update, ctx):
    await update.message.reply_text("Selamat datang di IHSG Predictor Bot! Ketik /help")

async def lampu(update, ctx):
    await update.message.reply_text("LAMPU: HIJAU - Kondisi pasar normal.")

async def status(update, ctx):
    baris = [
        "Status Sistem IHSG Predictor:",
        "",
        "Bot        : Online 24 jam di Railway",
        "Model      : 11 sektor (RandomForest)",
        "Saham scan : 38 saham aktif",
        "Akurasi    : 58.74% rata-rata",
        "Overfit    : Tidak ada (semua gap < 10%)",
        "Fitur      : 30 (teknikal + komoditas)",
        "",
        "Komoditas aktif:",
        "- Batu bara - Minyak Brent",
        "- Emas - CPO/Sawit",
        "",
        "Update: 2026-03-26",
    ]
    await update.message.reply_text(chr(10).join(baris))

async def ranking(update, ctx):
    baris = [
        "TOP 10 SAHAM (26 Mar 2026):",
        "",
        "1.  PTBA | Skor:50 | Proba:42% | Tambang",
        "2.  ITMG | Skor:48 | Proba:42% | Tambang",
        "3.  ADRO | Skor:46 | Proba:42% | Tambang",
        "4.  ASII | Skor:42 | Proba:37% | Lainnya",
        "5.  TLKM | Skor:39 | Proba:38% | Telekomunikasi",
        "6.  BMRI | Skor:38 | Proba:33% | Perbankan",
        "7.  ISAT | Skor:38 | Proba:38% | Telekomunikasi",
        "8.  AKRA | Skor:33 | Proba:42% | Energi",
        "9.  ANTM | Skor:33 | Proba:42% | Tambang",
        "10. ABMM | Skor:32 | Proba:38% | Lainnya",
        "",
        "Semua skor < 55 = SKIP hari ini",
        "Model: 11 sektor | Akurasi: 58.74%",
        "Update: 2026-03-26",
    ]
    await update.message.reply_text(chr(10).join(baris))

async def help_cmd(update, ctx):
    baris = [
        "Daftar Perintah IHSG Bot:",
        "",
        "/start   - Menu utama",
        "/ranking - Top 10 saham hari ini",
        "/lampu   - Status kondisi pasar",
        "/status  - Info model dan sistem",
        "/help    - Menu ini",
    ]
    await update.message.reply_text(chr(10).join(baris))

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
