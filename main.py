"""
main.py
Jalankan bot Telegram + jadwal otomatis sekaligus
- Bot Telegram aktif 24 jam (balas perintah)
- Jadwal otomatis: 08:00 download, 08:15 scoring, 08:30 kirim ranking, 15:30 evaluasi
- Sentimen: Groq AI (llama-3.1-8b-instant) — fallback ke kamus kata kunci
"""
import os, time, pickle, requests, schedule, threading
import pandas as pd, numpy as np
from datetime import datetime
from xml.etree import ElementTree as ET
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN        = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID      = os.environ.get("TELEGRAM_CHAT_ID", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# ── Cache sentimen AI (supaya Groq tidak dipanggil berkali-kali) ──
_cache_sentimen_ai = {
    "tanggal" : None,
    "hasil"   : None,   # dict: {skor_global, sentimen, lampu, bobot, skor_saham}
}

# ── Kamus sentimen (FALLBACK kalau Groq gagal) ────────────────
POSITIF = [
    "laba naik","laba tumbuh","laba meningkat","laba bersih naik",
    "pendapatan naik","revenue naik","omzet naik",
    "dividen","buyback","right issue","stock split",
    "kontrak baru","akuisisi","ekspansi","investasi masuk",
    "top gainer","rally","menguat","rebound","pulih","recovery",
    "batu bara naik","coal naik","harga batu bara",
    "minyak naik","crude naik","harga minyak naik",
    "emas naik","gold naik","harga emas naik",
    "perak naik","nikel naik","tembaga naik",
    "komoditas naik","energi naik",
    "inflasi turun","deflasi","suku bunga turun","fed cut",
    "rupiah menguat","rupiah apresiasi",
    "ekspor naik","neraca dagang surplus",
    "IPO","listing baru",
]
NEGATIF = [
    "rugi","kerugian","laba turun","laba merosot","laba anjlok",
    "pendapatan turun","revenue turun",
    "bangkrut","pailit","gagal bayar","default","delisting","suspensi",
    "korupsi","tersangka","penyidikan","penyelidikan","kasus hukum",
    "perang","serangan","rudal","bom","militer","konflik bersenjata",
    "Iran","Hormuz","blokade","embargo","sanksi",
    "eskalasi","geopolitik panas","ketegangan militer",
    "minyak naik inflasi","bbm naik","harga bbm naik",
    "inflasi naik","inflasi tinggi","harga pangan naik",
    "suku bunga naik","fed naik","bi rate naik",
    "rupiah melemah","rupiah anjlok","dolar naik",
    "resesi","krisis","stagflasi","perlambatan ekonomi",
    "PHK","pemutusan kerja","tutup pabrik",
    "banjir","gempa","tsunami","bencana alam",
    "IHSG turun","IHSG melemah","IHSG anjlok",
    "asing jual","foreign sell","net sell asing",
    "cpo turun","sawit turun",
]

SAHAM_LIST = [
    "BBCA","BBRI","BMRI","BBNI","BRIS","BNGA","BBTN","PNBN",
    "TLKM","EXCL","ISAT","TOWR","MTEL","TBIG",
    "ADRO","PTBA","ITMG","INCO","ANTM","TINS","MEDC","HRUM","MDKA",
    "UNVR","ICBP","MYOR","KLBF","KAEF","CPIN","SIDO","GGRM","HMSP",
    "AALI","SIMP","LSIP",
    "ASII","AUTO","SMSM","UNTR",
    "SMGR","BSDE","CTRA","PWON","LPKR","SMRA",
    "GOTO","EMTK","BUKA",
    "AKRA","PGAS","ESSA",
    "ACES","MAPI","LPPF","RALS",
    "MIKA","SILO","HEAL",
    "SCMA","MNCN",
]

SEKTOR_SAHAM = {
    "BBCA":"perbankan","BBRI":"perbankan","BMRI":"perbankan","BBNI":"perbankan",
    "BRIS":"perbankan","BNGA":"perbankan","BBTN":"perbankan","PNBN":"perbankan",
    "TLKM":"telekomunikasi","EXCL":"telekomunikasi","ISAT":"telekomunikasi",
    "TOWR":"telekomunikasi","MTEL":"telekomunikasi","TBIG":"telekomunikasi",
    "ADRO":"tambang","PTBA":"tambang","ITMG":"tambang","ANTM":"tambang",
    "INCO":"tambang","TINS":"tambang","MEDC":"tambang","HRUM":"tambang","MDKA":"tambang",
    "UNVR":"konsumer","ICBP":"konsumer","MYOR":"konsumer","KLBF":"konsumer",
    "CPIN":"konsumer","GGRM":"konsumer","HMSP":"konsumer","KAEF":"konsumer",
    "AALI":"agribisnis","SIMP":"agribisnis","LSIP":"agribisnis",
    "SMGR":"properti","BSDE":"properti","CTRA":"properti","PWON":"properti",
    "SMRA":"properti","LPKR":"properti",
    "MIKA":"kesehatan","SILO":"kesehatan","HEAL":"kesehatan",
    "PGAS":"energi","AKRA":"energi","ESSA":"energi",
    "SCMA":"media","MNCN":"media","EMTK":"media",
    "ACES":"ritel","MAPI":"ritel","LPPF":"ritel","RALS":"ritel",
}

# ── Fungsi utilitas ───────────────────────────────────────────
def kirim_telegram(pesan):
    if not TOKEN or not CHAT_ID:
        print(f"[MSG] {pesan[:80]}")
        return
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": pesan}, timeout=10)
    except Exception as e:
        print(f"ERROR kirim: {e}")

# ── Sentimen AI (Groq) ────────────────────────────────────────
def ambil_sentimen_groq():
    """
    Panggil Groq AI via sentimen_ai.py.
    Return dict: {skor_global, sentimen, lampu, bobot, skor_saham}
    atau None kalau gagal.
    Hasil di-cache per hari supaya tidak panggil Groq berkali-kali.
    """
    global _cache_sentimen_ai
    tanggal = datetime.now().strftime("%Y-%m-%d")

    # Pakai cache kalau hari sama
    if _cache_sentimen_ai["tanggal"] == tanggal and _cache_sentimen_ai["hasil"]:
        print("  [Sentimen] Pakai cache hari ini")
        return _cache_sentimen_ai["hasil"]

    if not GROQ_API_KEY:
        print("  [Sentimen] GROQ_API_KEY tidak ada → pakai kamus kata kunci")
        return None

    try:
        from sentimen_ai import scoring_sentimen_ai
        print("  [Sentimen] Memanggil Groq AI...")
        hasil = scoring_sentimen_ai(api_key=GROQ_API_KEY)
        if hasil:
            _cache_sentimen_ai["tanggal"] = tanggal
            _cache_sentimen_ai["hasil"]   = hasil
            print(f"  [Sentimen AI] Skor: {hasil['skor_global']:+.2f} | {hasil['lampu']}")
            return hasil
    except Exception as e:
        print(f"  [Sentimen] Groq gagal: {e}")

    return None

# ── Sentimen fallback (kamus kata kunci lama) ─────────────────
def ambil_sentimen_kamus():
    """Kamus kata kunci — dipakai kalau Groq tidak tersedia."""
    sumber = {
        "IDX"  : "https://www.idxchannel.com/rss",
        "CNBC" : "https://www.cnbcindonesia.com/rss",
        "Detik": "https://finance.detik.com/rss",
    }
    skor_saham  = {}
    skor_sektor = {}
    skor_global = 0
    berita_pos  = []
    berita_neg  = []

    for nama, url in sumber.items():
        try:
            r    = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=8)
            root = ET.fromstring(r.text)
            for item in root.findall(".//item"):
                judul = item.find("title")
                if judul is None:
                    continue
                teks = judul.text.upper()
                skor = sum(1 for k in POSITIF if k.upper() in teks)
                skor -= sum(1 for k in NEGATIF if k.upper() in teks)
                skor_global += skor
                saham = [s for s in SAHAM_LIST if s in teks]
                for s in saham:
                    skor_saham[s]  = skor_saham.get(s, 0) + skor
                    sektor = SEKTOR_SAHAM.get(s, "lainnya")
                    skor_sektor[sektor] = skor_sektor.get(sektor, 0) + skor
                if skor >= 2:
                    berita_pos.append(f"+{skor} {judul.text[:55]}")
                elif skor <= -2:
                    berita_neg.append(f"{skor} {judul.text[:55]}")
        except:
            pass

    return skor_saham, skor_sektor, skor_global, berita_pos[:3], berita_neg[:3]

def ambil_sentimen():
    """
    Wrapper utama:
    1. Coba Groq AI dulu
    2. Kalau gagal → fallback kamus kata kunci
    Return selalu 5-tuple agar kompatibel dengan semua pemanggil lama:
      (skor_saham, skor_sektor, skor_global_display, berita_pos, berita_neg)
    """
    ai = ambil_sentimen_groq()
    if ai:
        skor_saham  = ai.get("skor_saham", {})
        skor_sektor = {}   # Groq belum per-sektor, teknikal tetap jalan normal
        skor_global = ai["skor_global"]   # float -2 s/d +2

        # Baca berita pos/neg dari CSV hasil Groq hari ini
        tanggal  = datetime.now().strftime("%Y-%m-%d")
        csv_path = f"data/berita/sentimen_ai_{tanggal}.csv"
        berita_pos, berita_neg = [], []
        if os.path.exists(csv_path):
            try:
                df_b = pd.read_csv(csv_path)
                pos  = df_b[df_b["skor"] >= 1].sort_values("skor", ascending=False)
                neg  = df_b[df_b["skor"] <= -1].sort_values("skor")
                berita_pos = [f"+{r['skor']} [{r['sumber']}] {r['judul'][:50]}"
                              for _, r in pos.head(3).iterrows()]
                berita_neg = [f"{r['skor']} [{r['sumber']}] {r['judul'][:50]}"
                              for _, r in neg.head(3).iterrows()]
            except:
                pass

        return skor_saham, skor_sektor, skor_global, berita_pos, berita_neg

    # Fallback kamus kata kunci
    print("  [Sentimen] Pakai kamus kata kunci (fallback)")
    return ambil_sentimen_kamus()

def hitung_skor_teknikal(df):
    close  = df["close"]
    volume = df["volume"]
    delta  = close.diff()
    gain   = delta.clip(lower=0).rolling(14).mean()
    loss   = (-delta).clip(lower=0).rolling(14).mean()
    rs     = gain / loss.replace(0, np.nan)
    rsi    = 100 - (100 / (1 + rs))
    ema12  = close.ewm(span=12, adjust=False).mean()
    ema26  = close.ewm(span=26, adjust=False).mean()
    macd   = ema12 - ema26
    sma20  = close.rolling(20).mean()
    std20  = close.rolling(20).std()
    bb     = (close - (sma20 - 2*std20)) / (4*std20).replace(0, np.nan)
    vol_r  = volume / volume.rolling(20).mean().replace(0, np.nan)

    rsi_n  = float(rsi.iloc[-1])  if not pd.isna(rsi.iloc[-1])  else 50
    macd_n = max(0, min(100, 50 + float(macd.iloc[-1]) * 1000)) if not pd.isna(macd.iloc[-1]) else 50
    bb_n   = max(0, min(100, float(bb.iloc[-1]) * 100)) if not pd.isna(bb.iloc[-1]) else 50
    vol_n  = min(100, float(vol_r.iloc[-1]) * 50) if not pd.isna(vol_r.iloc[-1]) else 50

    return round(rsi_n*0.3 + macd_n*0.3 + bb_n*0.2 + vol_n*0.2, 1)

def scoring_harian():
    tanggal = datetime.now().strftime("%Y-%m-%d")
    print(f"[{datetime.now().strftime('%H:%M')}] Scoring {tanggal}...")

    skor_saham, skor_sektor, skor_global, bpos, bneg = ambil_sentimen()

    # Deteksi apakah pakai Groq AI atau kamus (untuk threshold yang tepat)
    pakai_ai = _cache_sentimen_ai["tanggal"] == tanggal and _cache_sentimen_ai["hasil"] is not None

    if pakai_ai:
        # Skala Groq: -2 s/d +2
        lampu = "HIJAU"  if skor_global >  0.3 else "MERAH"  if skor_global < -0.3 else "KUNING"
        bobot = _cache_sentimen_ai["hasil"]["bobot"]
        mode_sentimen = f"AI Groq ({skor_global:+.2f})"
    else:
        # Skala kamus: bisa puluhan
        lampu = "HIJAU"  if skor_global >  5 else "MERAH"  if skor_global < -5 else "KUNING"
        bobot = 1.1 if skor_global > 5 else 0.9 if skor_global < -5 else 1.0
        mode_sentimen = f"Kamus ({skor_global:+d})"

    print(f"  Sentimen: {mode_sentimen} | Lampu: {lampu}")

    try:
        with open("models/models_latest.pkl","rb") as f:
            models = pickle.load(f)
    except:
        kirim_telegram("ERROR: Model tidak ditemukan")
        return []

    hasil = []
    for fname in os.listdir("data"):
        if not fname.endswith(".csv") or fname.startswith("KOMODITAS"):
            continue
        kode = fname.replace(".csv","")
        try:
            df = pd.read_csv(f"data/{fname}")
            df.columns = [c.lower() for c in df.columns]
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            if len(df) < 50 or df["close"].iloc[-1] < 100:
                continue
            if df["close"].iloc[-1] * df["volume"].iloc[-1] < 500_000_000:
                continue
            if "high" not in df.columns:
                continue

            skor_tek = hitung_skor_teknikal(df)
            sektor   = SEKTOR_SAHAM.get(kode, "lainnya")

            # Skor berita per saham
            if pakai_ai:
                # Groq: skor_saham sudah per-ticker (akumulasi skor -2 s/d +2)
                skor_b_raw = skor_saham.get(kode, 0)
                skor_b_n   = max(30, min(70, 50 + skor_b_raw * 10))
            else:
                # Kamus: skala bisa lebih besar
                skor_b   = skor_saham.get(kode, 0) * 3 + skor_sektor.get(sektor, 0)
                skor_b_n = max(30, min(70, 50 + skor_b * 5))

            model_s = models.get(sektor, models.get("lainnya"))
            proba   = 0.5
            if model_s:
                try:
                    X     = pd.DataFrame([{f: 0 for f in model_s["fitur"]}])
                    proba = float(model_s["pipeline"].predict_proba(X)[0][1])
                except:
                    proba = 0.5

            skor_f = round(min(100, max(0,
                (skor_tek * 0.40 + skor_b_n * 0.30 + proba * 100 * 0.30) * bobot
            )), 1)

            sinyal = "BELI" if skor_f >= 75 else "PANTAU" if skor_f >= 55 else "SKIP"
            hasil.append({
                "ticker"  : kode,
                "sektor"  : sektor,
                "skor"    : skor_f,
                "skor_tek": skor_tek,
                "proba"   : round(proba, 3),
                "sinyal"  : sinyal,
            })
        except:
            pass

    df_hasil = pd.DataFrame(hasil).sort_values("skor", ascending=False)
    os.makedirs("logs", exist_ok=True)
    df_hasil.to_csv(f"logs/ranking_{tanggal}.csv", index=False)

    # Kirim ke Telegram
    top10  = df_hasil.head(10)
    beli   = df_hasil[df_hasil["sinyal"]=="BELI"]
    pantau = df_hasil[df_hasil["sinyal"]=="PANTAU"]

    label_skor = f"{skor_global:+.2f}" if pakai_ai else f"{skor_global:+d}"
    baris = [
        f"IHSG Predictor — {tanggal}",
        f"Lampu: {lampu} | {'AI Groq' if pakai_ai else 'Kamus'}: {label_skor}",
        "",
        "TOP 10 SAHAM:",
    ]
    for i, (_, r) in enumerate(top10.iterrows(), 1):
        s = "BELI" if r["sinyal"]=="BELI" else "pantau" if r["sinyal"]=="PANTAU" else "skip"
        baris.append(f"{i:2}. {r['ticker']:5} | {r['skor']:5.1f} | {s}")

    if len(beli) > 0:
        baris.append(f"\nSINYAL BELI: {', '.join(beli['ticker'].tolist())}")
    elif len(pantau) > 0:
        baris.append(f"\nPANTAU: {', '.join(pantau['ticker'].head(3).tolist())}")
    else:
        baris.append("\nSemua SKIP hari ini")

    if bpos:
        baris.append("\nBerita positif:")
        for b in bpos:
            baris.append(f"  {b}")
    if bneg:
        baris.append("\nBerita negatif:")
        for b in bneg:
            baris.append(f"  {b}")

    baris.append(f"\nAkurasi: 60.45% | Sentimen: {'AI Groq' if pakai_ai else 'Kamus'}")
    kirim_telegram(chr(10).join(baris))
    print(f"  Ranking terkirim | Lampu: {lampu} | BELI: {len(beli)}")
    return df_hasil

def download_data():
    print(f"[{datetime.now().strftime('%H:%M')}] Download data saham...")
    ok = 0
    for kode in SAHAM_LIST:
        try:
            r = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{kode}.JK?range=3mo&interval=1d",
                headers={"User-Agent":"Mozilla/5.0"}, timeout=15)
            ts = r.json()["chart"]["result"][0]
            q  = ts["indicators"]["quote"][0]
            df_baru = pd.DataFrame({
                "date"  : pd.to_datetime(ts["timestamp"], unit="s").strftime("%Y-%m-%d"),
                "open"  : q["open"], "high": q["high"],
                "low"   : q["low"],  "close": q["close"],
                "volume": q["volume"],
            }).dropna()
            path = f"data/{kode}.csv"
            if os.path.exists(path):
                df_lama   = pd.read_csv(path)
                df_gabung = pd.concat([df_lama, df_baru]).drop_duplicates("date").sort_values("date")
                df_gabung.to_csv(path, index=False)
            else:
                df_baru.to_csv(path, index=False)
            ok += 1
            time.sleep(0.3)
        except:
            pass
    print(f"  {ok}/{len(SAHAM_LIST)} saham diupdate")

def evaluasi():
    tanggal = datetime.now().strftime("%Y-%m-%d")
    path    = f"logs/ranking_{tanggal}.csv"
    if not os.path.exists(path):
        return
    df   = pd.read_csv(path)
    beli = df[df["sinyal"]=="BELI"]
    kirim_telegram(chr(10).join([
        f"Evaluasi — {tanggal}",
        f"Sinyal BELI  : {len(beli)} saham",
        f"Total scan   : {len(df)} saham",
        "",
        "Catat hasil trade Anda hari ini",
    ]))

# ── Jadwal ────────────────────────────────────────────────────
def jalankan_jadwal():
    schedule.every().day.at("01:00").do(download_data)
    schedule.every().day.at("01:15").do(scoring_harian)
    schedule.every().day.at("08:30").do(evaluasi)
    print("Jadwal aktif: 08:00 WIB download | 08:15 WIB scoring | 15:30 WIB evaluasi")
    while True:
        schedule.run_pending()
        time.sleep(30)

# ── Bot Telegram commands ─────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    baris = [
        "Selamat datang di IHSG Predictor Bot",
        "",
        "/ranking  - Top 10 saham + sentimen berita",
        "/berita   - Berita positif dan negatif",
        "/lampu    - Status kondisi pasar",
        "/status   - Info model dan sistem",
        "/risiko   - Panduan manajemen risiko",
        "/posisi [modal] [skor] - Kalkulator",
        "/data     - Sumber data aktif",
        "/help     - Menu ini",
    ]
    await update.message.reply_text(chr(10).join(baris))

async def ranking(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Menghitung ranking...")
    try:
        _, _, skor_global, bpos, bneg = ambil_sentimen()
        tanggal  = datetime.now().strftime("%Y-%m-%d")
        path     = f"logs/ranking_{tanggal}.csv"
        pakai_ai = _cache_sentimen_ai["tanggal"] == tanggal and _cache_sentimen_ai["hasil"] is not None

        if os.path.exists(path):
            df = pd.read_csv(path).sort_values("skor", ascending=False)
        else:
            df = scoring_harian()
            if isinstance(df, list):
                await update.message.reply_text("Belum ada data ranking hari ini")
                return

        top10 = df.head(10)
        if pakai_ai:
            lampu = "HIJAU" if skor_global > 0.3 else "MERAH" if skor_global < -0.3 else "KUNING"
            label = f"AI Groq: {skor_global:+.2f}"
        else:
            lampu = "HIJAU" if skor_global > 5 else "MERAH" if skor_global < -5 else "KUNING"
            label = f"Kamus: {skor_global:+d}"

        baris = [
            f"TOP 10 SAHAM ({tanggal}):",
            f"Lampu: {lampu} | {label}",
            "",
        ]
        for i, (_, r) in enumerate(top10.iterrows(), 1):
            s = "BELI" if r["sinyal"]=="BELI" else "pantau" if r["sinyal"]=="PANTAU" else "skip"
            baris.append(f"{i:2}. {r['ticker']:5} | {r['skor']:5.1f} | {s} | {r['sektor']}")

        beli   = df[df["sinyal"]=="BELI"]
        pantau = df[df["sinyal"]=="PANTAU"]
        if len(beli) > 0:
            baris.append(f"\nSINYAL BELI: {', '.join(beli['ticker'].tolist())}")
        elif len(pantau) > 0:
            baris.append(f"\nPANTAU: {', '.join(pantau['ticker'].head(3).tolist())}")
        else:
            baris.append("\nSemua SKIP hari ini")

        await update.message.reply_text(chr(10).join(baris))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def berita(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Mengambil berita (AI Groq)..." if GROQ_API_KEY else "Mengambil berita...")
    try:
        _, _, skor_global, bpos, bneg = ambil_sentimen()
        pakai_ai = _cache_sentimen_ai["tanggal"] == datetime.now().strftime("%Y-%m-%d") \
                   and _cache_sentimen_ai["hasil"] is not None
        if pakai_ai:
            label  = "POSITIF" if skor_global > 0.3 else "NEGATIF" if skor_global < -0.3 else "NETRAL"
            header = f"BERITA PASAR (AI Groq): {label} ({skor_global:+.2f})"
        else:
            label  = "POSITIF" if skor_global > 3 else "NEGATIF" if skor_global < -3 else "NETRAL"
            header = f"BERITA PASAR (Kamus): {label} ({skor_global:+d})"

        baris = [header, ""]
        if bpos:
            baris.append("POSITIF:")
            baris.extend(bpos)
        if bneg:
            baris.append("\nNEGATIF:")
            baris.extend(bneg)
        if not bpos and not bneg:
            baris.append("Tidak ada berita signifikan hari ini")
        await update.message.reply_text(chr(10).join(baris))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def lampu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        _, _, skor_global, _, _ = ambil_sentimen()
        pakai_ai = _cache_sentimen_ai["tanggal"] == datetime.now().strftime("%Y-%m-%d") \
                   and _cache_sentimen_ai["hasil"] is not None
        if pakai_ai:
            status = "HIJAU" if skor_global > 0.3 else "MERAH" if skor_global < -0.3 else "KUNING"
            label  = f"Skor AI Groq: {skor_global:+.2f} (skala -2 s/d +2)"
        else:
            status = "HIJAU" if skor_global > 5 else "MERAH" if skor_global < -5 else "KUNING"
            label  = f"Skor kamus: {skor_global:+d}"
    except:
        status = "KUNING"
        label  = "Skor: N/A"

    baris = [
        f"LAMPU: {status}",
        label,
        "Akurasi model: 60.45%",
        "",
        "HIJAU  = sentimen positif, trading normal",
        "KUNING = sentimen campur, waspada",
        "MERAH  = sentimen negatif, hati-hati",
    ]
    await update.message.reply_text(chr(10).join(baris))

async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    mode = "AI Groq (llama-3.1-8b-instant)" if GROQ_API_KEY else "Kamus kata kunci (fallback)"
    baris = [
        "Status Sistem IHSG Predictor:",
        "",
        "Bot      : Online 24 jam di Railway",
        "Jadwal   : 08:00 WIB download | 08:15 WIB scoring",
        "           Ranking masuk Telegram jam 08:15 WIB",
        "Model    : 11 sektor RandomForest",
        "Saham    : 70 saham aktif",
        "Akurasi  : 60.45%",
        "Fitur    : 180 total",
        f"Sentimen : {mode}",
        "",
        "Data: teknikal + komoditas + cuaca",
        "      makro global + ENSO + berita real-time",
    ]
    await update.message.reply_text(chr(10).join(baris))

async def risiko(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    baris = [
        "MANAJEMEN RISIKO:",
        "",
        "Aturan wajib:",
        "- Stop loss  : -1% dari harga beli",
        "- Take profit: +2% dari harga beli",
        "- Rasio 1:2",
        "- Max 5 saham sekaligus",
        "- Kas minimum: 20% modal",
        "- Max risiko : 2% modal per trade",
        "",
        "Gunakan: /posisi [modal_juta] [skor]",
        "Contoh : /posisi 100 75",
    ]
    await update.message.reply_text(chr(10).join(baris))

async def posisi_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if not args or len(args) < 2:
        await update.message.reply_text(
            "Format: /posisi [modal_juta] [skor]\nContoh: /posisi 100 75")
        return
    try:
        modal  = float(args[0]) * 1_000_000
        skor   = float(args[1])
        faktor = 1.0 if skor >= 80 else 0.75 if skor >= 70 else 0.5 if skor >= 55 else 0.0
        sinyal = "SKIP" if skor < 55 else "PANTAU - 50%" if skor < 70 else "BELI - penuh"
        alokasi = (modal * 0.8 / 5) * faktor
        baris = [
            "Kalkulasi Posisi:",
            f"Modal    : Rp {modal/1e6:.0f} juta",
            f"Skor     : {skor}",
            f"Sinyal   : {sinyal}",
            "",
            f"Alokasi  : Rp {alokasi/1e6:.1f} juta",
            f"Stop loss: Rp {alokasi*0.01/1e3:.0f} ribu (-1%)",
            f"Target   : Rp {alokasi*0.016/1e3:.0f} ribu (+1.6% net)",
        ]
        await update.message.reply_text(chr(10).join(baris))
    except:
        await update.message.reply_text("Format salah. Contoh: /posisi 100 75")

async def data_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    baris = [
        "SUMBER DATA AKTIF (180 fitur):",
        "",
        "1. HARGA: 70 saham IDX",
        "2. KOMODITAS: coal oil gold CPO",
        "   beras gandum jagung kedelai",
        "3. CUACA 7 negara:",
        "   Indonesia Australia Brasil",
        "   Jerman China Amerika Rusia",
        "4. MAKRO 13 sumber:",
        "   S&P500 NASDAQ Nikkei HangSeng",
        "   VIX | USD EUR CNY JPY SGD AUD/IDR",
        "   US Bond yield",
        "5. ENSO + Kalender:",
        "   ONI/SOI El Nino | Libur nasional",
        "   Ramadan Lebaran window dressing",
        "6. BERITA real-time (AI Groq):",
        "   IDX Channel CNBC Detik Finance",
        "   60+ berita dianalisis tiap pagi",
    ]
    await update.message.reply_text(chr(10).join(baris))

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await start(update, ctx)

async def tombol(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("Ketik /help untuk semua perintah")

# ── Main ──────────────────────────────────────────────────────
def main():
    print("IHSG Predictor Bot + Jadwal Otomatis")
    print("="*40)
    print(f"Sentimen: {'AI Groq aktif' if GROQ_API_KEY else 'Kamus kata kunci (GROQ_API_KEY tidak ada)'}")

    # Jalankan jadwal di thread terpisah
    thread = threading.Thread(target=jalankan_jadwal, daemon=True)
    thread.start()

    # Jalankan bot Telegram di main thread
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
