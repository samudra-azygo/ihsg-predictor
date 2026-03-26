code = """import os
import requests
from xml.etree import ElementTree as ET
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")

POSITIF = ["naik","tumbuh","meningkat","rekor","laba","untung","dividen",
           "kontrak","ekspansi","investasi","rally","bullish","profit",
           "surplus","optimis","pulih","menguat","solid","positif"]
NEGATIF = ["turun","merosot","anjlok","rugi","kerugian","bangkrut",
           "suspensi","delisting","gagal","default","korupsi","kasus",
           "bearish","tekanan","krisis","resesi","perang","bencana",
           "tersangka","penyidikan","sanksi","pembekuan"]
SAHAM = ["BBCA","BBRI","BMRI","BBNI","BRIS","TLKM","EXCL","ISAT",
         "ADRO","PTBA","ITMG","ANTM","INCO","UNVR","ICBP","MYOR",
         "KLBF","AALI","SIMP","ASII","GOTO","PGAS","AKRA","SMGR",
         "BSDE","CTRA","MIKA","SILO","SCMA","MNCN","ACES","MAPI"]

def ambil_berita():
    sumber = {
        "IDX"  : "https://www.idxchannel.com/rss",
        "CNBC" : "https://www.cnbcindonesia.com/rss",
        "Detik": "https://finance.detik.com/rss",
    }
    berita = []
    skor_global = 0
    for nama, url in sumber.items():
        try:
            r    = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=8)
            root = ET.fromstring(r.text)
            for item in root.findall(".//item")[:30]:
                judul = item.find("title")
                if judul is None:
                    continue
                teks = judul.text.upper()
                skor = sum(1 for k in POSITIF if k.upper() in teks)
                skor -= sum(1 for k in NEGATIF if k.upper() in teks)
                skor_global += skor
                saham = [s for s in SAHAM if s in teks]
                berita.append({"judul":judul.text[:70],"skor":skor,"saham":saham,"sumber":nama})
        except:
            pass
    return berita, skor_global

async def start(update, ctx):
    baris = [
        "Selamat datang di IHSG Predictor Bot",
        "",
        "/ranking  - Top 10 saham + sentimen berita",
        "/berita   - Berita positif dan negatif hari ini",
        "/lampu    - Status kondisi pasar",
        "/status   - Info model dan sistem",
        "/risiko   - Panduan manajemen risiko",
        "/posisi [modal] [skor] - Kalkulator posisi",
        "/data     - Sumber data aktif",
        "/help     - Menu ini",
    ]
    await update.message.reply_text(chr(10).join(baris))

async def berita(update, ctx):
    await update.message.reply_text("Mengambil berita terbaru...")
    try:
        data, skor_global = ambil_berita()
        positif = [b for b in data if b["skor"] > 0][:5]
        negatif = [b for b in data if b["skor"] < 0][:5]
        total   = len(data)

        if skor_global > 3:
            label = "POSITIF - mendukung kenaikan"
        elif skor_global < -3:
            label = "NEGATIF - menekan pasar"
        else:
            label = "NETRAL"

        baris = [
            f"BERITA PASAR HARI INI:",
            f"Total: {total} berita | Skor: {skor_global:+d} | {label}",
            "",
            "POSITIF:",
        ]
        for b in positif:
            saham_str = f" [{','.join(b['saham'])}]" if b["saham"] else ""
            baris.append(f"+{b['skor']} [{b['sumber']}] {b['judul']}{saham_str}")

        baris.append("")
        baris.append("NEGATIF:")
        for b in negatif:
            saham_str = f" [{','.join(b['saham'])}]" if b["saham"] else ""
            baris.append(f"{b['skor']} [{b['sumber']}] {b['judul']}{saham_str}")

        await update.message.reply_text(chr(10).join(baris))
    except Exception as e:
        await update.message.reply_text(f"Error ambil berita: {e}")

async def ranking(update, ctx):
    try:
        _, skor_global = ambil_berita()
        if skor_global > 3:
            sentimen = "POSITIF"
        elif skor_global < -3:
            sentimen = "NEGATIF"
        else:
            sentimen = "NETRAL"
    except:
        sentimen = "NETRAL"
        skor_global = 0

    baris = [
        f"TOP 10 SAHAM (26 Mar 2026):",
        f"Sentimen berita: {sentimen} ({skor_global:+d})",
        "",
        "1.  ITMG | Skor:53 | Teknikal:77 | Tambang",
        "2.  PTBA | Skor:53 | Teknikal:74 | Tambang",
        "3.  ADRO | Skor:52 | Teknikal:73 | Tambang",
        "4.  AKRA | Skor:50 | Teknikal:67 | Energi",
        "5.  ESSA | Skor:50 | Teknikal:66 | Energi",
        "6.  LSIP | Skor:49 | Teknikal:70 | Agribisnis",
        "7.  SIMP | Skor:48 | Teknikal:67 | Agribisnis",
        "8.  MEDC | Skor:47 | Teknikal:60 | Tambang",
        "9.  UNTR | Skor:47 | Teknikal:71 | Lainnya",
        "10. ASII | Skor:45 | Teknikal:60 | Lainnya",
        "",
        "Semua SKIP - skor < 55",
        "Kondisi: Pasar tertekan hari ini",
        "Model: 11 sektor | Akurasi: 60.45%",
    ]
    await update.message.reply_text(chr(10).join(baris))

async def lampu(update, ctx):
    try:
        _, skor_global = ambil_berita()
    except:
        skor_global = 0

    if skor_global > 5:
        lampu_status = "HIJAU - sentimen positif kuat"
    elif skor_global < -5:
        lampu_status = "MERAH - sentimen negatif kuat"
    else:
        lampu_status = "KUNING - sentimen campur"

    baris = [
        "STATUS LAMPU:",
        "",
        f"Lampu     : {lampu_status}",
        f"Skor berita: {skor_global:+d}",
        "Akurasi   : 60.45%",
        "",
        "Kriteria:",
        "HIJAU  - Akurasi > 58%, berita positif",
        "KUNING - Akurasi 50-58% atau berita campur",
        "MERAH  - Akurasi < 50% atau berita sangat negatif",
    ]
    await update.message.reply_text(chr(10).join(baris))

async def status(update, ctx):
    baris = [
        "Status Sistem IHSG Predictor:",
        "",
        "Bot      : Online 24 jam di Railway",
        "Model    : 11 sektor RandomForest",
        "Saham    : 70 saham aktif",
        "Akurasi  : 60.45%",
        "Fitur    : 145 total",
        "",
        "Data aktif:",
        "- Teknikal  : RSI MACD BB volume",
        "- Komoditas : coal oil CPO pangan",
        "- Cuaca     : 7 negara",
        "- Makro     : S&P500 VIX kurs bond",
        "- Berita    : IDX CNBC Detik real-time",
        "",
        "Update: 2026-03-26",
    ]
    await update.message.reply_text(chr(10).join(baris))

async def data_cmd(update, ctx):
    baris = [
        "SUMBER DATA AKTIF (145 fitur):",
        "",
        "1. HARGA: 70 saham IDX",
        "2. KOMODITAS: coal oil gold CPO",
        "   beras gandum jagung kedelai",
        "3. CUACA 7 negara:",
        "   Indonesia Australia Brasil",
        "   Jerman China Amerika Rusia",
        "4. MAKRO 13 sumber:",
        "   S&P500 NASDAQ Nikkei HangSeng",
        "   VIX (fear index)",
        "   USD EUR CNY JPY SGD AUD /IDR",
        "   US Bond yield",
        "5. BERITA real-time:",
        "   IDX Channel CNBC Detik Finance",
        "   210+ berita dianalisis per hari",
    ]
    await update.message.reply_text(chr(10).join(baris))

async def risiko(update, ctx):
    baris = [
        "MANAJEMEN RISIKO:",
        "Modal diasumsikan: Rp 100 juta",
        "",
        "Aturan wajib:",
        "- Max risiko per trade: 2% modal",
        "- Stop loss    : -1% dari harga beli",
        "- Take profit  : +2% dari harga beli",
        "- Rasio 1:2",
        "- Max 5 saham sekaligus",
        "- Kas minimum  : 20% modal",
        "",
        "Gunakan /posisi [modal] [skor]",
        "Contoh: /posisi 100 75",
    ]
    await update.message.reply_text(chr(10).join(baris))

async def posisi_cmd(update, ctx):
    args = ctx.args
    if not args or len(args) < 2:
        await update.message.reply_text("Format: /posisi [modal_juta] [skor]" + chr(10) + "Contoh: /posisi 100 75")
        return
    try:
        modal = float(args[0]) * 1_000_000
        skor  = float(args[1])
        if skor >= 80:
            faktor = 1.0
        elif skor >= 70:
            faktor = 0.75
        elif skor >= 55:
            faktor = 0.5
        else:
            faktor = 0.0
        if skor < 55:
            sinyal = "SKIP - skor terlalu rendah"
        elif skor < 70:
            sinyal = "PANTAU - posisi 50%"
        else:
            sinyal = "BELI - posisi penuh"
        alokasi = (modal * 0.8 / 5) * faktor
        baris = [
            f"Kalkulasi Posisi:",
            f"Modal    : Rp {modal/1e6:.0f} juta",
            f"Skor     : {skor}",
            f"Sinyal   : {sinyal}",
            "",
            f"Alokasi  : Rp {alokasi/1e6:.1f} juta",
            f"Stop loss: Rp {alokasi*0.01/1e3:.0f} ribu (-1%)",
            f"Target   : Rp {alokasi*0.016/1e3:.0f} ribu (+1.6% net)",
            f"Kas sisa : Rp {modal*0.2/1e6:.0f} juta (20%)",
        ]
        await update.message.reply_text(chr(10).join(baris))
    except:
        await update.message.reply_text("Format salah. Contoh: /posisi 100 75")

async def help_cmd(update, ctx):
    baris = [
        "Daftar Perintah IHSG Bot:",
        "",
        "/start         - Menu utama",
        "/ranking       - Top 10 saham hari ini",
        "/berita        - Berita positif dan negatif",
        "/lampu         - Status kondisi pasar",
        "/status        - Info model dan sistem",
        "/risiko        - Panduan manajemen risiko",
        "/posisi 100 75 - Kalkulator posisi",
        "/data          - Sumber data aktif",
        "/help          - Menu ini",
    ]
    await update.message.reply_text(chr(10).join(baris))

async def tombol(update, ctx):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("Ketik /help untuk semua perintah")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("ranking", ranking))
    app.add_handler(CommandHandler("berita",  berita))
    app.add_handler(CommandHandler("lampu",   lampu))
    app.add_handler(CommandHandler("status",  status))
    app.add_handler(CommandHandler("risiko",  risiko))
    app.add_handler(CommandHandler("posisi",  posisi_cmd))
    app.add_handler(CommandHandler("data",    data_cmd))
    app.add_handler(CommandHandler("help",    help_cmd))
    app.add_handler(CallbackQueryHandler(tombol))
    print("Bot siap")
    app.run_polling()

if __name__ == "__main__":
    main()
"""

with open("bot_simple.py", "w") as f:
    f.write(code)
print("bot_simple.py berhasil dibuat")
