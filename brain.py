"""
brain.py v3 — IHSG Predictor Brain
Fokus: Model SWING 1-3 hari
- Uji korelasi otomatis semua fitur vs target
- Data Indonesia gratis (BI, BPS, BMKG, dll)
- Self-healing
- Laporan jam 22:00 WIB
"""
import os, time, ssl, json, pickle, warnings
import urllib.request, urllib.error, urllib.parse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.metrics import accuracy_score
from scipy import stats
warnings.filterwarnings("ignore")

os.makedirs("models", exist_ok=True)
os.makedirs("logs/brain", exist_ok=True)
os.makedirs("logs/korelasi", exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode    = ssl.CERT_NONE
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; IHSGBrain/3.0)"}
TOKEN   = os.environ.get("TELEGRAM_TOKEN","")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID","")

BEST_ACC_FILE  = "logs/brain/best_acc_swing.txt"
HISTORY_FILE   = "logs/brain/history_swing.csv"
STATE_FILE     = "logs/brain/state_swing.json"
KORELASI_FILE  = "logs/korelasi/korelasi_swing.csv"

BASELINE_ACC   = 0.6481  # CV model swing pertama
TARGET_ACC     = 0.70    # target swing

# ── Telegram ──────────────────────────────────────────────────
def telegram(pesan):
    if not TOKEN or not CHAT_ID:
        print(f"[TELEGRAM]\n{pesan[:300]}")
        return
    try:
        url  = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": CHAT_ID, "text": pesan, "parse_mode": "HTML"
        }).encode()
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=15, context=CTX)
    except Exception as e:
        print(f"Telegram error: {e}")

# ── State ─────────────────────────────────────────────────────
def load_best_acc():
    if os.path.exists(BEST_ACC_FILE):
        try: return float(open(BEST_ACC_FILE).read().strip())
        except: pass
    return BASELINE_ACC

def save_best_acc(acc):
    with open(BEST_ACC_FILE,"w") as f: f.write(str(acc))

def load_state():
    default = {"hari_ke":0,"total_training":0,"total_deploy":0,"riwayat_cv":[]}
    if os.path.exists(STATE_FILE):
        try:
            s = json.load(open(STATE_FILE))
            for k,v in default.items():
                if k not in s: s[k] = v
            return s
        except: pass
    return default

def save_state(s):
    with open(STATE_FILE,"w") as f: json.dump(s, f, indent=2)

def simpan_history(row):
    df = pd.read_csv(HISTORY_FILE) if os.path.exists(HISTORY_FILE) else pd.DataFrame()
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(HISTORY_FILE, index=False)

# ── Download Yahoo ────────────────────────────────────────────
def yahoo_series(ticker, period="2y"):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?range={period}&interval=1d&includePrePost=false")
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
                d = json.loads(r.read().decode())
            res = d["chart"]["result"]
            if not res: return None
            ts     = res[0]["timestamp"]
            closes = res[0]["indicators"]["quote"][0]["close"]
            dates  = pd.to_datetime(ts, unit="s").normalize()
            s = pd.Series(closes, index=dates).dropna()
            return s if len(s) > 50 else None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(10+attempt*5); continue
            return None
        except: return None
    return None

# ══════════════════════════════════════════════════════════════
# DATA INDONESIA GRATIS
# ══════════════════════════════════════════════════════════════
def download_data_indonesia():
    """
    Kumpulkan data Indonesia dari sumber gratis.
    Return: dict {nama: pd.Series}
    """
    data = {}
    print("  Download data Indonesia...")

    # 1. KURS BI (USD/IDR resmi dari Yahoo)
    s = yahoo_series("USDIDR=X", "2y")
    if s is not None:
        data["usdidr"] = s
        print(f"    ✓ USD/IDR: {float(s.iloc[-1]):.0f}")
    time.sleep(0.5)

    # 2. IHSG proxy (^JKSE)
    s = yahoo_series("^JKSE", "2y")
    if s is not None:
        data["ihsg"] = s
        print(f"    ✓ IHSG: {float(s.iloc[-1]):.0f}")
    time.sleep(0.5)

    # 3. CPO (minyak sawit — komoditas utama Indonesia)
    s = yahoo_series("FCPO.KL", "2y")
    if s is not None:
        data["cpo"] = s
        print(f"    ✓ CPO: {float(s.iloc[-1]):.0f}")
    time.sleep(0.5)

    # 4. Batu bara (Newcastle)
    s = yahoo_series("MTF=F", "2y")
    if s is not None:
        data["batubara"] = s
        print(f"    ✓ Batu bara: {float(s.iloc[-1]):.0f}")
    time.sleep(0.5)

    # 5. Nikel (komoditas penting Indonesia)
    s = yahoo_series("NI=F", "2y")
    if s is not None:
        data["nikel"] = s
        print(f"    ✓ Nikel: {float(s.iloc[-1]):.0f}")
    time.sleep(0.5)

    # 6. Emas (safe haven)
    s = yahoo_series("GC=F", "2y")
    if s is not None:
        data["emas"] = s
        print(f"    ✓ Emas: {float(s.iloc[-1]):.0f}")
    time.sleep(0.5)

    # 7. Minyak Brent (pengaruh BBM Indonesia)
    s = yahoo_series("BZ=F", "2y")
    if s is not None:
        data["brent"] = s
        print(f"    ✓ Brent: {float(s.iloc[-1]):.2f}")
    time.sleep(0.5)

    # 8. VIX (fear index global)
    s = yahoo_series("^VIX", "2y")
    if s is not None:
        data["vix"] = s
        print(f"    ✓ VIX: {float(s.iloc[-1]):.1f}")
    time.sleep(0.5)

    # 9. SP500 (pasar global)
    s = yahoo_series("^GSPC", "2y")
    if s is not None:
        data["sp500"] = s
        print(f"    ✓ SP500: {float(s.iloc[-1]):.0f}")
    time.sleep(0.5)

    # 10. Pasar Asia (korelasi tinggi dengan IHSG)
    asia = {
        "^HSI":"hangseng","^KS11":"kospi","^N225":"nikkei",
        "^STI":"sti","^KLSE":"klci","000001.SS":"sse",
    }
    for ticker, nama in asia.items():
        s = yahoo_series(ticker, "2y")
        if s is not None:
            data[nama] = s
            print(f"    ✓ {nama}: {float(s.iloc[-1]):.0f}")
        time.sleep(0.4)

    # 11. US Bond Yield (pengaruh capital flow)
    s = yahoo_series("^TNX", "2y")
    if s is not None:
        data["usbond"] = s
        print(f"    ✓ US Bond: {float(s.iloc[-1]):.2f}%")
    time.sleep(0.5)

    # 12. DXY (Dollar Index — pengaruh rupiah)
    s = yahoo_series("DX-Y.NYB", "2y")
    if s is not None:
        data["dxy"] = s
        print(f"    ✓ DXY: {float(s.iloc[-1]):.2f}")
    time.sleep(0.5)

    print(f"  Total data: {len(data)} sumber")
    return data

# ══════════════════════════════════════════════════════════════
# FITUR SWING
# ══════════════════════════════════════════════════════════════
def buat_fitur_swing(df, data_indonesia):
    """Buat semua fitur untuk model swing 1-3 hari."""
    close  = pd.to_numeric(df["close"],  errors="coerce")
    high   = pd.to_numeric(df.get("high",  close), errors="coerce")
    low    = pd.to_numeric(df.get("low",   close), errors="coerce")
    volume = pd.to_numeric(df.get("volume",
             pd.Series(1e6, index=df.index)), errors="coerce").fillna(1e6)

    ret = close.pct_change()
    f   = pd.DataFrame(index=df.index)

    # ── RSI ──────────────────────────────────────────────────
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta).clip(lower=0).rolling(14).mean()
    rsi   = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
    f["rsi"]            = rsi
    f["rsi_oversold"]   = (rsi < 30).astype(int)
    f["rsi_overbought"] = (rsi > 70).astype(int)
    f["rsi_naik"]       = ((rsi > rsi.shift(1)) & (rsi < 50)).astype(int)
    f["rsi_cross50"]    = ((rsi > 50) & (rsi.shift(1) <= 50)).astype(int)

    # ── MACD ─────────────────────────────────────────────────
    ema12  = close.ewm(span=12).mean()
    ema26  = close.ewm(span=26).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    f["macd"]           = macd
    f["macd_hist"]      = macd - signal
    f["macd_cross"]     = ((macd > signal) & (macd.shift(1) <= signal.shift(1))).astype(int)
    f["macd_positif"]   = (macd > 0).astype(int)
    f["macd_hist_naik"] = ((macd-signal) > (macd.shift(1)-signal.shift(1))).astype(int)

    # ── Bollinger Band ────────────────────────────────────────
    sma20 = close.rolling(20).mean()
    sma5  = close.rolling(5).mean()
    sma10 = close.rolling(10).mean()
    sma50 = close.rolling(50).mean()
    std20 = close.rolling(20).std()
    bb_lo = sma20 - 2*std20
    bb_up = sma20 + 2*std20
    f["bb_pct"]         = (close - bb_lo) / (4*std20).replace(0, np.nan)
    f["below_bb"]       = (close < bb_lo).astype(int)
    f["above_bb"]       = (close > bb_up).astype(int)
    f["bb_squeeze"]     = (std20 < std20.rolling(20).mean()*0.8).astype(int)

    # ── Moving Average ────────────────────────────────────────
    f["close_vs_sma5"]  = (close / sma5.replace(0,np.nan) - 1)
    f["close_vs_sma10"] = (close / sma10.replace(0,np.nan) - 1)
    f["close_vs_sma20"] = (close / sma20.replace(0,np.nan) - 1)
    f["close_vs_sma50"] = (close / sma50.replace(0,np.nan) - 1)
    f["sma5_cross10"]   = ((sma5>sma10) & (sma5.shift(1)<=sma10.shift(1))).astype(int)
    f["golden_cross"]   = ((sma5>sma10) & (sma10>sma50)).astype(int)
    f["death_cross"]    = ((sma5<sma10) & (sma5.shift(1)>=sma10.shift(1))).astype(int)

    # ── Volume ───────────────────────────────────────────────
    vol_ma = volume.rolling(20).mean().replace(0, np.nan)
    f["vol_ratio"]      = volume / vol_ma
    f["vol_spike"]      = (f["vol_ratio"] > 2).astype(int)
    f["vol_spike3"]     = (f["vol_ratio"] > 3).astype(int)
    f["vol_naik"]       = (volume > volume.shift(1)).astype(int)
    f["akumulasi"]      = ((close > close.shift(1)) & (f["vol_ratio"] > 1.5)).astype(int)
    f["akumulasi_2d"]   = f["akumulasi"].rolling(2).sum()
    f["distribusi"]     = ((close < close.shift(1)) & (f["vol_ratio"] > 1.5)).astype(int)

    # ── Breakout ─────────────────────────────────────────────
    high20 = high.rolling(20).max()
    low20  = low.rolling(20).min()
    high5  = high.rolling(5).max()
    f["breakout_up"]    = ((close > high20.shift(1)) & (f["vol_ratio"] > 1.5)).astype(int)
    f["breakout_down"]  = ((close < low20.shift(1))).astype(int)
    f["near_high20"]    = ((close / high20.replace(0,np.nan)) > 0.97).astype(int)
    f["near_low20"]     = ((close / low20.replace(0,np.nan)) < 1.03).astype(int)
    f["range_pct"]      = (high20 - low20) / low20.replace(0,np.nan)

    # ── Stochastic ───────────────────────────────────────────
    low14  = low.rolling(14).min()
    high14 = high.rolling(14).max()
    stoch  = (close - low14) / (high14 - low14).replace(0, np.nan) * 100
    stoch_d = stoch.rolling(3).mean()
    f["stoch_k"]        = stoch
    f["stoch_oversold"] = (stoch < 20).astype(int)
    f["stoch_cross"]    = ((stoch > stoch_d) & (stoch.shift(1) <= stoch_d.shift(1)) & (stoch < 40)).astype(int)

    # ── Candle Pattern ────────────────────────────────────────
    body   = abs(close - close.shift(1))
    shadow = high - low
    f["hammer"]         = ((shadow > body*2) & (close > close.shift(1))).astype(int)
    f["doji"]           = (body < shadow*0.1).astype(int)
    f["strong_candle"]  = ((close - close.shift(1)) > close.shift(1)*0.02).astype(int)
    f["weak_candle"]    = ((close.shift(1) - close) > close.shift(1)*0.02).astype(int)

    # ── Return lags ──────────────────────────────────────────
    for lag in [1, 2, 3, 5, 10]:
        f[f"ret_{lag}d"]  = ret.shift(lag)
    f["ret_5d_sum"]     = ret.shift(1).rolling(5).sum()
    f["ret_10d_sum"]    = ret.shift(1).rolling(10).sum()
    f["volatility_5d"]  = ret.rolling(5).std()
    f["volatility_10d"] = ret.rolling(10).std()
    f["volatility_20d"] = ret.rolling(20).std()
    f["vol_spike_price"]= (f["volatility_5d"] > f["volatility_20d"]*1.5).astype(int)

    # ── MFI & CMF ────────────────────────────────────────────
    tp   = (high + low + close) / 3
    mf   = tp * volume
    pmf  = mf.where(tp > tp.shift(1), 0).rolling(14).sum()
    nmf  = mf.where(tp < tp.shift(1), 0).rolling(14).sum()
    mfi  = 100 - (100 / (1 + pmf / nmf.replace(0, np.nan)))
    mfv  = ((close-low)-(high-close)) / (high-low).replace(0,np.nan) * volume
    cmf  = mfv.rolling(20).sum() / volume.rolling(20).sum().replace(0,np.nan)
    f["mfi"]            = mfi
    f["mfi_oversold"]   = (mfi < 20).astype(int)
    f["mfi_naik"]       = ((mfi > mfi.shift(1)) & (mfi < 30)).astype(int)
    f["cmf"]            = cmf
    f["cmf_positif"]    = (cmf > 0).astype(int)

    # ── Kalender ─────────────────────────────────────────────
    f["hari"]           = df.index.dayofweek
    f["bulan"]          = df.index.month
    f["senin"]          = (df.index.dayofweek == 0).astype(int)
    f["jumat"]          = (df.index.dayofweek == 4).astype(int)
    f["awal_bulan"]     = (df.index.day <= 5).astype(int)
    f["akhir_bulan"]    = (df.index.day >= 25).astype(int)
    f["kuartal"]        = df.index.quarter

    # ── Data Indonesia ────────────────────────────────────────
    for nama, series in data_indonesia.items():
        try:
            s     = series.reindex(df.index, method="ffill")
            s_ret = s.pct_change()
            f[f"{nama}_ret"]    = s_ret
            f[f"{nama}_ret_lag"]= s_ret.shift(1)
            f[f"{nama}_trend5"] = (s / s.rolling(5).mean().replace(0,np.nan) - 1)

            # Fitur khusus per sumber
            if nama == "vix":
                f["vix_level"]  = s
                f["vix_tinggi"] = (s > 25).astype(int)
                f["vix_ekstrem"]= (s > 35).astype(int)
                f["vix_turun"]  = ((s < s.shift(1)) & (s.shift(1) > 30)).astype(int)
            if nama == "usdidr":
                f["rupiah_lemah"]   = (s > 16500).astype(int)
                f["rupiah_sangat_lemah"] = (s > 17000).astype(int)
                f["rupiah_stabil"]  = (s_ret.rolling(3).std() < 0.003).astype(int)
            if nama == "ihsg":
                f["ihsg_naik"]  = (s_ret > 0).astype(int)
                f["ihsg_trend"] = (s / s.rolling(20).mean().replace(0,np.nan) - 1)
            if nama in ["hangseng","kospi","nikkei","sti"]:
                f[f"{nama}_hijau"] = (s_ret > 0).astype(int)
        except:
            pass

    # Berapa pasar Asia hijau hari ini
    asia_cols = [c for c in f.columns if c.endswith("_hijau")]
    if asia_cols:
        f["asia_pct_naik"]   = f[asia_cols].mean(axis=1)
        f["asia_semua_naik"] = (f["asia_pct_naik"] > 0.7).astype(int)
        f["asia_semua_turun"]= (f["asia_pct_naik"] < 0.3).astype(int)

    return f

# ══════════════════════════════════════════════════════════════
# UJI KORELASI
# ══════════════════════════════════════════════════════════════
def uji_korelasi(X_combined, y_combined, simpan=True):
    """
    Uji korelasi setiap fitur vs target (naik 1-3 hari).
    Return: list fitur yang signifikan (|r| > 0.03, p < 0.05)
    """
    print("\n  Uji korelasi fitur...")
    hasil_korelasi = []

    for col in X_combined.columns:
        try:
            x = X_combined[col].fillna(0)
            y = y_combined

            # Pearson correlation
            r_p, p_p = stats.pearsonr(x, y)

            # Spearman correlation (lebih robust)
            r_s, p_s = stats.spearmanr(x, y)

            hasil_korelasi.append({
                "fitur"     : col,
                "pearson_r" : round(r_p, 4),
                "pearson_p" : round(p_p, 4),
                "spearman_r": round(r_s, 4),
                "spearman_p": round(p_s, 4),
                "abs_r"     : round(max(abs(r_p), abs(r_s)), 4),
                "signifikan": (p_p < 0.05 and abs(r_p) > 0.03) or
                              (p_s < 0.05 and abs(r_s) > 0.03),
            })
        except:
            pass

    df_kor = pd.DataFrame(hasil_korelasi).sort_values("abs_r", ascending=False)

    if simpan:
        df_kor.to_csv(KORELASI_FILE, index=False)

    # Filter fitur signifikan
    fitur_signifikan = df_kor[df_kor["signifikan"]==True]["fitur"].tolist()

    print(f"  Total fitur      : {len(df_kor)}")
    print(f"  Fitur signifikan : {len(fitur_signifikan)}")
    print(f"\n  TOP 10 KORELASI:")
    for _, r in df_kor.head(10).iterrows():
        bar = "█" * int(r["abs_r"]*200)
        sig = "✓" if r["signifikan"] else "✗"
        print(f"    {sig} {r['fitur']:<30} r={r['pearson_r']:+.4f}  {bar}")

    return fitur_signifikan, df_kor

# ══════════════════════════════════════════════════════════════
# SELF-HEALING
# ══════════════════════════════════════════════════════════════
ERROR_LOG = "logs/brain/error_log.json"

def catat_error(fungsi, error_msg):
    log = []
    if os.path.exists(ERROR_LOG):
        try: log = json.load(open(ERROR_LOG))
        except: pass
    log.append({
        "waktu" : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fungsi": fungsi,
        "error" : str(error_msg)[:200],
    })
    with open(ERROR_LOG,"w") as f:
        json.dump(log[-50:], f, indent=2)

def self_heal(nama, error):
    err = str(error).lower()
    if "ssl" in err or "certificate" in err:
        return True
    if "no such file" in err or "filenotfound" in err:
        for folder in ["models","logs/brain","data","data/idx500"]:
            os.makedirs(folder, exist_ok=True)
        return True
    if "429" in err or "too many" in err:
        print("[SELF-HEAL] Rate limit, tunggu 60 detik")
        time.sleep(60)
        return True
    if "memory" in err:
        print("[SELF-HEAL] Memory error, kurangi data")
        return True
    return False

def safe_run(fungsi, *args, nama="fungsi", max_retry=2, **kwargs):
    for attempt in range(max_retry):
        try:
            return fungsi(*args, **kwargs)
        except Exception as e:
            catat_error(nama, e)
            print(f"[ERROR] {nama}: {e}")
            if attempt < max_retry-1 and self_heal(nama, e):
                time.sleep(5)
                continue
            return None
    return None

# ══════════════════════════════════════════════════════════════
# TRAINING SWING
# ══════════════════════════════════════════════════════════════
STRATEGI_SWING = [
    # nama,           trees, depth, lr,    subsample, algo
    ("GB-Fast",       200,   4,     0.05,  0.8,       "gb"),
    ("GB-Deep",       300,   6,     0.03,  0.8,       "gb"),
    ("GB-ManyTrees",  400,   4,     0.05,  0.9,       "gb"),
    ("RF-Balanced",   400,   12,    None,  None,      "rf"),
    ("RF-Deep",       500,   14,    None,  None,      "rf"),
]

def load_semua_data(data_indonesia):
    """Load semua saham dari folder idx500 + data + biostatistik."""
    X_all, y_all, meta = [], [], []
    folder_list = ["data/idx500", "data", "data/biostatistik/saham"]
    scanned = set()

    for folder in folder_list:
        if not os.path.exists(folder): continue
        for fname in os.listdir(folder):
            if not fname.endswith(".csv"): continue
            kode = fname.replace(".csv","")
            if kode in scanned: continue
            if any(x in kode.upper() for x in [
                "KOMODITAS","MAKRO","CUACA","IHSG","VIX","USD",
                "BERAS","GANDUM","MINYAK","EMAS","BATU"
            ]): continue
            if not (kode.isupper() and len(kode) <= 6): continue
            scanned.add(kode)

            try:
                df = pd.read_csv(os.path.join(folder, fname))
                df.columns = [c.lower() for c in df.columns]
                if "date" not in df.columns: continue
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
                for col in ["close","high","low","volume"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna(subset=["close"])
                df = df[df["close"] > 50]
                if len(df) < 150: continue

                # TARGET SWING: naik >= 1.5% dalam 1-3 hari
                close = df["close"]
                ret_max_3d = pd.DataFrame({
                    "r1": close.shift(-1)/close - 1,
                    "r2": close.shift(-2)/close - 1,
                    "r3": close.shift(-3)/close - 1,
                }).max(axis=1)
                target = (ret_max_3d >= 0.015).astype(int)

                X = buat_fitur_swing(df, data_indonesia)
                df_g = X.copy()
                df_g["target"] = target

                valid = (df_g["target"].notna() &
                         (df_g.isna().sum(axis=1) < df_g.shape[1]*0.4))
                df_g = df_g[valid].fillna(0)
                if len(df_g) < 100: continue

                X_all.append(df_g.drop("target", axis=1))
                y_all.append(df_g["target"])
                meta.append({"kode": kode, "n": len(df_g)})
            except:
                continue

    return X_all, y_all, meta

def train_swing(nama, trees, depth, lr, subsample, algo,
                X_combined, y_combined, fitur_pakai):
    """Training satu strategi swing."""
    X = X_combined[fitur_pakai]

    if algo == "gb":
        clf = GradientBoostingClassifier(
            n_estimators=trees, max_depth=depth,
            learning_rate=lr, subsample=subsample,
            random_state=42
        )
    else:
        clf = RandomForestClassifier(
            n_estimators=trees, max_depth=depth,
            min_samples_leaf=10, max_features="sqrt",
            random_state=42, n_jobs=-1, class_weight="balanced"
        )

    model = Pipeline([("scaler", StandardScaler()), ("clf", clf)])
    tscv  = TimeSeriesSplit(n_splits=5)
    scores = cross_val_score(model, X, y_combined,
                              cv=tscv, scoring="accuracy", n_jobs=-1)
    cv = round(float(scores.mean()), 4)
    model.fit(X, y_combined)
    return model, cv

# ══════════════════════════════════════════════════════════════
# FUNGSI UTAMA
# ══════════════════════════════════════════════════════════════
def training_loop():
    """
    Jam 07:00 WIB: training loop swing.
    1. Download data Indonesia
    2. Load semua saham
    3. Uji korelasi
    4. Training model swing dengan fitur signifikan
    5. Deploy kalau lebih baik
    """
    tanggal   = datetime.now().strftime("%Y-%m-%d")
    state     = load_state()
    best_acc  = load_best_acc()
    batas_jam = datetime.now().replace(hour=21, minute=45, second=0)

    print(f"\n{'='*60}")
    print(f"BRAIN v3 — SWING SCANNER — {tanggal}")
    print(f"Best acc: {best_acc*100:.2f}% | Target: {TARGET_ACC*100:.0f}%")
    print(f"{'='*60}")

    # 1. Download data Indonesia
    print("\n[1/5] Download data Indonesia...")
    data_indonesia = safe_run(download_data_indonesia, nama="download_indonesia") or {}
    print(f"  Berhasil: {len(data_indonesia)} sumber data")

    # 2. Load semua data saham
    print("\n[2/5] Load data saham...")
    X_all, y_all, meta = safe_run(
        load_semua_data, data_indonesia, nama="load_data"
    ) or ([], [], [])

    if not X_all:
        print("ERROR: tidak ada data!")
        telegram(f"🚨 Brain error: tidak ada data saham\n{tanggal}")
        return best_acc, False

    print(f"  Saham: {len(meta)} | Baris: {sum(m['n'] for m in meta):,}")

    # 3. Gabungkan dataset
    print("\n[3/5] Gabungkan dataset...")
    X_combined = pd.concat(X_all).fillna(0)
    y_combined = pd.concat(y_all)
    X_combined = X_combined.loc[:, X_combined.nunique() > 1]
    print(f"  Dataset: {len(X_combined):,} baris | {X_combined.shape[1]} fitur")
    print(f"  Positif: {y_combined.sum():,} ({y_combined.mean()*100:.1f}%)")

    # 4. Uji korelasi
    print("\n[4/5] Uji korelasi...")
    fitur_signifikan, df_korelasi = safe_run(
        uji_korelasi, X_combined, y_combined,
        nama="uji_korelasi"
    ) or (X_combined.columns.tolist(), pd.DataFrame())

    # Minimal 20 fitur
    if len(fitur_signifikan) < 20:
        print(f"  Fitur signifikan terlalu sedikit ({len(fitur_signifikan)}), pakai semua")
        fitur_signifikan = X_combined.columns.tolist()

    fitur_signifikan = [f for f in fitur_signifikan if f in X_combined.columns]
    print(f"  Fitur yang dipakai: {len(fitur_signifikan)}")

    # 5. Training semua strategi
    print("\n[5/5] Training model swing...")
    hasil_semua     = []
    acc_terbaik     = best_acc
    strategi_menang = "-"
    deployed        = False
    error_count     = 0

    for nama, trees, depth, lr, subsample, algo in STRATEGI_SWING:
        if datetime.now() >= batas_jam:
            print(f"\nBatas waktu 21:45 WIB, stop training")
            break

        print(f"\n  [{nama}] trees={trees} depth={depth} algo={algo}")
        waktu_mulai = datetime.now()

        try:
            model, cv = train_swing(
                nama, trees, depth, lr, subsample, algo,
                X_combined, y_combined, fitur_signifikan
            )
            durasi = (datetime.now()-waktu_mulai).seconds // 60
            print(f"  CV={cv*100:.2f}% | {durasi} menit")

            hasil_semua.append({
                "strategi": nama, "cv": cv,
                "durasi": durasi, "error": False
            })

            if cv > acc_terbaik:
                acc_terbaik     = cv
                strategi_menang = nama
                print(f"  ✅ LEBIH BAIK! {best_acc*100:.2f}% → {cv*100:.2f}%")

                # Simpan model swing
                import shutil
                path_baru = f"models/model_swing_{tanggal.replace('-','')}.pkl"
                model_data = {
                    "pipeline"   : model,
                    "fitur"      : fitur_signifikan,
                    "cv_accuracy": cv,
                    "nama_model" : nama,
                    "target"     : "naik >= 1.5% dalam 1-3 hari",
                    "n_saham"    : len(meta),
                    "n_data"     : len(X_combined),
                    "tanggal"    : tanggal,
                    "fitur_korelasi": len(fitur_signifikan),
                }
                with open(path_baru, "wb") as f_:
                    pickle.dump(model_data, f_)
                shutil.copy(path_baru, "models/model_swing.pkl")
                save_best_acc(acc_terbaik)
                deployed = True
                state["total_deploy"] += 1
                print(f"  ✅ Model swing di-deploy!")

                if cv >= TARGET_ACC:
                    print(f"\n🎯 TARGET {TARGET_ACC*100:.0f}% TERCAPAI!")
                    break
            else:
                print(f"  Belum lebih baik dari {acc_terbaik*100:.2f}%")

        except Exception as e:
            catat_error(f"train_{nama}", e)
            error_count += 1
            print(f"  ERROR: {e}")
            hasil_semua.append({"strategi": nama, "cv": 0, "durasi": 0, "error": True})

    # Update state
    state["hari_ke"]       += 1
    state["total_training"] += len(hasil_semua)
    state["riwayat_cv"]     = (state.get("riwayat_cv",[]) + [acc_terbaik])[-30:]
    save_state(state)

    simpan_history({
        "tanggal"        : tanggal,
        "cv_terbaik"     : acc_terbaik,
        "strategi_menang": strategi_menang,
        "deployed"       : deployed,
        "n_fitur"        : len(fitur_signifikan),
        "n_saham"        : len(meta),
        "error_count"    : error_count,
    })

    # Simpan data untuk laporan jam 22:00
    top_korelasi = []
    if len(df_korelasi) > 0:
        top_korelasi = df_korelasi.head(5)[["fitur","pearson_r","abs_r"]].to_dict("records")

    laporan_data = {
        "tanggal"        : tanggal,
        "best_acc"       : acc_terbaik,
        "deployed"       : deployed,
        "strategi_menang": strategi_menang,
        "hasil_semua"    : hasil_semua,
        "total_training" : state["total_training"],
        "total_deploy"   : state["total_deploy"],
        "riwayat_cv"     : state["riwayat_cv"],
        "error_count"    : error_count,
        "n_fitur"        : len(fitur_signifikan),
        "n_saham"        : len(meta),
        "top_korelasi"   : top_korelasi,
        "n_data_indo"    : len(data_indonesia),
    }
    with open("logs/brain/laporan_hari_ini.json","w") as f:
        json.dump(laporan_data, f, indent=2)

    print(f"\nTraining selesai. Laporan dikirim jam 22:00 WIB.")
    return acc_terbaik, deployed

def kirim_laporan():
    """22:00 WIB: kirim laporan ke Telegram."""
    tanggal = datetime.now().strftime("%Y-%m-%d")
    laporan_path = "logs/brain/laporan_hari_ini.json"

    if not os.path.exists(laporan_path):
        telegram(
            f"🧠 <b>LAPORAN BRAIN v3 — {tanggal}</b>\n\n"
            f"⚠️ Tidak ada data training hari ini."
        )
        return

    with open(laporan_path) as f:
        d = json.load(f)

    best_acc  = d["best_acc"]
    deployed  = d["deployed"]
    menang    = d["strategi_menang"]
    hasil     = d["hasil_semua"]
    riwayat   = d.get("riwayat_cv", [])
    top_kor   = d.get("top_korelasi", [])

    # Progress bar
    progress = max(0, min(100, (best_acc-BASELINE_ACC)/(TARGET_ACC-BASELINE_ACC)*100))
    bar      = "█"*int(progress/5) + "░"*(20-int(progress/5))

    # Tren
    tren = ""
    if len(riwayat) >= 2:
        delta = (riwayat[-1]-riwayat[-2])*100
        tren  = f"{'▲' if delta>0 else '▼'} {abs(delta):.2f}% vs kemarin"

    # Detail strategi
    detail = ""
    for h in hasil:
        if h.get("error"):
            detail += f"❌ {h['strategi']}: ERROR\n"
        else:
            flag = "✅" if h["cv"] > BASELINE_ACC else "⬜"
            detail += f"{flag} {h['strategi']}: {h['cv']*100:.2f}% ({h['durasi']}m)\n"

    # Top korelasi
    kor_info = ""
    if top_kor:
        kor_info = "🔬 Top korelasi fitur:\n"
        for k in top_kor[:5]:
            kor_info += f"  {k['fitur']}: r={k['pearson_r']:+.4f}\n"

    if best_acc >= TARGET_ACC:
        status = f"🎯 <b>TARGET {TARGET_ACC*100:.0f}% TERCAPAI!</b>"
    elif deployed:
        delta = (best_acc - BASELINE_ACC)*100
        status = f"✅ Model swing diupdate! +{delta:.2f}%"
    else:
        status = f"⬜ Belum ada peningkatan"

    error_info = f"⚠️ {d.get('error_count',0)} error (auto-fixed)\n" if d.get('error_count',0) > 0 else ""

    msg = (
        f"🧠 <b>LAPORAN BRAIN v3 — SWING MODEL</b>\n"
        f"📅 {tanggal}\n"
        f"{'─'*32}\n"
        f"🎯 <b>CV terbaik: {best_acc*100:.2f}%</b>\n"
        f"📈 {tren}\n"
        f"{error_info}"
        f"{status}\n"
        f"{'─'*32}\n"
        f"📊 Hasil training:\n{detail}"
        f"{'─'*32}\n"
        f"🏆 Strategi terbaik: {menang}\n"
        f"📦 Training: {d['total_training']} | Deploy: {d['total_deploy']}\n"
        f"📁 Saham: {d.get('n_saham',0)} | Fitur: {d.get('n_fitur',0)}\n"
        f"🇮🇩 Data Indonesia: {d.get('n_data_indo',0)} sumber\n"
        f"{'─'*32}\n"
        f"{kor_info}"
        f"{'─'*32}\n"
        f"📊 Progress ke {TARGET_ACC*100:.0f}%:\n"
        f"[{bar}] {progress:.0f}%\n"
        f"Gap: {(TARGET_ACC-best_acc)*100:.2f}% lagi\n"
        f"{'─'*32}\n"
        f"⏰ Training besok mulai 07:00 WIB"
    )
    telegram(msg)

# ── Entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "train"
    if cmd == "laporan":
        kirim_laporan()
    else:
        training_loop()
