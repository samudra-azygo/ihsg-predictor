"""
scoring_swing.py
Scoring semua saham IDX berdasarkan model swing 1-3 hari
Tidak peduli fundamental — yang penting korelasi teknikal kuat
"""
import os, time, ssl, json, pickle, warnings
import pandas as pd
import numpy as np
import urllib.request, urllib.parse
from datetime import datetime
warnings.filterwarnings("ignore")

TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode    = ssl.CERT_NONE

def hitung_fitur_swing(df):
    close  = pd.to_numeric(df["close"],  errors="coerce")
    high   = pd.to_numeric(df.get("high",  close), errors="coerce")
    low    = pd.to_numeric(df.get("low",   close), errors="coerce")
    volume = pd.to_numeric(df.get("volume",
             pd.Series(1e6, index=df.index)), errors="coerce").fillna(1e6)
    ret = close.pct_change()
    f   = pd.DataFrame(index=df.index)

    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta).clip(lower=0).rolling(14).mean()
    rsi   = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
    f["rsi"]           = rsi
    f["rsi_oversold"]  = (rsi < 30).astype(int)
    f["rsi_naik"]      = ((rsi > rsi.shift(1)) & (rsi < 50)).astype(int)
    f["rsi_cross50"]   = ((rsi > 50) & (rsi.shift(1) <= 50)).astype(int)

    ema12  = close.ewm(span=12).mean()
    ema26  = close.ewm(span=26).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    f["macd"]          = macd
    f["macd_hist"]     = macd - signal
    f["macd_cross"]    = ((macd > signal) & (macd.shift(1) <= signal.shift(1))).astype(int)
    f["macd_positif"]  = (macd > 0).astype(int)

    sma5   = close.rolling(5).mean()
    sma10  = close.rolling(10).mean()
    sma20  = close.rolling(20).mean()
    sma50  = close.rolling(50).mean()
    std20  = close.rolling(20).std()
    bb_lo  = sma20 - 2*std20
    f["bb_pct"]        = (close - bb_lo) / (4*std20).replace(0, np.nan)
    f["below_bb"]      = (close < bb_lo).astype(int)
    f["bb_squeeze"]    = (std20 < std20.rolling(20).mean()*0.8).astype(int)
    f["close_vs_sma5"] = (close / sma5.replace(0,np.nan) - 1)
    f["close_vs_sma10"]= (close / sma10.replace(0,np.nan) - 1)
    f["close_vs_sma50"]= (close / sma50.replace(0,np.nan) - 1)
    f["sma5_cross10"]  = ((sma5>sma10)&(sma5.shift(1)<=sma10.shift(1))).astype(int)
    f["golden_cross"]  = ((sma5>sma10)&(sma10>sma50)).astype(int)

    vol_ma = volume.rolling(20).mean().replace(0,np.nan)
    f["vol_ratio"]     = volume / vol_ma
    f["vol_spike"]     = (f["vol_ratio"] > 2).astype(int)
    f["vol_naik"]      = (volume > volume.shift(1)).astype(int)
    f["akumulasi"]     = ((close>close.shift(1))&(f["vol_ratio"]>1.5)).astype(int)
    f["akumulasi_2d"]  = f["akumulasi"].rolling(2).sum()

    high20 = high.rolling(20).max()
    low20  = low.rolling(20).min()
    f["breakout_up"]   = ((close>high20.shift(1))&(f["vol_ratio"]>1.5)).astype(int)
    f["near_high20"]   = ((close/high20.replace(0,np.nan))>0.97).astype(int)
    f["range_pct"]     = (high20-low20)/low20.replace(0,np.nan)

    low14  = low.rolling(14).min()
    high14 = high.rolling(14).max()
    stoch  = (close-low14)/(high14-low14).replace(0,np.nan)*100
    stoch_d= stoch.rolling(3).mean()
    f["stoch_k"]       = stoch
    f["stoch_oversold"]= (stoch<20).astype(int)
    f["stoch_cross"]   = ((stoch>stoch_d)&(stoch.shift(1)<=stoch_d.shift(1))&(stoch<40)).astype(int)

    body   = abs(close-close.shift(1))
    shadow = high-low
    f["hammer"]        = ((shadow>body*2)&(close>close.shift(1))).astype(int)
    f["doji"]          = (body<shadow*0.1).astype(int)
    f["strong_candle"] = ((close-close.shift(1))>close.shift(1)*0.02).astype(int)

    for lag in [1,2,3,5]:
        f[f"ret_{lag}d"] = ret.shift(lag)
    f["ret_5d_sum"]    = ret.shift(1).rolling(5).sum()
    f["volatility_5d"] = ret.rolling(5).std()
    f["volatility_10d"]= ret.rolling(10).std()

    tp   = (high+low+close)/3
    mf   = tp*volume
    pmf  = mf.where(tp>tp.shift(1),0).rolling(14).sum()
    nmf  = mf.where(tp<tp.shift(1),0).rolling(14).sum()
    mfi  = 100-(100/(1+pmf/nmf.replace(0,np.nan)))
    f["mfi"]           = mfi
    f["mfi_oversold"]  = (mfi<20).astype(int)

    f["hari"]          = df.index.dayofweek
    f["bulan"]         = df.index.month
    f["senin"]         = (df.index.dayofweek==0).astype(int)
    f["jumat"]         = (df.index.dayofweek==4).astype(int)
    return f

def scoring_swing():
    tanggal = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"SCORING SWING 1-3 HARI — {tanggal}")
    print(f"{'='*60}")

    # Load model
    try:
        with open("models/model_swing.pkl", "rb") as f:
            rb = pickle.load(f)
        model    = rb["pipeline"]
        fitur_list = rb["fitur"]
        cv_acc   = rb.get("cv_accuracy", 0)
        print(f"  Model dimuat: {rb['nama_model']} (CV={cv_acc*100:.1f}%)")
    except Exception as e:
        print(f"  ERROR load model: {e}")
        print(f"  Jalankan train_swing.py dulu!")
        return

    # Scan semua saham
    hasil = []
    folder_list = ["data"]
    scanned = set()

    for folder in folder_list:
        if not os.path.exists(folder):
            continue
        for fname in os.listdir(folder):
            if not fname.endswith(".csv"):
                continue
            kode = fname.replace(".csv", "")
            if kode in scanned or kode.startswith("KOMODITAS"):
                continue
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

                if len(df) < 100: continue
                harga = float(df["close"].iloc[-1])
                if harga < 50: continue  # filter penny stock

                X = hitung_fitur_swing(df)
                X = X.fillna(0)

                for col in fitur_list:
                    if col not in X.columns:
                        X[col] = 0
                X_last = X[fitur_list].iloc[[-1]]

                proba = float(model.predict_proba(X_last)[0][1])

                # Sinyal berdasarkan probabilitas
                if proba >= 0.55:
                    sinyal = "BELI"
                elif proba >= 0.45:
                    sinyal = "PANTAU"
                else:
                    sinyal = "SKIP"

                if sinyal in ["BELI", "PANTAU"]:
                    rsi_now = float(X["rsi"].iloc[-1]) if "rsi" in X.columns else 50
                    vol_r   = float(X["vol_ratio"].iloc[-1]) if "vol_ratio" in X.columns else 1
                    hasil.append({
                        "ticker" : kode,
                        "harga"  : harga,
                        "proba"  : round(proba, 3),
                        "rsi"    : round(rsi_now, 1),
                        "vol_r"  : round(vol_r, 2),
                        "sinyal" : sinyal,
                    })
            except:
                continue

    df_hasil = pd.DataFrame(hasil) if hasil else pd.DataFrame(columns=["ticker","harga","proba","rsi","vol_r","sinyal"])
    if not df_hasil.empty: df_hasil = df_hasil.sort_values("proba", ascending=False)
    df_hasil.to_csv(f"logs/swing_{tanggal}.csv", index=False)

    beli   = df_hasil[df_hasil["sinyal"]=="BELI"]
    pantau = df_hasil[df_hasil["sinyal"]=="PANTAU"]

    print(f"\n  Total discan  : {len(scanned)} saham")
    print(f"  Sinyal BELI   : {len(beli)}")
    print(f"  Sinyal PANTAU : {len(pantau)}")

    print(f"\n{'─'*65}")
    print(f"TOP SINYAL BELI (naik >= 1.5% dalam 1-3 hari):")
    print(f"{'─'*65}")
    print(f"{'Ticker':<8} {'Harga':>10} {'Proba':>7} {'RSI':>6} {'VolR':>6}  Sinyal")
    print("─"*65)
    for _, r in df_hasil[df_hasil["sinyal"]=="BELI"].head(20).iterrows():
        print(f"{r['ticker']:<8} {r['harga']:>10,.0f} {r['proba']:>7.3f} "
              f"{r['rsi']:>6.1f} {r['vol_r']:>6.2f}  {r['sinyal']}")

    if len(pantau) > 0:
        print(f"\nPANTAU ({len(pantau)}): {', '.join(pantau['ticker'].head(10).tolist())}")

    # Kirim Telegram
    if TOKEN and CHAT_ID:
        baris = [
            f"🎯 SWING SCANNER 1-3 HARI — {tanggal}",
            f"Scan: {len(scanned)} saham | Model CV: {cv_acc*100:.1f}%",
            "",
        ]
        if len(beli) > 0:
            baris.append(f"✅ SINYAL BELI ({len(beli)} saham):")
            for _, r in beli.head(10).iterrows():
                baris.append(f"  {r['ticker']:6} | Rp{r['harga']:,.0f} | prob:{r['proba']:.2f} | RSI:{r['rsi']:.0f}")
        else:
            baris.append("Tidak ada sinyal BELI hari ini")

        if len(pantau) > 0:
            baris.append(f"\n👀 PANTAU: {', '.join(pantau['ticker'].head(8).tolist())}")

        baris.append(f"\n[Swing model: korelasi teknikal 1-3 hari]")
        data = urllib.parse.urlencode({
            "chat_id": CHAT_ID,
            "text": chr(10).join(baris),
            "parse_mode": "HTML"
        }).encode()
        try:
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=data)
            urllib.request.urlopen(req, timeout=15, context=_SSL_CTX)
            print("\n  ✓ Terkirim ke Telegram")
        except Exception as e:
            print(f"\n  ✗ Telegram error: {e}")

    return df_hasil

if __name__ == "__main__":
    scoring_swing()
