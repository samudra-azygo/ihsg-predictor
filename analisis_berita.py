"""
analisis_berita.py
Analisis sentimen berita saham IDX dari:
- IDX Channel
- CNBC Indonesia  
- Detik Finance
"""
import requests
from xml.etree import ElementTree as ET
import pandas as pd
import os
from datetime import datetime

os.makedirs("data/berita", exist_ok=True)

# ── Kamus sentimen ────────────────────────────────────────────
POSITIF = [
    "naik","tumbuh","meningkat","rekor","laba","untung","dividen",
    "kontrak","ekspansi","investasi","rally","bullish","profit",
    "surplus","optimis","pulih","menguat","solid","positif",
    "minyak naik","crude naik","coal naik","emas naik","gold naik",
    "harga minyak","harga emas","harga batu bara","harga coal",
    "energy rally","komoditas naik","windfall","supercycle",
    "akuisisi","right issue","buyback","stock split","dividen naik",
    "laba naik","pendapatan naik","pertumbuhan","ekspor naik",
]
NEGATIF = [
    "turun","merosot","anjlok","rugi","kerugian","bangkrut",
    "suspensi","delisting","gagal","default","korupsi","kasus",
    "bearish","tekanan","krisis","resesi","perang","bencana",
    "tersangka","penyidikan","sanksi","pembekuan",
    "perang","serangan","rudal","bom","militer","konflik",
    "Iran","Israel","Hormuz","blokade","eskalasi","invasi",
    "geopolitik","ketegangan","ancaman","embargo",
    "inflasi tinggi","stagflasi","resesi global","PHK massal",
    "bangkrut","pailit","gagal bayar","kredit macet",
    "banjir","gempa","tsunami","kebakaran hutan","kekeringan",
]

# ── Daftar saham IDX ──────────────────────────────────────────
SAHAM = [
    "BBCA","BBRI","BMRI","BBNI","BRIS","BNGA","BBTN","ARTO","PNBN",
    "TLKM","EXCL","ISAT","TOWR","MTEL","TBIG","LINK",
    "ADRO","PTBA","ITMG","INCO","ANTM","TINS","MEDC","HRUM","MDKA",
    "UNVR","ICBP","MYOR","KLBF","KAEF","CPIN","SIDO","GGRM","HMSP",
    "AALI","SIMP","LSIP",
    "ASII","AUTO","SMSM","UNTR",
    "SMGR","INTP","WIKA","PTPP","WSKT","ADHI",
    "GOTO","EMTK","BUKA","DMMX",
    "AKRA","PGAS","ESSA","ELSA",
    "SMRA","BSDE","CTRA","PWON","LPKR",
    "ACES","MAPI","LPPF","RALS",
    "MIKA","SILO","HEAL",
    "SCMA","MNCN",
]

# Sektor per saham
SEKTOR_SAHAM = {
    "BBCA":"perbankan","BBRI":"perbankan","BMRI":"perbankan","BBNI":"perbankan",
    "BRIS":"perbankan","BNGA":"perbankan","BBTN":"perbankan","PNBN":"perbankan",
    "TLKM":"telekomunikasi","EXCL":"telekomunikasi","ISAT":"telekomunikasi",
    "ADRO":"tambang","PTBA":"tambang","ITMG":"tambang","ANTM":"tambang",
    "INCO":"tambang","TINS":"tambang","MEDC":"tambang","HRUM":"tambang",
    "UNVR":"konsumer","ICBP":"konsumer","MYOR":"konsumer","KLBF":"konsumer",
    "CPIN":"konsumer","GGRM":"konsumer","HMSP":"konsumer",
    "AALI":"agribisnis","SIMP":"agribisnis","LSIP":"agribisnis",
    "SMGR":"properti","BSDE":"properti","CTRA":"properti","PWON":"properti",
    "MIKA":"kesehatan","SILO":"kesehatan","HEAL":"kesehatan",
    "PGAS":"energi","AKRA":"energi","ESSA":"energi",
    "SCMA":"media","MNCN":"media","EMTK":"media",
    "ACES":"ritel","MAPI":"ritel","LPPF":"ritel","RALS":"ritel",
}

# ── Ambil berita ──────────────────────────────────────────────
SUMBER = {
    "IDX Channel"   : "https://www.idxchannel.com/rss",
    "CNBC Indonesia": "https://www.cnbcindonesia.com/rss",
    "Detik Finance" : "https://finance.detik.com/rss",
}

print("Ambil berita terbaru...")
print("="*60)

semua_berita = []
for nama_sumber, url in SUMBER.items():
    try:
        r    = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
        root = ET.fromstring(r.text)
        items = root.findall(".//item")
        print(f"  {nama_sumber}: {len(items)} berita")
        for item in items:
            judul   = item.find("title")
            tanggal = item.find("pubDate")
            link    = item.find("link")
            if judul is None:
                continue
            teks = judul.text.upper()
            skor = 0
            for k in POSITIF:
                if k.upper() in teks:
                    skor += 1
            for k in NEGATIF:
                if k.upper() in teks:
                    skor -= 1
            saham_disebut = [s for s in SAHAM if s in teks]
            semua_berita.append({
                "judul"  : judul.text,
                "sumber" : nama_sumber,
                "tanggal": tanggal.text[:30] if tanggal is not None else "",
                "skor"   : skor,
                "saham"  : ",".join(saham_disebut),
                "link"   : link.text if link is not None else "",
            })
    except Exception as e:
        print(f"  ERROR {nama_sumber}: {e}")

df = pd.DataFrame(semua_berita)
df.to_csv("data/berita/berita_hari_ini.csv", index=False)
print(f"\nTotal: {len(df)} berita dari {df['sumber'].nunique()} sumber")

# ── Ringkasan sentimen ────────────────────────────────────────
print("\nRINGKASAN SENTIMEN:")
print(f"  Positif  : {len(df[df['skor']>0])} berita")
print(f"  Negatif  : {len(df[df['skor']<0])} berita")
print(f"  Netral   : {len(df[df['skor']==0])} berita")
print(f"  Skor rata: {df['skor'].mean():.2f}")

# ── Berita positif terkuat ────────────────────────────────────
print("\nBERITA POSITIF TERKUAT:")
top_pos = df[df['skor']>0].nlargest(5,'skor')
for _, r in top_pos.iterrows():
    print(f"  +{r['skor']} [{r['sumber']}] {r['judul'][:65]}")
    if r['saham']:
        print(f"     Saham: {r['saham']}")

# ── Berita negatif terkuat ────────────────────────────────────
print("\nBERITA NEGATIF TERKUAT:")
top_neg = df[df['skor']<0].nsmallest(5,'skor')
for _, r in top_neg.iterrows():
    print(f"  {r['skor']} [{r['sumber']}] {r['judul'][:65]}")
    if r['saham']:
        print(f"     Saham: {r['saham']}")

# ── Skor per saham ────────────────────────────────────────────
print("\nSAHAM YANG DISEBUT HARI INI:")
skor_saham = {}
for _, row in df[df['saham']!=''].iterrows():
    for s in row['saham'].split(','):
        if s:
            skor_saham[s] = skor_saham.get(s, 0) + row['skor']

if skor_saham:
    for s, skor in sorted(skor_saham.items(), key=lambda x: -x[1]):
        sektor = SEKTOR_SAHAM.get(s, "lainnya")
        label  = "POSITIF" if skor > 0 else "NEGATIF" if skor < 0 else "NETRAL"
        print(f"  {s:6s} | {skor:+2d} | {label:8s} | {sektor}")
else:
    print("  Tidak ada saham spesifik yang disebut")

# ── Skor per sektor ───────────────────────────────────────────
print("\nSENTIMEN PER SEKTOR:")
skor_sektor = {}
for s, skor in skor_saham.items():
    sektor = SEKTOR_SAHAM.get(s, "lainnya")
    skor_sektor[sektor] = skor_sektor.get(sektor, 0) + skor

for sektor, skor in sorted(skor_sektor.items(), key=lambda x: -x[1]):
    bar  = "+" * abs(skor) if skor > 0 else "-" * abs(skor)
    print(f"  {sektor:15s} | {skor:+2d} | {bar}")

# ── Simpan skor harian ────────────────────────────────────────
tanggal = datetime.now().strftime("%Y-%m-%d")
skor_df = pd.DataFrame([
    {"tanggal": tanggal, "saham": s, "skor_berita": v}
    for s, v in skor_saham.items()
])
if not skor_df.empty:
    skor_df.to_csv(f"data/berita/skor_{tanggal}.csv", index=False)
    print(f"\nSkor tersimpan: data/berita/skor_{tanggal}.csv")

skor_global = df['skor'].sum()
print(f"\nSKOR GLOBAL PASAR: {skor_global:+d}")
if skor_global > 3:
    print("Sentimen: POSITIF - kondisi berita mendukung kenaikan")
elif skor_global < -3:
    print("Sentimen: NEGATIF - kondisi berita menekan pasar")
else:
    print("Sentimen: NETRAL - tidak ada sinyal kuat dari berita")
