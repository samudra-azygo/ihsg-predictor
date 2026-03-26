"""
update_sentimen_perang.py
Update kamus sentimen di main.py dengan kata kunci perang Iran-Amerika
dan sinyal positif untuk sektor energi/tambang
"""

import re

# Baca main.py
with open("main.py", "r") as f:
    isi = f.read()

# Kamus baru yang lebih lengkap
POSITIF_BARU = """POSITIF = [
    "naik","tumbuh","meningkat","rekor","laba","untung","dividen",
    "kontrak","ekspansi","investasi","rally","bullish","profit",
    "surplus","optimis","pulih","menguat","solid","positif",
    "minyak naik","crude naik","coal naik","emas naik","gold naik",
    "harga minyak","harga emas","harga batu bara","harga coal",
    "energy rally","komoditas naik","windfall","supercycle",
    "akuisisi","right issue","buyback","stock split","dividen naik",
    "laba naik","pendapatan naik","pertumbuhan","ekspor naik",
]"""

NEGATIF_BARU = """NEGATIF = [
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
]"""

# Ganti kamus di main.py
isi_baru = re.sub(
    r'POSITIF = \[.*?\]',
    POSITIF_BARU,
    isi,
    flags=re.DOTALL
)
isi_baru = re.sub(
    r'NEGATIF = \[.*?\]',
    NEGATIF_BARU,
    isi_baru,
    flags=re.DOTALL
)

# Simpan
with open("main.py", "w") as f:
    f.write(isi_baru)

print("main.py berhasil diupdate")
print("Kata kunci baru:")
print("  POSITIF: minyak naik, coal naik, emas naik, energy rally...")
print("  NEGATIF: perang, Iran, Hormuz, rudal, embargo, sanksi...")

# Update juga analisis_berita.py kalau ada
import os
if os.path.exists("analisis_berita.py"):
    with open("analisis_berita.py", "r") as f:
        isi2 = f.read()
    isi2_baru = re.sub(
        r'POSITIF = \[.*?\]',
        POSITIF_BARU,
        isi2,
        flags=re.DOTALL
    )
    isi2_baru = re.sub(
        r'NEGATIF = \[.*?\]',
        NEGATIF_BARU,
        isi2_baru,
        flags=re.DOTALL
    )
    with open("analisis_berita.py", "w") as f:
        f.write(isi2_baru)
    print("analisis_berita.py berhasil diupdate")

# Test langsung
print("\nTest analisis berita dengan kamus baru...")
import requests
from xml.etree import ElementTree as ET

# Load kamus baru
exec(POSITIF_BARU)
exec(NEGATIF_BARU)

sumber = {
    "IDX"  : "https://www.idxchannel.com/rss",
    "CNBC" : "https://www.cnbcindonesia.com/rss",
    "Detik": "https://finance.detik.com/rss",
}

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
            if skor >= 2:
                berita_pos.append(f"+{skor} [{nama}] {judul.text[:60]}")
            elif skor <= -2:
                berita_neg.append(f"{skor} [{nama}] {judul.text[:60]}")
    except:
        pass

print(f"\nSkor global pasar: {skor_global:+d}")
if skor_global > 3:
    print("Sentimen: POSITIF")
elif skor_global < -3:
    print("Sentimen: NEGATIF")
else:
    print("Sentimen: NETRAL")

print(f"\nBerita NEGATIF terkuat (perang/krisis):")
for b in berita_neg[:5]:
    print(f"  {b}")

print(f"\nBerita POSITIF terkuat (energi/komoditas):")
for b in berita_pos[:5]:
    print(f"  {b}")
