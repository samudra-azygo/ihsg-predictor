"""
auto_retrain.py
Script retrain otomatis yang berjalan di Railway.
Jadwal: setiap Minggu jam 02:00 WIB (Sabtu 19:00 UTC)

Alur:
1. Download data terbaru
2. Retrain model
3. Kalau akurasi naik -> update models_latest.pkl + push ke GitHub
4. Kirim laporan ke Telegram
"""
import os, time, ssl, json, pickle, subprocess, warnings
import urllib.request, urllib.error
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.metrics import accuracy_score
warnings.filterwarnings("ignore")

# ── Config dari environment variables Railway ─────────────────
TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GH_TOKEN= os.environ.get("GITHUB_TOKEN", "")  # perlu ditambah di Railway
GH_REPO = "samudra-azygo/ihsg-predictor"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode    = ssl.CERT_NONE
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AutoRetrain/1.0)"}

os.makedirs("models", exist_ok=True)
os.makedirs("logs", exist_ok=True)
os.makedirs("data", exist_ok=True)

# ── Kirim Telegram ────────────────────────────────────────────
def kirim_telegram(pesan):
    if not TOKEN or not CHAT_ID:
        print(f"[TELEGRAM] {pesan[:100]}")
        return
    try:
        import urllib.parse
        url  = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": CHAT_ID, "text": pesan
        }).encode()
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=10, context=CTX)
    except Exception as e:
        print(f"Telegram error: {e}")

# ── Download Yahoo Finance ────────────────────────────────────
def yahoo_get(ticker, period="5y"):
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
            q      = res[0]["indicators"]["quote"][0]
            closes = q.get("close", [])
            volumes= q.get("volume", [])
            highs  = q.get("high", closes)
            lows   = q.get("low", closes)
            dates  = pd.to_datetime(ts, unit="s").normalize()
            df = pd.DataFrame({
                "date"  : dates,
                "close" : closes,
                "high"  : highs,
                "low"   : lows,
                "volume": volumes,
            }).dropna(subset=["close"])
            df["date"] = df["date"].dt.strftime("%Y-%m-%d")
            return df if len(df) > 50 else None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(8 + attempt*5)
                continue
            return None
        except: return None
    return None

def yahoo_series(ticker, period="5y"):
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
                time.sleep(8 + attempt*5)
                continue
            return None
        except: return None
    return None

# ── Pemetaan sektor lengkap ───────────────────────────────────
SEKTOR = {
    "BBCA":"perbankan","BBRI":"perbankan","BMRI":"perbankan","BBNI":"perbankan",
    "BRIS":"perbankan","BNGA":"perbankan","BBTN":"perbankan","PNBN":"perbankan",
    "BDMN":"perbankan","MEGA":"perbankan","BJBR":"perbankan","NISP":"perbankan",
    "ARTO":"perbankan","BTPS":"perbankan","NOBU":"perbankan","BBMD":"perbankan",
    "AGRO":"perbankan","BJTM":"perbankan","BANK":"perbankan","BBYB":"perbankan",
    "AMAR":"perbankan","BCIC":"perbankan","INPC":"perbankan","BMAS":"perbankan",
    "MCOR":"perbankan","SDRA":"perbankan","BNII":"perbankan","BACA":"perbankan",
    "TLKM":"telekomunikasi","EXCL":"telekomunikasi","ISAT":"telekomunikasi",
    "TOWR":"telekomunikasi","MTEL":"telekomunikasi","TBIG":"telekomunikasi",
    "LINK":"telekomunikasi","CENT":"telekomunikasi","SUPR":"telekomunikasi",
    "ADRO":"tambang","PTBA":"tambang","ITMG":"tambang","INCO":"tambang",
    "ANTM":"tambang","TINS":"tambang","MEDC":"tambang","HRUM":"tambang",
    "MDKA":"tambang","PTRO":"tambang","DOID":"tambang","MBAP":"tambang",
    "GEMS":"tambang","BUMI":"tambang","BYAN":"tambang","MYOH":"tambang",
    "INDY":"tambang","DEWA":"tambang","ARII":"tambang","FIRE":"tambang",
    "GTBO":"tambang","DKFT":"tambang","SMMT":"tambang","ARTI":"tambang",
    "ELSA":"energi","ESSA":"energi","PGAS":"energi","AKRA":"energi",
    "ENRG":"energi","RUIS":"energi","WINS":"energi","MITI":"energi",
    "UNVR":"konsumer","ICBP":"konsumer","MYOR":"konsumer","CPIN":"konsumer",
    "GGRM":"konsumer","HMSP":"konsumer","INDF":"konsumer","ULTJ":"konsumer",
    "DLTA":"konsumer","MLBI":"konsumer","SKBM":"konsumer","SKLT":"konsumer",
    "STTP":"konsumer","ROTI":"konsumer","GOOD":"konsumer","HOKI":"konsumer",
    "ADES":"konsumer","AISA":"konsumer","ALTO":"konsumer","CAMP":"konsumer",
    "CLEO":"konsumer","FOOD":"konsumer","KEJU":"konsumer","PSDN":"konsumer",
    "BTEK":"konsumer","TBLA":"konsumer","SIDO":"konsumer",
    "AALI":"agribisnis","SIMP":"agribisnis","LSIP":"agribisnis",
    "SSMS":"agribisnis","SGRO":"agribisnis","BWPT":"agribisnis",
    "GZCO":"agribisnis","PALM":"agribisnis","SULI":"agribisnis",
    "ANJT":"agribisnis","CSRA":"agribisnis","SMAR":"agribisnis",
    "BSDE":"properti","CTRA":"properti","PWON":"properti","LPKR":"properti",
    "SMRA":"properti","DILD":"properti","MKPI":"properti","ASRI":"properti",
    "BEST":"properti","DART":"properti","EMDE":"properti","GPRA":"properti",
    "JRPT":"properti","KIJA":"properti","MDLN":"properti","MTLA":"properti",
    "RDTX":"properti","WSBP":"properti","TOTL":"properti","WTON":"properti",
    "SMGR":"properti","INTP":"properti","SMBR":"properti","KRAS":"properti",
    "WIKA":"properti","PTPP":"properti","WSKT":"properti","ADHI":"properti",
    "NRCA":"properti","IDPR":"properti","CSIS":"properti","GWSA":"properti",
    "NIRO":"properti","PPRO":"properti","RBMS":"properti","RODA":"properti",
    "JIHD":"properti","PJAA":"properti","SMDM":"properti","SCBD":"properti",
    "MIKA":"kesehatan","SILO":"kesehatan","HEAL":"kesehatan","PRDA":"kesehatan",
    "SAME":"kesehatan","PYFA":"kesehatan","TSPC":"kesehatan","INAF":"kesehatan",
    "KLBF":"kesehatan","KAEF":"kesehatan","SOHO":"kesehatan","MERK":"kesehatan",
    "DVLA":"kesehatan","SCPI":"kesehatan","IRRA":"kesehatan",
    "SCMA":"media","MNCN":"media","EMTK":"media","BMTR":"media",
    "KPIG":"media","MDIA":"media","FILM":"media","VIVA":"media","IPTV":"media",
    "GOTO":"teknologi","BUKA":"teknologi","DMMX":"teknologi","MTDL":"teknologi",
    "MCAS":"teknologi","WIFI":"teknologi","PADI":"teknologi","JTPE":"teknologi",
    "ACES":"ritel","MAPI":"ritel","LPPF":"ritel","RALS":"ritel",
    "HERO":"ritel","MIDI":"ritel","AMRT":"ritel","CSAP":"ritel",
    "RANC":"ritel","EPMT":"ritel","LTLS":"ritel","INTA":"ritel",
    "ASII":"otomotif","AUTO":"otomotif","SMSM":"otomotif","UNTR":"otomotif",
    "INDS":"otomotif","GJTL":"otomotif","IMAS":"otomotif",
    "NIPS":"otomotif","PRAS":"otomotif","DRMA":"otomotif","BOLT":"otomotif",
    "GDYR":"otomotif","LPIN":"otomotif",
    "ADMF":"keuangan","BFIN":"keuangan","CFIN":"keuangan","PNLF":"keuangan",
    "SMMA":"keuangan","WOMF":"keuangan","BCAP":"keuangan","TRIM":"keuangan",
    "VINS":"keuangan","PNIN":"keuangan","ABDA":"keuangan","ASRM":"keuangan",
    "LPGI":"keuangan","OCAP":"keuangan","AHAP":"keuangan","MREI":"keuangan",
    "JSMR":"infrastruktur","CMNP":"infrastruktur","META":"infrastruktur",
    "NELY":"infrastruktur","PORT":"infrastruktur","GIAA":"infrastruktur",
    "TMAS":"infrastruktur","HITS":"infrastruktur","IATA":"infrastruktur",
    "GMFI":"infrastruktur","JAYA":"infrastruktur",
    "BAJA":"industri","ISSP":"industri","LION":"industri","LMSH":"industri",
    "PICO":"industri","TBMS":"industri","KDSI":"industri",
    "KBLI":"industri","KBLM":"industri","SCCO":"industri","VOKS":"industri",
}

SAHAM_DOWNLOAD = [
    "BBCA","BBRI","BMRI","BBNI","BRIS","BNGA","BBTN","PNBN","BDMN","MEGA",
    "BJBR","NISP","ARTO","BTPS","NOBU","AGRO","BJTM","BANK",
    "TLKM","EXCL","ISAT","TOWR","MTEL","TBIG","LINK","CENT",
    "ADRO","PTBA","ITMG","INCO","ANTM","TINS","MEDC","HRUM","MDKA",
    "PTRO","DOID","MBAP","GEMS","BUMI","BYAN","MYOH","INDY","DEWA",
    "ELSA","ESSA","PGAS","AKRA","ENRG","RUIS",
    "UNVR","ICBP","MYOR","CPIN","GGRM","HMSP","INDF","ULTJ","DLTA",
    "MLBI","SKBM","SKLT","STTP","ROTI","GOOD","ADES","AISA","ALTO",
    "AALI","SIMP","LSIP","SSMS","SGRO","BWPT","ANJT","SMAR",
    "BSDE","CTRA","PWON","LPKR","SMRA","DILD","MKPI","ASRI","BEST",
    "DART","JRPT","KIJA","MDLN","MTLA","RDTX","WSBP","TOTL","WTON",
    "SMGR","INTP","WIKA","PTPP","WSKT","ADHI","NRCA","IDPR","KRAS",
    "MIKA","SILO","HEAL","PRDA","SAME","PYFA","TSPC","INAF","KLBF",
    "KAEF","SOHO","MERK","DVLA","SCPI","SIDO",
    "SCMA","MNCN","EMTK","BMTR","KPIG","MDIA","FILM","VIVA",
    "GOTO","BUKA","DMMX","MTDL","MCAS","WIFI",
    "ACES","MAPI","LPPF","RALS","HERO","MIDI","AMRT","CSAP","RANC",
    "ASII","AUTO","SMSM","UNTR","INDS","GJTL","IMAS","NIPS","BOLT",
    "ADMF","BFIN","CFIN","PNLF","SMMA","WOMF","BCAP","TRIM","VINS",
    "PNIN","ABDA","ASRM","LPGI","AHAP",
    "JSMR","CMNP","META","NELY","PORT","GIAA","TMAS","HITS","IATA",
    "BAJA","ISSP","LION","KBLI","KBLM","SCCO","VOKS",
]

# ── Fitur teknikal ────────────────────────────────────────────
def fitur_teknikal(df):
    close  = pd.to_numeric(df["close"], errors="coerce")
    high   = pd.to_numeric(df.get("high", close), errors="coerce")
    low    = pd.to_numeric(df.get("low", close), errors="coerce")
    volume = pd.to_numeric(df.get("volume", pd.Series(1e6, index=df.index)),
                           errors="coerce").fillna(1e6)
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta).clip(lower=0).rolling(14).mean()
    rsi   = 100-(100/(1+gain/loss.replace(0,np.nan)))
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd  = ema12-ema26
    msig  = macd.ewm(span=9).mean()
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    std20 = close.rolling(20).std()
    bb    = (close-(sma20-2*std20))/(4*std20).replace(0,np.nan)
    vol_r = volume/volume.rolling(20).mean().replace(0,np.nan)
    ret   = close.pct_change()
    tp    = (high+low+close)/3
    mf    = tp*volume
    pmf   = mf.where(tp>tp.shift(1),0).rolling(14).sum()
    nmf   = mf.where(tp<tp.shift(1),0).rolling(14).sum()
    mfi   = 100-(100/(1+pmf/nmf.replace(0,np.nan)))
    mfv   = ((close-low)-(high-close))/(high-low).replace(0,np.nan)*volume
    cmf   = mfv.rolling(20).sum()/volume.rolling(20).sum().replace(0,np.nan)
    f = pd.DataFrame(index=df.index)
    f["rsi"]            = rsi
    f["macd"]           = macd
    f["macd_hist"]      = macd-msig
    f["bb_pct"]         = bb
    f["vol_ratio"]      = vol_r
    f["return_lag1"]    = ret.shift(1)
    f["return_lag3"]    = ret.rolling(3).sum().shift(1)
    f["return_lag5"]    = ret.rolling(5).sum().shift(1)
    f["volatility_5d"]  = ret.rolling(5).std()
    f["volatility_20d"] = ret.rolling(20).std()
    f["above_ma20"]     = (close>sma20).astype(int)
    f["above_ma50"]     = (close>sma50).astype(int)
    f["vol_spike"]      = (vol_r>2).astype(int)
    f["akumulasi"]      = ((close>close.shift(1))&(volume>volume.shift(1))).astype(int)
    f["mfi"]            = mfi
    f["cmf"]            = cmf
    f["momentum_5d"]    = close.pct_change(5)
    f["momentum_20d"]   = close.pct_change(20)
    f["bulan"]          = df.index.month
    f["kuartal"]        = df.index.quarter
    f["hari_minggu"]    = df.index.dayofweek
    f["hari_tahun"]     = df.index.dayofyear
    return f

def fitur_asia(data_asia, idx):
    f = pd.DataFrame(index=idx)
    for nama in ["set","hangseng","klci","kospi","sti","sse","nikkei","ftse","dax"]:
        if nama not in data_asia: continue
        s   = data_asia[nama].reindex(idx, method="ffill")
        ret = s.pct_change()
        ma5 = s.rolling(5,min_periods=1).mean()
        f[f"{nama}_ret"]   = ret
        f[f"{nama}_lag1"]  = ret.shift(1)
        f[f"{nama}_trend"] = (s-ma5)/ma5.replace(0,np.nan)
    for nama in ["usdidr","jpyidr"]:
        if nama not in data_asia: continue
        s   = data_asia[nama].reindex(idx, method="ffill")
        ret = s.pct_change()
        f[f"{nama}_ret"]  = ret
        f[f"{nama}_lag1"] = ret.shift(1)
        if nama=="usdidr":
            f["rupiah_lemah"] = (s>16500).astype(int)
    for nama in ["vvix","dowjones","brent"]:
        if nama not in data_asia: continue
        s   = data_asia[nama].reindex(idx, method="ffill")
        ret = s.pct_change()
        f[f"{nama}_lag1"] = ret.shift(1)
        if nama=="vvix":
            f["vvix_tinggi"] = (s.shift(1)>100).astype(int)
            f["vvix_panik"]  = (s.shift(1)>120).astype(int)
        if nama=="brent":
            f["brent_naik"] = (ret.shift(1)>0.02).astype(int)
    return f

def buat_dataset(kode, data_asia):
    for path in [f"data/{kode}.csv", f"data/biostatistik/saham/{kode}.csv"]:
        if not os.path.exists(path): continue
        try:
            df = pd.read_csv(path)
            df.columns = [c.lower() for c in df.columns]
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            for col in ["close","open","high","low","volume"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna(subset=["close"])
            if len(df) < 100: return None, None
            df["target"] = (df["close"].shift(-1) > df["close"]).astype(int)
            ftek  = fitur_teknikal(df)
            fasia = fitur_asia(data_asia, df.index)
            X = pd.concat([ftek, fasia], axis=1)
            y = df["target"]
            valid = y.notna() & (X.isna().sum(axis=1) < X.shape[1]*0.4)
            X = X[valid].fillna(0)
            y = y[valid]
            return (X, y) if len(X) >= 60 else (None, None)
        except:
            continue
    return None, None

def train_sektor(nama, saham_list, data_asia):
    X_all, y_all, ok = [], [], []
    for kode in saham_list:
        X, y = buat_dataset(kode, data_asia)
        if X is not None:
            X_all.append(X); y_all.append(y); ok.append(kode)
    if not X_all: return None
    X_c = pd.concat(X_all).fillna(0)
    y_c = pd.concat(y_all)
    X_c = X_c.loc[:, X_c.nunique() > 1]
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("rf", RandomForestClassifier(
            n_estimators=300, max_depth=10, min_samples_leaf=15,
            max_features="sqrt", random_state=42, n_jobs=-1,
            class_weight="balanced",
        ))
    ])
    tscv = TimeSeriesSplit(n_splits=5)
    try:
        scores = cross_val_score(model, X_c, y_c, cv=tscv,
                                  scoring="accuracy", n_jobs=-1)
        cv_mean = round(float(scores.mean()), 4)
    except:
        cv_mean = 0
    model.fit(X_c, y_c)
    return {
        "pipeline": model, "fitur": X_c.columns.tolist(),
        "cv_accuracy": cv_mean,
        "train_acc": round(accuracy_score(y_c, model.predict(X_c)), 4),
        "n_saham": len(ok), "n_data": len(X_c),
    }

# ══════════════════════════════════════════════════════════════
# MAIN AUTO RETRAIN
# ══════════════════════════════════════════════════════════════
def jalankan_retrain():
    waktu_mulai = datetime.now()
    print(f"\n{'='*60}")
    print(f"AUTO RETRAIN — {waktu_mulai.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    kirim_telegram(
        f"🔄 Auto Retrain dimulai\n"
        f"Waktu: {waktu_mulai.strftime('%d %b %Y %H:%M WIB')}\n"
        f"Target: akurasi > 60.45%"
    )

    # 1. Download saham terbaru
    print("\n[1/5] Download data saham terbaru...")
    ok_saham = 0
    for kode in SAHAM_DOWNLOAD:
        path = f"data/{kode}.csv"
        df_baru = yahoo_get(f"{kode}.JK", period="3mo")
        if df_baru is not None:
            if os.path.exists(path):
                df_lama = pd.read_csv(path)
                df_gabung = pd.concat([df_lama, df_baru]).drop_duplicates(
                    "date").sort_values("date")
                df_gabung.to_csv(path, index=False)
            else:
                df_baru = yahoo_get(f"{kode}.JK", period="max")
                if df_baru is not None:
                    df_baru.to_csv(path, index=False)
            ok_saham += 1
        time.sleep(0.4)
    print(f"  {ok_saham}/{len(SAHAM_DOWNLOAD)} saham diupdate")

    # 2. Download pasar Asia
    print("\n[2/5] Download pasar Asia...")
    tickers_asia = {
        "^SET.BK":"set","^HSI":"hangseng","^KLSE":"klci",
        "^KS11":"kospi","^STI":"sti","000001.SS":"sse",
        "^N225":"nikkei","^FTSE":"ftse","^GDAXI":"dax",
        "USDIDR=X":"usdidr","JPYIDR=X":"jpyidr",
        "^VVIX":"vvix","^DJI":"dowjones","BZ=F":"brent",
    }
    data_asia = {}
    for ticker, nama in tickers_asia.items():
        s = yahoo_series(ticker)
        if s is not None:
            data_asia[nama] = s
        time.sleep(0.8)
    print(f"  {len(data_asia)}/14 sumber Asia berhasil")

    # 3. Kelompokkan saham per sektor
    print("\n[3/5] Kelompokkan saham...")
    SKIP = ["KOMODITAS","MAKRO","CUACA","ENSO","KALENDER","GABUNGAN",
            "BDI","IHSG","KOSPI","STI_","KLCI","Nikkei","HangSeng",
            "SSE","SET_","SP500","DowJones","NASDAQ","FTSE","DAX",
            "VIX","USD","EUR","JPY","SGD","AUD","DXY","USBond",
            "Bitcoin","Ethereum","iShares","MSCI","beras","gandum",
            "jagung","kedelai","kopi","gula","kakao","kapas",
            "minyak","gas","emas","perak","tembaga","palladium"]
    semua_kode = set()
    for folder in ["data", "data/biostatistik/saham"]:
        if not os.path.exists(folder): continue
        for fname in os.listdir(folder):
            if not fname.endswith(".csv"): continue
            if any(x.lower() in fname.lower() for x in SKIP): continue
            kode = fname.replace(".csv","")
            if len(kode) <= 6 and kode.isupper():
                semua_kode.add(kode)
    per_sektor = {}
    for kode in sorted(semua_kode):
        sek = SEKTOR.get(kode, "lainnya")
        per_sektor.setdefault(sek, []).append(kode)
    print(f"  {sum(len(v) for v in per_sektor.values())} saham, "
          f"{len(per_sektor)} sektor")

    # 4. Training
    print("\n[4/5] Training model...")
    models_baru = {}
    hasil_cv = []
    for sektor in sorted(per_sektor.keys()):
        print(f"  [{sektor}]", end=" ", flush=True)
        result = train_sektor(sektor, per_sektor[sektor], data_asia)
        if result:
            models_baru[sektor] = result
            hasil_cv.append({
                "sektor": sektor,
                "cv_accuracy": result["cv_accuracy"],
                "n_saham": result["n_saham"],
            })
            print(f"CV={result['cv_accuracy']:.4f} ({result['n_saham']} saham)")
        else:
            print("skip")

    # 5. Evaluasi dan simpan
    print("\n[5/5] Evaluasi dan simpan...")
    df_cv = pd.DataFrame(hasil_cv)
    avg_cv = df_cv["cv_accuracy"].mean() if len(df_cv) > 0 else 0
    model_lama_acc = 0.6045

    # Simpan model baru
    path_baru = f"models/models_auto_{datetime.now().strftime('%Y%m%d')}.pkl"
    with open(path_baru, "wb") as f:
        pickle.dump(models_baru, f)

    waktu_selesai = datetime.now()
    durasi = (waktu_selesai - waktu_mulai).seconds // 60

    if avg_cv > model_lama_acc:
        # Update models_latest
        import shutil
        shutil.copy(path_baru, "models/models_latest.pkl")
        print(f"  ✅ AKURASI NAIK! {model_lama_acc*100:.2f}% -> {avg_cv*100:.2f}%")

        # Push ke GitHub kalau ada token
        if GH_TOKEN:
            try:
                subprocess.run([
                    "git", "config", "user.email", "bot@ihsg-predictor.com"
                ], check=True)
                subprocess.run([
                    "git", "config", "user.name", "IHSG Bot"
                ], check=True)
                subprocess.run(["git", "add", "models/models_latest.pkl"],
                               check=True)
                subprocess.run([
                    "git", "commit", "-m",
                    f"Auto retrain: {avg_cv*100:.2f}% (+{(avg_cv-model_lama_acc)*100:.2f}%)"
                ], check=True)
                remote_url = (f"https://{GH_TOKEN}@github.com/{GH_REPO}.git")
                subprocess.run(["git", "push", remote_url, "main"],
                               check=True, capture_output=True)
                print("  ✅ Push ke GitHub berhasil")
                gh_status = "✅ GitHub updated"
            except Exception as e:
                print(f"  ✗ GitHub push gagal: {e}")
                gh_status = "⚠️ GitHub push gagal"
        else:
            gh_status = "⚠️ GITHUB_TOKEN belum diset"

        kirim_telegram(
            f"✅ AUTO RETRAIN BERHASIL!\n\n"
            f"Akurasi lama : {model_lama_acc*100:.2f}%\n"
            f"Akurasi baru : {avg_cv*100:.2f}%\n"
            f"Peningkatan  : +{(avg_cv-model_lama_acc)*100:.2f}%\n"
            f"Durasi       : {durasi} menit\n"
            f"GitHub       : {gh_status}\n\n"
            f"Model sudah diupdate dan aktif!"
        )
    else:
        import shutil
        shutil.copy("models/models_final.pkl", "models/models_latest.pkl")
        print(f"  ⚠️ Akurasi tidak naik: {avg_cv*100:.2f}% < {model_lama_acc*100:.2f}%")
        print(f"  Model lama tetap dipakai")

        kirim_telegram(
            f"⚠️ Auto Retrain selesai — akurasi belum naik\n\n"
            f"Akurasi baru : {avg_cv*100:.2f}%\n"
            f"Akurasi lama : {model_lama_acc*100:.2f}%\n"
            f"Durasi       : {durasi} menit\n\n"
            f"Model lama tetap aktif."
        )

    df_cv.to_csv(f"logs/auto_retrain_{datetime.now().strftime('%Y%m%d')}.csv",
                 index=False)
    print(f"\nSelesai: {waktu_selesai.strftime('%H:%M:%S')} "
          f"(durasi {durasi} menit)")
    return avg_cv

if __name__ == "__main__":
    jalankan_retrain()
