"""
download_idx500.py
Download data harga semua saham IDX (500+ saham)
Simpan ke data/idx500/KODE.csv
"""
import os, time, ssl, json, urllib.request, urllib.error
import pandas as pd
from datetime import datetime

os.makedirs("data/idx500", exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; IDXBot/1.0)"}

# 500+ saham IDX paling likuid dan aktif
SAHAM_IDX = [
    # Perbankan
    "BBCA","BBRI","BMRI","BBNI","BRIS","BNGA","BBTN","PNBN","BDMN","NISP",
    "MEGA","BTPN","AGRO","BNBA","BJTM","BJBR","BKSW","BTPS","DNAR","ARTO",
    # Tambang & Energi
    "ADRO","PTBA","ITMG","INCO","ANTM","TINS","MEDC","HRUM","MDKA","MBAP",
    "ESSA","ELSA","PGAS","AKRA","DSSA","BYAN","GEMS","GTBO","KKGI","SMMT",
    "ARTI","BIPI","ENRG","FIRE","INDO","MYOH","PKPK","PSAB","RUIS","SMRU",
    # Telekomunikasi
    "TLKM","EXCL","ISAT","TOWR","MTEL","TBIG","FREN","DEAL","MORA",
    # Konsumer & Retail
    "UNVR","ICBP","MYOR","KLBF","KAEF","CPIN","GGRM","HMSP","SIDO","ULTJ",
    "INDF","MLBI","DLTA","SKBM","SKLT","CAMP","CEKA","GOOD","HOKI","KEJU",
    "LPIN","MGNA","MRAT","PCAR","PSDN","ROTI","STTP","TBLA","ULTJ","WIIM",
    "ACES","MAPI","LPPF","RALS","HERO","AMRT","MIDI","CSAP","MPPA","RANC",
    # Properti & Konstruksi  
    "BSDE","CTRA","PWON","LPKR","SMRA","ASRI","DILD","MDLN","MKPI","MMLP",
    "APLN","DART","EMDE","FORZ","GPRA","GWSA","JRPT","KIJA","LAND","LPCK",
    "NIRO","OMRE","PLIN","POLL","PPRO","RBMS","RDTX","RODA","SMDM","SMCB",
    "SMGR","INTP","WTON","WSBP","ARNA","MARK","TOTO","CLEO",
    # Otomotif & Manufaktur
    "ASII","AUTO","SMSM","UNTR","IMAS","INDS","LPIN","MASA","NIPS","PRAS",
    "ADMG","AMIN","BOLT","BRAM","GDYR","GJTL","INKA","KRAH","LEMA","MDRN",
    # Agribisnis
    "AALI","SIMP","LSIP","BWPT","GZCO","JAWA","MAGP","PALM","SGRO","SSMS",
    "TBLA","UNSP","ANJT","DSNG","HACL",
    # Kesehatan & Farmasi
    "MIKA","SILO","HEAL","KLBF","KAEF","TSPC","SCPI","MERK","INAF","PYFA",
    "PRDA","SAME","SRAJ","CARE",
    # Media & Teknologi
    "SCMA","MNCN","EMTK","GOTO","BUKA","MTDL","MLPT","LUCK","EDGE","DMMX",
    "INET","KIOS","MCAS","MPXL","NFCX","PEGE","UANG","VKTR","WIFI","YELO",
    # Infrastruktur & Utilitas
    "JSMR","WIKA","WSKT","ADHI","PTPP","NRCA","TOTL","DGIK","IDPR","PBSA",
    "CASS","GIAA","INDY","IPCM","MBSS","NELY","SAFE","SMDR","SOCI","TMAS",
    "ASSA","BIRD","BLTA","CMPP","HELI","LRNA","MIRA","TAXI","TRJA","WEHA",
    # Keuangan Non-Bank
    "ADMF","BFIN","CFIN","MFIN","TIFA","VRNA","WOMF","DEFI","HDFA","IMJS",
    "BCAP","BBLD","BPII","GSMF","PANS","TRIM","YULE",
    # Lainnya
    "PTRO","DOID","BULL","COCO","DNET","EPMT","ERAA","FISH","FOOD","FORU",
    "GEMA","GREN","GWSA","HADE","HERO","HKMU","HRTA","IGAR","IKBI","INCI",
    "IPOL","ISSP","JAWA","JECC","JIHD","JPFA","KBLI","KBLM","KDSI","KICI",
    "KINO","KMTR","KOBX","KOIN","KPIG","LMAS","LMSH","MAIN","MAMI","MAPI",
    "MATS","MBAP","MBSS","MCOR","MDLN","MFMI","MIKA","MKTR","MLBI","MLIA",
    "MLPL","MNCN","MOLI","MPMX","MPPA","MRAT","MSKY","MTLA","MYOR","MYRX",
    "NASI","NCKL","NIKL","NIRO","NRCA","NSSS","OCAP","OILS","OKAS","PBRX",
    "PDES","PEGE","PGLI","PICO","PJAA","PKPK","PLAS","PLIN","PMJS","PNGO",
    "POWR","PPGL","PPRE","PRAS","PRDA","PSSI","PTIS","PTSP","PYFA","RAAM",
    "RBMS","RCCC","RDTX","RICY","RIGS","RIMO","RMBA","ROTI","RUIS","SAFE",
    "SAME","SIMA","SMBR","SMCB","SMDM","SMDR","SMGR","SMMT","SMRA","SMRU",
    "SOCI","SOHO","SONA","SOSS","SRIL","SRSN","SRTG","SSMS","STTP","SUGI",
    "TALF","TAXI","TBIG","TBLA","TCPI","TDPM","TELE","TFCO","TGKA","TGRA",
    "TINS","TIRA","TKGA","TKIM","TLKM","TMAS","TNCA","TOPS","TOTL","TOWR",
    "TRIM","TRJA","TRST","TSPC","TUGU","UANG","UCID","ULTJ","UNIC","UNSP",
    "VICI","VINS","VIVA","VKTR","WEGE","WEHA","WIFI","WIKA","WIIM","WINS",
    "WMPP","WOMF","WSKT","WTON","YELO","YULE","ZINC","ZYRX",
]
# Hapus duplikat
SAHAM_IDX = list(dict.fromkeys(SAHAM_IDX))
print(f"Total saham target: {len(SAHAM_IDX)}")

def download_saham(kode, period="2y"):
    ticker = f"{kode}.JK"
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?range={period}&interval=1d&includePrePost=false")
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
                d = json.loads(r.read().decode())
            res = d["chart"]["result"]
            if not res: return None
            ts      = res[0]["timestamp"]
            q       = res[0]["indicators"]["quote"][0]
            closes  = q.get("close", [])
            volumes = q.get("volume", [])
            highs   = q.get("high",  closes)
            lows    = q.get("low",   closes)
            opens   = q.get("open",  closes)
            dates   = pd.to_datetime(ts, unit="s").normalize()
            df = pd.DataFrame({
                "date"  : dates,
                "open"  : opens,
                "high"  : highs,
                "low"   : lows,
                "close" : closes,
                "volume": volumes,
            }).dropna(subset=["close"])
            df = df[df["close"] > 0]
            if len(df) < 100: return None
            return df
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(10 + attempt * 5)
                continue
            return None
        except Exception:
            return None
    return None

print(f"Mulai download {len(SAHAM_IDX)} saham...")
print("="*60)

berhasil = 0
gagal    = 0
gagal_list = []

for i, kode in enumerate(SAHAM_IDX, 1):
    path = f"data/idx500/{kode}.csv"
    # Skip kalau sudah ada dan baru (< 1 hari)
    if os.path.exists(path):
        umur = (datetime.now().timestamp() - os.path.getmtime(path)) / 3600
        if umur < 20:
            berhasil += 1
            if i % 50 == 0:
                print(f"  [{i}/{len(SAHAM_IDX)}] {kode} sudah ada (skip)")
            continue

    df = download_saham(kode)
    if df is not None:
        df.to_csv(path, index=False)
        berhasil += 1
        if i % 20 == 0 or berhasil <= 10:
            harga = float(df["close"].iloc[-1])
            print(f"  [{i}/{len(SAHAM_IDX)}] ✓ {kode}: Rp{harga:,.0f} ({len(df)} hari)")
    else:
        gagal += 1
        gagal_list.append(kode)

    time.sleep(0.5)  # hindari rate limit

print(f"\n{'='*60}")
print(f"SELESAI!")
print(f"  Berhasil : {berhasil} saham")
print(f"  Gagal    : {gagal} saham")
if gagal_list:
    print(f"  Gagal list: {', '.join(gagal_list[:20])}")
print(f"  Folder   : data/idx500/")
print(f"\nLangkah berikutnya: jalankan train_swing.py")
