"""
train_swing.py
Model baru: prediksi saham naik >= 1.5% dalam 1-3 hari
Berbasis korelasi teknikal — tidak peduli fundamental
"""
import os, time, ssl, json, pickle, warnings
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.metrics import accuracy_score, classification_report
warnings.filterwarnings("ignore")

os.makedirs("models", exist_ok=True)
os.makedirs("logs", exist_ok=True)

print("="*60)
print("TRAINING MODEL SWING 1-3 HARI")
print("Target: naik >= 1.5% dalam 1-3 hari ke depan")
print("="*60)

def hitung_fitur_swing(df):
    """Fitur teknikal untuk prediksi swing 1-3 hari."""
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
    f["rsi"]           = rsi
    f["rsi_oversold"]  = (rsi < 30).astype(int)
    f["rsi_naik"]      = ((rsi > rsi.shift(1)) & (rsi < 50)).astype(int)
    f["rsi_cross50"]   = ((rsi > 50) & (rsi.shift(1) <= 50)).astype(int)

    # ── MACD ─────────────────────────────────────────────────
    ema12  = close.ewm(span=12).mean()
    ema26  = close.ewm(span=26).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    f["macd"]          = macd
    f["macd_hist"]     = macd - signal
    f["macd_cross"]    = ((macd > signal) & (macd.shift(1) <= signal.shift(1))).astype(int)
    f["macd_positif"]  = (macd > 0).astype(int)

    # ── Bollinger Band ────────────────────────────────────────
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bb_up = sma20 + 2*std20
    bb_lo = sma20 - 2*std20
    f["bb_pct"]        = (close - bb_lo) / (4*std20).replace(0, np.nan)
    f["below_bb"]      = (close < bb_lo).astype(int)
    f["bb_squeeze"]    = (std20 < std20.rolling(20).mean()*0.8).astype(int)

    # ── Moving Average ────────────────────────────────────────
    sma5   = close.rolling(5).mean()
    sma10  = close.rolling(10).mean()
    sma50  = close.rolling(50).mean()
    f["close_vs_sma5"]  = (close / sma5.replace(0, np.nan) - 1)
    f["close_vs_sma10"] = (close / sma10.replace(0, np.nan) - 1)
    f["close_vs_sma50"] = (close / sma50.replace(0, np.nan) - 1)
    f["sma5_cross10"]   = ((sma5 > sma10) & (sma5.shift(1) <= sma10.shift(1))).astype(int)
    f["golden_cross"]   = ((sma5 > sma10) & (sma10 > sma50)).astype(int)

    # ── Volume ───────────────────────────────────────────────
    vol_ma = volume.rolling(20).mean().replace(0, np.nan)
    f["vol_ratio"]     = volume / vol_ma
    f["vol_spike"]     = (f["vol_ratio"] > 2).astype(int)
    f["vol_naik"]      = (volume > volume.shift(1)).astype(int)
    # Akumulasi: harga naik + volume besar
    f["akumulasi"]     = ((close > close.shift(1)) & (f["vol_ratio"] > 1.5)).astype(int)
    f["akumulasi_2d"]  = f["akumulasi"].rolling(2).sum()

    # ── Breakout ─────────────────────────────────────────────
    high20 = high.rolling(20).max()
    low20  = low.rolling(20).min()
    f["breakout_up"]   = ((close > high20.shift(1)) & (f["vol_ratio"] > 1.5)).astype(int)
    f["near_high20"]   = ((close / high20.replace(0, np.nan)) > 0.97).astype(int)
    f["range_pct"]     = (high20 - low20) / low20.replace(0, np.nan)

    # ── Stochastic ───────────────────────────────────────────
    low14  = low.rolling(14).min()
    high14 = high.rolling(14).max()
    stoch  = (close - low14) / (high14 - low14).replace(0, np.nan) * 100
    stoch_d = stoch.rolling(3).mean()
    f["stoch_k"]       = stoch
    f["stoch_oversold"]= (stoch < 20).astype(int)
    f["stoch_cross"]   = ((stoch > stoch_d) & (stoch.shift(1) <= stoch_d.shift(1)) & (stoch < 40)).astype(int)

    # ── Candle Pattern ────────────────────────────────────────
    body   = abs(close - close.shift(1))
    shadow = high - low
    f["hammer"]        = ((shadow > body*2) & (close > close.shift(1))).astype(int)
    f["doji"]          = (body < shadow*0.1).astype(int)
    f["strong_candle"] = ((close - close.shift(1)) > close.shift(1)*0.02).astype(int)

    # ── Return lags ──────────────────────────────────────────
    for lag in [1, 2, 3, 5]:
        f[f"ret_{lag}d"]   = ret.shift(lag)
    f["ret_5d_sum"]    = ret.shift(1).rolling(5).sum()
    f["volatility_5d"] = ret.rolling(5).std()
    f["volatility_10d"]= ret.rolling(10).std()

    # ── MFI ──────────────────────────────────────────────────
    tp   = (high + low + close) / 3
    mf   = tp * volume
    pmf  = mf.where(tp > tp.shift(1), 0).rolling(14).sum()
    nmf  = mf.where(tp < tp.shift(1), 0).rolling(14).sum()
    mfi  = 100 - (100 / (1 + pmf / nmf.replace(0, np.nan)))
    f["mfi"]           = mfi
    f["mfi_oversold"]  = (mfi < 20).astype(int)

    # ── Kalender ─────────────────────────────────────────────
    f["hari"]          = df.index.dayofweek
    f["bulan"]         = df.index.month
    f["senin"]         = (df.index.dayofweek == 0).astype(int)
    f["jumat"]         = (df.index.dayofweek == 4).astype(int)

    return f

# ── Load semua data ───────────────────────────────────────────
print("\n[1/4] Load data saham...")
folder_list = ["data/idx500", "data", "data/biostatistik/saham"]

X_all = []
y_all = []
meta  = []

for folder in folder_list:
    if not os.path.exists(folder):
        continue
    files = [f for f in os.listdir(folder) if f.endswith(".csv")]
    print(f"  Folder {folder}: {len(files)} file")

    for fname in files:
        kode = fname.replace(".csv", "")
        if any(kode in m["kode"] for m in meta):
            continue  # skip duplikat

        path = os.path.join(folder, fname)
        try:
            df = pd.read_csv(path)
            df.columns = [c.lower() for c in df.columns]
            if "date" not in df.columns:
                continue
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            for col in ["close","high","low","volume","open"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna(subset=["close"])
            df = df[df["close"] > 50]  # filter harga terlalu murah (penny stock)

            if len(df) < 150:
                continue

            # TARGET: naik >= 1.5% dalam 1-3 hari ke depan
            close = df["close"]
            ret_max_3d = pd.DataFrame({
                "r1": close.shift(-1) / close - 1,
                "r2": close.shift(-2) / close - 1,
                "r3": close.shift(-3) / close - 1,
            }).max(axis=1)
            target = (ret_max_3d >= 0.015).astype(int)

            X = hitung_fitur_swing(df)
            df_g = X.copy()
            df_g["target"] = target

            valid = (df_g["target"].notna() &
                     (df_g.isna().sum(axis=1) < df_g.shape[1] * 0.4))
            df_g = df_g[valid].fillna(0)

            if len(df_g) < 100:
                continue

            y_k = df_g["target"]
            X_k = df_g.drop("target", axis=1)

            X_all.append(X_k)
            y_all.append(y_k)
            meta.append({"kode": kode, "n": len(X_k)})

        except Exception as e:
            continue

print(f"\n  Total saham berhasil : {len(meta)}")
print(f"  Total baris data     : {sum(m['n'] for m in meta):,}")

if not X_all:
    print("ERROR: tidak ada data! Jalankan download_idx500.py dulu.")
    exit()

# ── Training ─────────────────────────────────────────────────
print("\n[2/4] Gabungkan dataset...")
X_combined = pd.concat(X_all).fillna(0)
y_combined = pd.concat(y_all)
X_combined = X_combined.loc[:, X_combined.nunique() > 1]

fitur_list = X_combined.columns.tolist()
print(f"  Dataset  : {len(X_combined):,} baris | {len(fitur_list)} fitur")
print(f"  Positif  : {y_combined.sum():,} ({y_combined.mean()*100:.1f}%)")
print(f"  Negatif  : {(1-y_combined).sum():,} ({(1-y_combined).mean()*100:.1f}%)")

print("\n[3/4] Training model...")
model_rf = Pipeline([
    ("scaler", StandardScaler()),
    ("rf", RandomForestClassifier(
        n_estimators=400,
        max_depth=12,
        min_samples_leaf=10,
        max_features="sqrt",
        random_state=42,
        n_jobs=-1,
        class_weight="balanced",
    ))
])

model_gb = Pipeline([
    ("scaler", StandardScaler()),
    ("gb", GradientBoostingClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        random_state=42,
    ))
])

tscv = TimeSeriesSplit(n_splits=5)

print("  Random Forest...")
scores_rf = cross_val_score(model_rf, X_combined, y_combined,
                             cv=tscv, scoring="accuracy", n_jobs=-1)
print(f"    CV: {scores_rf.mean():.4f} +/- {scores_rf.std():.4f}")

print("  Gradient Boosting...")
scores_gb = cross_val_score(model_gb, X_combined, y_combined,
                             cv=tscv, scoring="accuracy", n_jobs=-1)
print(f"    CV: {scores_gb.mean():.4f} +/- {scores_gb.std():.4f}")

if scores_rf.mean() >= scores_gb.mean():
    model_final = model_rf
    nama = "RandomForest"
    cv   = scores_rf.mean()
else:
    model_final = model_gb
    nama = "GradientBoosting"
    cv   = scores_gb.mean()

print(f"\n  Model terpilih: {nama} (CV={cv:.4f})")
model_final.fit(X_combined, y_combined)
train_acc = accuracy_score(y_combined, model_final.predict(X_combined))
print(f"  Train accuracy: {train_acc:.4f}")

# ── Feature importance ────────────────────────────────────────
print("\n[4/4] Simpan model...")
if nama == "RandomForest":
    imp = model_final.named_steps["rf"].feature_importances_
else:
    imp = model_final.named_steps["gb"].feature_importances_

df_imp = pd.DataFrame({"fitur": fitur_list, "importance": imp}
                      ).sort_values("importance", ascending=False)
print("\n  TOP 15 FITUR:")
for _, r in df_imp.head(15).iterrows():
    bar = "█" * int(r["importance"]*300)
    print(f"    {r['fitur']:<25} {r['importance']:.4f}  {bar}")

# Simpan
model_swing = {
    "pipeline"   : model_final,
    "fitur"      : fitur_list,
    "cv_accuracy": round(float(cv), 4),
    "train_acc"  : round(float(train_acc), 4),
    "nama_model" : nama,
    "target"     : "naik >= 1.5% dalam 1-3 hari",
    "n_saham"    : len(meta),
    "n_data"     : len(X_combined),
    "tanggal"    : datetime.now().strftime("%Y-%m-%d"),
}
with open("models/model_swing.pkl", "wb") as f:
    pickle.dump(model_swing, f)
df_imp.to_csv("logs/fitur_swing.csv", index=False)

print(f"\n{'='*60}")
print(f"SELESAI!")
print(f"  Model    : models/model_swing.pkl")
print(f"  CV Acc   : {cv*100:.2f}%")
print(f"  Saham    : {len(meta)} saham dipakai training")
print(f"  Target   : naik >= 1.5% dalam 1-3 hari")
print(f"\nLangkah berikutnya: jalankan scoring_swing.py")
