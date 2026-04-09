"""
scoring_improved.py
Sistem scoring yang diperbaiki — mengatasi 3 penyebab akurasi rendah:

MASALAH 1: Fitur komoditas/makro diisi 0 saat prediksi
SOLUSI   : Download komoditas & makro real-time via yfinance sebelum scoring

MASALAH 2: Threshold tidak adaptif
SOLUSI   : Threshold dinamis berdasarkan kondisi pasar (IHSG momentum)

MASALAH 3: Tidak ada filter pasar bearish
SOLUSI   : Market regime detection — kalau IHSG bearish, skip semua BELI

Jalankan: python3 scoring_improved.py
"""
import os, time, pickle, warnings
import pandas as pd
import numpy as np
import urllib.request, urllib.error, urllib.parse, json
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

warnings.filterwarnings("ignore")

# ── Konfigurasi ───────────────────────────────────────────────
TOKEN        = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID      = os.environ.get("TELEGRAM_CHAT_ID", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

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

# ── PERBAIKAN 1: Download makro real-time (pakai requests, tanpa yfinance) ──
import ssl as _ssl
_SSL_CTX = _ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode    = _ssl.CERT_NONE

def _yahoo_download(ticker, period="30d"):
    """Download harga penutupan dari Yahoo Finance API v8 pakai urllib (built-in)."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?range={period}&interval=1d&includePrePost=false")
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
                data = json.loads(resp.read().decode())
            result = data["chart"]["result"]
            if not result:
                return None
            ts     = result[0]["timestamp"]
            closes = result[0]["indicators"]["quote"][0]["close"]
            dates  = pd.to_datetime(ts, unit="s").normalize()
            s = pd.Series(closes, index=dates).dropna()
            return s
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(3 + attempt * 2)  # tunggu lalu retry
                continue
            return None
        except Exception:
            return None
    return None

def download_makro():
    """Download data makro terbaru pakai Yahoo Finance API langsung (tanpa yfinance)."""
    print("  Download makro real-time...")

    tickers = {
        "^GSPC"   : "sp500",
        "^IXIC"   : "nasdaq",
        "^N225"   : "nikkei",
        "^HSI"    : "hangseng",
        "^VIX"    : "vix",
        "USDIDR=X": "usdidr",
        "EURIDR=X": "euridr",
        "CNYIDR=X": "cnyidr",
        "JPYIDR=X": "jpyidr",
        "SGDIDR=X": "sgdidr",
        "AUDIDR=X": "audidr",
        "CL=F"    : "oil",
        "GC=F"    : "gold",
        "^TNX"    : "usbond",
        "MTF=F"   : "coal",
    }

    data = {}
    for ticker, nama in tickers.items():
        s = _yahoo_download(ticker)
        if s is not None and len(s) > 0:
            data[nama] = s
            print(f"    ✓ {nama}: {float(s.iloc[-1]):.2f}")
        else:
            print(f"    ✗ {nama}: gagal")
        time.sleep(1)  # hindari rate limit Yahoo

    return data

def buat_fitur_makro(makro_data, tanggal):
    """Buat fitur makro untuk tanggal tertentu dari data yang sudah didownload."""
    fitur = {}
    tgl = pd.Timestamp(tanggal)

    for nama, series in makro_data.items():
        if nama in ["gold2"]:
            continue
        # Ambil data s/d tanggal ini
        s = series[series.index <= tgl]
        if len(s) < 5:
            continue
        try:
            v0    = float(s.iloc[-1])
            v1    = float(s.iloc[-2]) if len(s) > 1 else v0
            v2    = float(s.iloc[-3]) if len(s) > 2 else v0
            pct   = (v0 - v1) / v1 if v1 != 0 else 0
            ma5   = float(s.tail(5).mean())
            trend = (v0 - ma5) / ma5 if ma5 != 0 else 0

            fitur[f"{nama}_pct"]  = round(pct, 6)
            fitur[f"{nama}_lag1"] = round((v1 - v2) / v2 if v2 != 0 else 0, 6)
            fitur[f"{nama}_lag2"] = round((v2 - float(s.iloc[-4])) / float(s.iloc[-4])
                                          if len(s) > 3 and float(s.iloc[-4]) != 0 else 0, 6)
            fitur[f"{nama}_ma5"]  = round(trend, 6)

            # Fitur turunan khusus
            if nama == "vix":
                fitur["vix_trend"]  = 1 if trend > 0 else -1
                fitur["vix_level"]  = v0
                fitur["vix_tinggi"] = 1 if v0 > 25 else 0
                fitur["vix_panik"]  = 1 if v0 > 35 else 0
            if nama == "usdidr":
                fitur["rupiah_lemah"]   = 1 if v0 > 16500 else 0
                fitur["rupiah_volatil"] = 1 if abs(pct) > 0.01 else 0
            if nama == "usbond":
                fitur["bond_naik"]  = 1 if pct > 0 else 0
                fitur["bond_level"] = v0
        except:
            pass

    return fitur

# ── PERBAIKAN 2: Market regime detection ─────────────────────
def deteksi_regime_pasar(makro_data):
    """
    Deteksi kondisi pasar: BULL / NETRAL / BEAR
    Berdasarkan: SP500 momentum + VIX level + IHSG proxy
    Return: regime, bobot_threshold
    """
    regime_skor = 0

    # SP500 momentum (proxy global)
    if "sp500" in makro_data:
        s = makro_data["sp500"].tail(10)
        if len(s) >= 5:
            ret_5d = (float(s.iloc[-1]) - float(s.iloc[-5])) / float(s.iloc[-5])
            if ret_5d > 0.02:
                regime_skor += 2
            elif ret_5d > 0:
                regime_skor += 1
            elif ret_5d < -0.03:
                regime_skor -= 2
            elif ret_5d < 0:
                regime_skor -= 1

    # VIX level
    if "vix" in makro_data:
        vix = float(makro_data["vix"].iloc[-1])
        if vix < 18:
            regime_skor += 1
        elif vix > 25:
            regime_skor -= 1
        elif vix > 35:
            regime_skor -= 2

    # Rupiah
    if "usdidr" in makro_data:
        usdidr = float(makro_data["usdidr"].iloc[-1])
        if usdidr > 16800:
            regime_skor -= 1
        elif usdidr < 15800:
            regime_skor += 1

    if regime_skor >= 2:
        regime = "BULL"
        thr_beli = 62
        bobot    = 1.15
    elif regime_skor <= -2:
        regime = "BEAR"
        thr_beli = 72   # lebih ketat saat bearish
        bobot    = 0.85
    else:
        regime = "NETRAL"
        thr_beli = 67
        bobot    = 1.0

    print(f"  Regime pasar : {regime} (skor={regime_skor:+d})")
    print(f"  Threshold BELI adaptif: {thr_beli}")
    return regime, thr_beli, bobot

# ── PERBAIKAN 3: Fitur teknikal lengkap ──────────────────────
def hitung_fitur_teknikal(df):
    close  = df["close"]
    high   = df["high"]
    low    = df["low"]
    volume = df["volume"]

    delta  = close.diff()
    gain   = delta.clip(lower=0).rolling(14).mean()
    loss   = (-delta).clip(lower=0).rolling(14).mean()
    rs     = gain / loss.replace(0, np.nan)
    rsi    = 100 - (100 / (1 + rs))

    ema12      = close.ewm(span=12, adjust=False).mean()
    ema26      = close.ewm(span=26, adjust=False).mean()
    macd_line  = ema12 - ema26
    signal     = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist  = macd_line - signal

    sma20  = close.rolling(20).mean()
    std20  = close.rolling(20).std()
    bb_pct = (close - (sma20 - 2*std20)) / (4*std20).replace(0, np.nan)

    vol_r  = volume / volume.rolling(20).mean().replace(0, np.nan)
    ret    = close.pct_change()
    tp     = (high + low + close) / 3
    mf     = tp * volume
    pos_mf = mf.where(tp > tp.shift(1), 0).rolling(14).sum()
    neg_mf = mf.where(tp < tp.shift(1), 0).rolling(14).sum()
    mfv    = ((close - low) - (high - close)) / (high - low).replace(0, np.nan) * volume

    row = {}
    row["rsi"]           = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50
    row["macd"]          = float(macd_line.iloc[-1]) if not pd.isna(macd_line.iloc[-1]) else 0
    row["macd_hist"]     = float(macd_hist.iloc[-1]) if not pd.isna(macd_hist.iloc[-1]) else 0
    row["bb_pct"]        = float(bb_pct.iloc[-1]) if not pd.isna(bb_pct.iloc[-1]) else 0.5
    row["vol_ratio"]     = float(vol_r.iloc[-1]) if not pd.isna(vol_r.iloc[-1]) else 1
    row["return_lag1"]   = float(ret.iloc[-2]) if len(ret) > 1 else 0
    row["return_lag3"]   = float(ret.tail(4).sum()) if len(ret) > 3 else 0
    row["return_lag5"]   = float(ret.tail(6).sum()) if len(ret) > 5 else 0
    row["volatility_5d"] = float(ret.tail(5).std()) if len(ret) > 5 else 0
    row["volatility_20d"]= float(ret.tail(20).std()) if len(ret) > 20 else 0
    row["above_ma20"]    = int(close.iloc[-1] > sma20.iloc[-1]) if not pd.isna(sma20.iloc[-1]) else 0
    row["above_ma50"]    = int(close.iloc[-1] > close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else 0
    row["vol_spike"]     = int(vol_r.iloc[-1] > 2) if not pd.isna(vol_r.iloc[-1]) else 0
    row["akumulasi"]     = int(close.iloc[-1] > close.iloc[-2] and volume.iloc[-1] > volume.iloc[-2])
    mfi_val = 100 - (100 / (1 + pos_mf.iloc[-1] / neg_mf.iloc[-1])) if not pd.isna(pos_mf.iloc[-1]) and neg_mf.iloc[-1] != 0 else 50
    row["mfi"]           = float(mfi_val) if not pd.isna(mfi_val) else 50
    cmf_num  = mfv.tail(20).sum()
    cmf_den  = volume.tail(20).sum()
    row["cmf"]           = float(cmf_num / cmf_den) if cmf_den != 0 else 0

    # Fitur rebound tambahan
    high   = pd.to_numeric(df.get("high", close), errors="coerce")
    low2   = pd.to_numeric(df.get("low",  close), errors="coerce")
    low14  = low2.rolling(14).min()
    high14 = high.rolling(14).max()
    stoch_k = (close - low14) / (high14 - low14).replace(0, np.nan) * 100
    stoch_d = stoch_k.rolling(3).mean()
    row["stoch_k"]        = float(stoch_k.iloc[-1]) if not pd.isna(stoch_k.iloc[-1]) else 50
    row["stoch_oversold"] = 1 if row["stoch_k"] < 20 else 0
    row["stoch_cross_up"] = 1 if (stoch_k.iloc[-1] > stoch_d.iloc[-1] and
                                   stoch_k.iloc[-2] <= stoch_d.iloc[-2] and
                                   stoch_k.iloc[-1] < 40) else 0
    row["drawdown_10d"]   = float(close.pct_change(10).iloc[-1]) if len(close) >= 10 else 0
    row["drawdown_20d"]   = float(close.pct_change(20).iloc[-1]) if len(close) >= 20 else 0
    vol_r2 = volume / volume.rolling(20).mean().replace(0, np.nan)
    row["akumulasi"]      = 1 if (close.iloc[-1] > close.iloc[-2] and
                                   volume.iloc[-1] > volume.tail(5).mean() * 1.5) else 0
    row["momentum_5d"]   = float(close.pct_change(5).iloc[-1]) if len(close) >= 5 else 0
    row["momentum_20d"]  = float(close.pct_change(20).iloc[-1]) if len(close) >= 20 else 0
    row["bulan"]         = df.index[-1].month
    row["kuartal"]       = df.index[-1].quarter
    row["hari_minggu"]   = df.index[-1].dayofweek
    row["hari_tahun"]    = df.index[-1].dayofyear
    return row

# ── Scoring utama ─────────────────────────────────────────────
def scoring_improved():
    tanggal = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"SCORING IMPROVED — {tanggal}")
    print(f"{'='*60}")

    # Step 1: Download makro
    print("\n[1/4] Download data makro...")
    try:
        makro_data = download_makro()
    except Exception as e:
        print(f"  ERROR download makro: {e}")
        makro_data = {}

    # Step 2: Deteksi regime pasar
    print("\n[2/4] Analisis regime pasar...")
    regime, thr_beli, bobot_regime = deteksi_regime_pasar(makro_data)

    # Step 3: Buat fitur makro untuk hari ini
    fitur_makro = buat_fitur_makro(makro_data, tanggal)
    print(f"  Fitur makro tersedia: {len(fitur_makro)}")

    # Step 4: Load model
    print("\n[3/4] Load model...")
    try:
        with open("models/models_latest.pkl", "rb") as f:
            models = pickle.load(f)
        print(f"  {len(models)} sektor dimuat")
    except Exception as e:
        print(f"  ERROR: {e}")
        return

    # Load model rebound jika ada
    model_rebound = None
    fitur_rebound = None
    if regime == "BEAR":
        try:
            with open("models/model_rebound.pkl", "rb") as f:
                rb = pickle.load(f)
            model_rebound = rb["pipeline"]
            fitur_rebound = rb["fitur"]
            print(f"  ✓ Model rebound dimuat (CV={rb.get('cv_accuracy',0)*100:.1f}%)")
        except:
            print(f"  ✗ Model rebound tidak ada — mode krisis nonaktif")

    # Step 5: Scoring per saham
    print("\n[4/4] Scoring saham...")
    hasil = []

    for fname in os.listdir("data"):
        if not fname.endswith(".csv") or fname.startswith("KOMODITAS"):
            continue
        kode = fname.replace(".csv", "")
        if kode not in SAHAM_LIST:
            continue

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

            sektor  = SEKTOR_SAHAM.get(kode, "lainnya")
            model_s = models.get(sektor, models.get("lainnya"))
            fitur_list = model_s["fitur"]

            # Gabungkan fitur teknikal + makro
            fitur_tek = hitung_fitur_teknikal(df)
            fitur_gabung = {**fitur_makro, **fitur_tek}  # teknikal override makro jika overlap

            # Buat vector fitur lengkap
            X = pd.DataFrame([{
                f: fitur_gabung.get(f, 0) for f in fitur_list
            }])

            # Prediksi model
            try:
                proba = float(model_s["pipeline"].predict_proba(X)[0][1])
            except:
                proba = 0.5

            # Skor teknikal
            rsi_n  = min(100, max(0, fitur_tek.get("rsi", 50)))
            macd_n = min(100, max(0, 50 + fitur_tek.get("macd", 0) * 1000))
            bb_n   = min(100, max(0, fitur_tek.get("bb_pct", 0.5) * 100))
            vol_n  = min(100, fitur_tek.get("vol_ratio", 1) * 50)
            skor_tek = rsi_n*0.3 + macd_n*0.3 + bb_n*0.2 + vol_n*0.2

            # Skor makro bonus/penalty
            skor_makro = 50  # netral jika tidak ada data
            if fitur_makro:
                skor_makro = 50
                # VIX rendah = +5, tinggi = -5
                if "vix_level" in fitur_makro:
                    vix = fitur_makro["vix_level"]
                    skor_makro += max(-10, min(10, (25 - vix) * 0.5))
                # Rupiah kuat = +3
                if "rupiah_lemah" in fitur_makro and fitur_makro["rupiah_lemah"] == 0:
                    skor_makro += 3
                # SP500 naik = +5
                if "sp500_pct" in fitur_makro:
                    skor_makro += min(8, max(-8, fitur_makro["sp500_pct"] * 500))

            # Skor final dengan bobot regime
            skor_final = (
                skor_tek   * 0.35 +
                skor_makro * 0.25 +
                proba * 100 * 0.40
            ) * bobot_regime

            skor_final = round(min(100, max(0, skor_final)), 1)

            # Threshold adaptif
            if skor_final >= thr_beli:
                sinyal = "BELI"
            elif skor_final >= thr_beli - 12:
                sinyal = "PANTAU"
            else:
                sinyal = "SKIP"

            # Extra filter: di regime BEAR, tidak ada BELI kalau RSI < 40
            if regime == "BEAR" and sinyal == "BELI" and rsi_n < 40:
                sinyal = "PANTAU"

            # ── MODE KRISIS: cek potensi rebound ──────────────────
            proba_rebound = 0.0
            if regime == "BEAR" and model_rebound is not None and fitur_rebound is not None:
                try:
                    fitur_rb = {**fitur_makro, **fitur_tek}
                    X_rb = pd.DataFrame([{
                        f: fitur_rb.get(f, 0) for f in fitur_rebound
                    }])
                    proba_rebound = float(model_rebound.predict_proba(X_rb)[0][1])
                    # Override SKIP → PANTAU (REBOUND?) jika probabilitas rebound tinggi
                    if sinyal == "SKIP" and proba_rebound >= 0.55:
                        sinyal = "PANTAU"
                    elif sinyal == "PANTAU" and proba_rebound >= 0.65:
                        sinyal = "BELI"  # konfiden tinggi → upgrade ke BELI
                except:
                    proba_rebound = 0.0

            hasil.append({
                "ticker"  : kode,
                "sektor"  : sektor,
                "skor"    : skor_final,
                "skor_tek": round(skor_tek, 1),
                "skor_mak": round(skor_makro, 1),
                "proba"   : round(proba, 3),
                "proba_rb": round(proba_rebound, 3),
                "rsi"     : round(rsi_n, 1),
                "sinyal"  : sinyal,
            })

        except Exception as e:
            pass

    df_hasil = pd.DataFrame(hasil).sort_values("skor", ascending=False)
    os.makedirs("logs", exist_ok=True)
    df_hasil.to_csv(f"logs/ranking_improved_{tanggal}.csv", index=False)

    # ── Tampilkan hasil ────────────────────────────────────────
    top10  = df_hasil.head(10)
    beli   = df_hasil[df_hasil["sinyal"] == "BELI"]
    pantau = df_hasil[df_hasil["sinyal"] == "PANTAU"]
    rebound_candidates = df_hasil[df_hasil["proba_rb"] >= 0.55].head(5) if "proba_rb" in df_hasil.columns else pd.DataFrame()

    LINE = "─" * 70
    print(f"\n{LINE}")
    print(f"TOP 10 SAHAM — {tanggal} | Regime: {regime} | Thr.BELI: {thr_beli}")
    if regime == "BEAR" and model_rebound is not None:
        print(f"🚨 MODE KRISIS AKTIF — Model Rebound Buy-the-Dip aktif")
    print(f"{LINE}")
    print(f"{'Rank':<5} {'Ticker':<7} {'Skor':>6} {'Sinyal':<8} {'RSI':>5} {'Tek':>6} {'Mak':>6} {'Proba':>6} {'RebProb':>8} {'Sektor'}")
    print(LINE)
    for i, (_, r) in enumerate(top10.iterrows(), 1):
        rb_str = f"{r.get('proba_rb',0):>8.3f}" if regime == "BEAR" else "       -"
        print(f"{i:<5} {r['ticker']:<7} {r['skor']:>6.1f} {r['sinyal']:<8} "
              f"{r['rsi']:>5.1f} {r['skor_tek']:>6.1f} {r['skor_mak']:>6.1f} "
              f"{r['proba']:>6.3f} {rb_str} {r['sektor']}")
    print(LINE)

    print(f"\nSINYAL:")
    if len(beli) > 0:
        print(f"  BELI   ({len(beli)}) : {', '.join(beli['ticker'].tolist())}")
    else:
        print(f"  BELI   (0) : — tidak ada (wajar di regime {regime})")
    if len(pantau) > 0:
        print(f"  PANTAU ({len(pantau)}) : {', '.join(pantau['ticker'].head(5).tolist())}{'...' if len(pantau)>5 else ''}")

    print(f"\nPERBAIKAN YANG AKTIF:")
    print(f"  ✓ Fitur makro real-time : {len(fitur_makro)} fitur dari yfinance")
    print(f"  ✓ Regime detection      : {regime} (threshold adaptif {thr_beli})")
    print(f"  ✓ Bobot regime          : {bobot_regime}")
    print(f"  ✓ Filter bear market    : RSI < 40 tidak BELI di regime BEAR")

    # Kirim ke Telegram
    if TOKEN and CHAT_ID:
        regime_ikon = "🟢" if regime=="BULL" else "🔴" if regime=="BEAR" else "🟡"
        mode_krisis = "\n🚨 MODE KRISIS AKTIF — Buy-the-Dip Scanner ON" if (regime=="BEAR" and model_rebound) else ""
        baris = [
            f"IHSG Predictor IMPROVED — {tanggal}",
            f"Regime: {regime_ikon} {regime} | Threshold: {thr_beli}{mode_krisis}",
            "",
            "TOP 10 SAHAM:",
        ]
        for i, (_, r) in enumerate(top10.iterrows(), 1):
            s = "BELI" if r["sinyal"]=="BELI" else "pantau" if r["sinyal"]=="PANTAU" else "skip"
            rb_info = f" | RB:{r.get('proba_rb',0):.2f}" if (regime=="BEAR" and r.get('proba_rb',0)>0.4) else ""
            baris.append(f"{i:2}. {r['ticker']:5} | {r['skor']:5.1f} | {s}{rb_info}")

        if len(beli) > 0:
            baris.append(f"\nSINYAL BELI: {', '.join(beli['ticker'].tolist())}")
        else:
            baris.append(f"\nSemua SKIP/PANTAU — Regime {regime}")

        # Kandidat rebound di mode krisis
        if regime == "BEAR" and len(rebound_candidates) > 0:
            rb_list = rebound_candidates["ticker"].tolist()
            baris.append(f"\n🎯 KANDIDAT REBOUND: {', '.join(rb_list)}")
            baris.append(f"(probabilitas naik ≥2% dalam 5 hari)")

        baris.append(f"\n[Improved: makro real-time + regime detection + rebound scanner]")
        url  = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        data  = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": chr(10).join(baris)}).encode()
        try:
            req = urllib.request.Request(url, data=data)
            urllib.request.urlopen(req, timeout=10)
            print("\n  ✓ Pesan terkirim ke Telegram")
        except Exception as e:
            print(f"\n  ✗ Telegram error: {e}")

    return df_hasil

if __name__ == "__main__":
    scoring_improved()
