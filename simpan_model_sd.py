"""
simpan_model_sd.py
Training dengan fitur Supply/Demand proxy lengkap
Target: akurasi naik ke 62-65%
"""
import pandas as pd, numpy as np, os, pickle
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score

os.makedirs("models", exist_ok=True)

# ── Muat komoditas ────────────────────────────────────────────
df_kom = pd.read_csv("data/komoditas/KOMODITAS_GABUNGAN.csv", index_col=0)
df_kom.index = pd.to_datetime(df_kom.index)
print(f"Komoditas: {len(df_kom.columns)} fitur")

SECTORS = {
    "tambang"      : ["ADRO","PTBA","ITMG","INCO","ANTM","TINS","MEDC","HRUM","MDKA"],
    "perbankan"    : ["BBRI","BMRI","BBCA","BBNI","BRIS","BNGA","BBTN","PNBN","BJBR","BJTM","BMAS","AGRO"],
    "konsumer"     : ["UNVR","ICBP","MYOR","KLBF","KAEF","CPIN","SIDO","GGRM","HMSP","WIIM","JPFA","MAIN","SIPD"],
    "agribisnis"   : ["AALI","SIMP","LSIP"],
    "energi"       : ["PGAS","AKRA","ESSA","ELSA","RUIS"],
    "properti"     : ["SMRA","BSDE","CTRA","PWON","LPKR"],
    "ritel"        : ["ACES","MAPI","LPPF","RALS"],
    "kesehatan"    : ["MIKA","SILO","HEAL"],
    "media"        : ["SCMA","MNCN","EMTK"],
    "telekomunikasi": ["TLKM","EXCL","ISAT","TOWR","MTEL","TBIG","LINK"],
}

def get_sektor(kode):
    for s, emiten in SECTORS.items():
        if kode in emiten:
            return s
    return "lainnya"

def hitung_semua_fitur(df):
    """Hitung fitur teknikal + supply/demand proxy."""
    close  = df["close"]
    high   = df["high"]
    low    = df["low"]
    volume = df["volume"]

    # ── Teknikal dasar ────────────────────────────────────
    df["ma5"]   = close.rolling(5).mean()
    df["ma20"]  = close.rolling(20).mean()
    df["ma50"]  = close.rolling(50).mean()

    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta).clip(lower=0).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    df["rsi"]       = 100 - (100 / (1 + rs))

    ema12           = close.ewm(span=12, adjust=False).mean()
    ema26           = close.ewm(span=26, adjust=False).mean()
    df["macd"]      = ema12 - ema26
    df["macd_hist"] = df["macd"] - df["macd"].ewm(span=9, adjust=False).mean()

    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    df["bb_pct"]    = (close - (sma20 - 2*std20)) / (4*std20).replace(0, np.nan)

    df["vol_ratio"] = volume / volume.rolling(20).mean().replace(0, np.nan)

    for lag in [1, 3, 5]:
        df[f"return_lag{lag}"] = close.pct_change(lag)

    df["volatility_5d"]  = close.pct_change().rolling(5).std()
    df["volatility_20d"] = close.pct_change().rolling(20).std()
    df["above_ma20"]     = (close > df["ma20"]).astype(int)
    df["above_ma50"]     = (close > df["ma50"]).astype(int)

    # ── Supply/Demand Proxy (6 fitur baru) ───────────────

    # 1. Volume Spike — volume hari ini vs rata-rata 30 hari
    vol_ma30        = volume.rolling(30).mean()
    df["vol_spike"] = (volume / vol_ma30.replace(0, np.nan)).fillna(1.0)
    df["vol_spike_biner"] = (df["vol_spike"] > 2.0).astype(int)

    # 2. Akumulasi vs Distribusi
    df["akumulasi"]  = ((close > close.shift(1)) & (volume > volume.shift(1))).astype(int)
    df["distribusi"] = ((close < close.shift(1)) & (volume > volume.shift(1))).astype(int)

    # 3. On-Balance Volume (OBV) — proxy aliran uang
    obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
    df["obv_pct"]   = obv.pct_change(5)   # perubahan OBV 5 hari

    # 4. Money Flow Index (MFI) — RSI berbasis volume
    typical_price  = (high + low + close) / 3
    money_flow     = typical_price * volume
    pos_flow       = money_flow.where(typical_price > typical_price.shift(1), 0)
    neg_flow       = money_flow.where(typical_price < typical_price.shift(1), 0)
    pos_mf_sum     = pos_flow.rolling(14).sum()
    neg_mf_sum     = neg_flow.rolling(14).sum()
    mfi_ratio      = pos_mf_sum / neg_mf_sum.replace(0, np.nan)
    df["mfi"]      = 100 - (100 / (1 + mfi_ratio))

    # 5. Chaikin Money Flow (CMF) — tekanan beli vs jual
    mfv  = ((close - low) - (high - close)) / (high - low).replace(0, np.nan) * volume
    df["cmf"] = mfv.rolling(20).sum() / volume.rolling(20).sum().replace(0, np.nan)

    # 6. Price-Volume Trend (PVT)
    pvt  = ((close.diff() / close.shift(1)) * volume).fillna(0).cumsum()
    df["pvt_pct"] = pvt.pct_change(5)

    # 7. Breakout — harga tembus high 20 hari
    df["is_breakout"] = (close > high.rolling(20).max().shift(1)).astype(int)

    # 8. Momentum harga
    df["momentum_5d"]  = close.pct_change(5)
    df["momentum_20d"] = close.pct_change(20)

    # Label: naik besok?
    df["label"] = (close.pct_change().shift(-1) > 0).astype(int)

    return df

# ── Kumpulkan semua data ──────────────────────────────────────
print("Muat data saham...")
semua = []
for f in os.listdir("data"):
    if not f.endswith(".csv") or f.startswith("KOMODITAS"):
        continue
    kode = f.replace(".csv", "")
    try:
        df = pd.read_csv(f"data/{f}")
        df.columns = [c.lower() for c in df.columns]
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()

        # Filter saham layak
        if len(df) < 100:
            continue
        if df["close"].iloc[-1] < 100:
            continue
        if df["close"].iloc[-1] * df["volume"].iloc[-1] < 500_000_000:
            continue
        # Pastikan ada high/low
        if "high" not in df.columns or "low" not in df.columns:
            continue

        df = hitung_semua_fitur(df)
        df["ticker"] = kode
        df["sektor"] = get_sektor(kode)
        df = df.join(df_kom, how="left").ffill()
        df = df.dropna(subset=["label", "rsi", "macd", "mfi", "cmf"])
        semua.append(df)
    except Exception as e:
        pass

df_all = pd.concat(semua).replace([np.inf, -np.inf], np.nan).dropna()
print(f"Dataset: {len(df_all):,} baris | {df_all['ticker'].nunique()} saham")

# ── Daftar semua fitur ────────────────────────────────────────
EXCLUDE = ["label","ticker","sektor","open","high","low","close","volume",
           "ma5","ma20","ma50"]
FITUR   = [c for c in df_all.columns if c not in EXCLUDE]

# Fitur supply/demand baru
SD_FITUR = ["vol_spike","vol_spike_biner","akumulasi","distribusi",
            "obv_pct","mfi","cmf","pvt_pct","is_breakout",
            "momentum_5d","momentum_20d"]

print(f"\nTotal fitur: {len(FITUR)}")
print(f"  Teknikal  : {len([f for f in FITUR if f not in SD_FITUR and not f.startswith(('coal','oil','gold','cpo'))])}")
print(f"  S/D proxy : {len([f for f in FITUR if f in SD_FITUR])}")
print(f"  Komoditas : {len([f for f in FITUR if f.startswith(('coal','oil','gold','cpo'))])}")

# ── Training per sektor ───────────────────────────────────────
models = {}
print("\nTraining RandomForest per sektor...")
total_acc = []

for sektor in sorted(df_all["sektor"].unique()):
    df_s = df_all[df_all["sektor"] == sektor]
    if len(df_s) < 100:
        continue

    fitur_ada = [f for f in FITUR if f in df_s.columns]
    X = df_s[fitur_ada].values
    y = df_s["label"].values

    split    = int(len(X) * 0.8)
    X_tr, X_te = X[:split], X[split:]
    y_tr, y_te = y[:split], y[split:]

    model = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", RandomForestClassifier(
            n_estimators=300,
            max_depth=6,
            min_samples_leaf=20,
            max_features="sqrt",
            random_state=42,
            n_jobs=-1,
        ))
    ])
    model.fit(X_tr, y_tr)

    acc_tr = accuracy_score(y_tr, model.predict(X_tr))
    acc_te = accuracy_score(y_te, model.predict(X_te))
    gap    = acc_tr - acc_te
    total_acc.append(acc_te)

    # Top 5 fitur
    imp    = model.named_steps["clf"].feature_importances_
    top5   = sorted(zip(fitur_ada, imp), key=lambda x: -x[1])[:5]
    sd_top = [n for n, v in top5 if n in SD_FITUR]

    print(f"  {sektor:15s} | n={len(df_s):5,} | "
          f"Train={acc_tr:.2%} | Test={acc_te:.2%} | "
          f"Gap={gap:.2%} {'OK' if gap < 0.10 else '!'}")
    if sd_top:
        print(f"    SD fitur masuk top5: {', '.join(sd_top)}")

    models[sektor] = {
        "pipeline"  : model,
        "fitur"     : fitur_ada,
        "acc_test"  : acc_te,
        "n_samples" : len(df_s),
    }

# ── Simpan ────────────────────────────────────────────────────
with open("models/models_latest.pkl", "wb") as f:
    pickle.dump(models, f)
with open("models/models_sd.pkl", "wb") as f:
    pickle.dump(models, f)

avg = np.mean(total_acc)
print(f"\nAkurasi rata-rata: {avg:.2%}")
print(f"Total sektor     : {len(models)}")
print("Model tersimpan!")

# ── Bandingkan dengan sebelumnya ──────────────────────────────
print("\nPerbandingan:")
print(f"  Sebelum (tanpa SD) : 58.74%")
print(f"  Sesudah (dengan SD): {avg:.2%}")
delta = avg - 0.5874
print(f"  Perubahan          : {delta:+.2%}")
