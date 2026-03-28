"""
download_enso.py
Download data ENSO (El Nino/La Nina) dari NOAA
Gratis, tidak perlu API key
Relevan untuk: agribisnis, konsumer pangan, cuaca ekstrem
"""
import requests
import pandas as pd
import numpy as np
import os
from io import StringIO

os.makedirs("data/enso", exist_ok=True)

# ── 1. Download ONI index ─────────────────────────────────────
print("Download ENSO ONI index...")
r = requests.get(
    "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt",
    headers={"User-Agent":"Mozilla/5.0"}, timeout=15
)

lines = r.text.strip().split("\n")
records = []
for line in lines[1:]:
    parts = line.split()
    if len(parts) >= 4:
        try:
            seas  = parts[0]
            yr    = int(parts[1])
            total = float(parts[2])
            anom  = float(parts[3])

            # Konversi season ke bulan
            seas_map = {
                "DJF":1,"JFM":2,"FMA":3,"MAM":4,"AMJ":5,"MJJ":6,
                "JJA":7,"JAS":8,"ASO":9,"SON":10,"OND":11,"NDJ":12
            }
            bulan = seas_map.get(seas, 1)
            records.append({
                "year": yr, "month": bulan,
                "oni": anom,
                "el_nino": 1 if anom >= 0.5 else 0,
                "la_nina": 1 if anom <= -0.5 else 0,
                "enso_kuat": 1 if abs(anom) >= 1.0 else 0,
            })
        except:
            pass

df_oni = pd.DataFrame(records)
df_oni["date"] = pd.to_datetime(df_oni[["year","month"]].assign(day=1))
df_oni = df_oni.set_index("date").sort_index()
df_oni.to_csv("data/enso/ONI.csv")
print(f"  OK ONI: {len(df_oni)} bulan")
print(f"  El Nino: {df_oni['el_nino'].sum()} bulan")
print(f"  La Nina: {df_oni['la_nina'].sum()} bulan")
print(f"  ONI terakhir: {df_oni['oni'].iloc[-1]:.2f}")

# ── 2. Download SOI index ─────────────────────────────────────
print("\nDownload SOI index...")
r2 = requests.get(
    "https://www.cpc.ncep.noaa.gov/data/indices/soi",
    headers={"User-Agent":"Mozilla/5.0"}, timeout=15
)

lines2 = r2.text.strip().split("\n")
soi_records = []
for line in lines2:
    parts = line.split()
    if len(parts) >= 2:
        try:
            yr = int(parts[0])
            if 1950 <= yr <= 2030:
                for m, val in enumerate(parts[1:13], 1):
                    if val not in ["-99.9","99.9","9999"]:
                        soi_records.append({
                            "year": yr, "month": m,
                            "soi": float(val)
                        })
        except:
            pass

df_soi = pd.DataFrame(soi_records)
if not df_soi.empty:
    df_soi["date"] = pd.to_datetime(df_soi[["year","month"]].assign(day=1))
    df_soi = df_soi.set_index("date").sort_index()
    df_soi.to_csv("data/enso/SOI.csv")
    print(f"  OK SOI: {len(df_soi)} bulan")

# ── 3. Gabungkan dan buat fitur harian ───────────────────────
print("\nBuat fitur ENSO harian...")

# Expand ke harian dengan forward fill
idx_harian = pd.date_range("2022-01-01", "2026-12-31", freq="D")
df_harian  = pd.DataFrame(index=idx_harian)

# Join ONI
oni_cols = ["oni","el_nino","la_nina","enso_kuat"]
df_oni_h = df_oni[oni_cols].reindex(idx_harian, method="ffill")
df_harian = df_harian.join(df_oni_h)

# Join SOI
if not df_soi.empty:
    df_soi_h = df_soi[["soi"]].reindex(idx_harian, method="ffill")
    df_harian = df_harian.join(df_soi_h)

# Fitur turunan
df_harian["oni_lag1m"]   = df_harian["oni"].shift(30)
df_harian["oni_lag3m"]   = df_harian["oni"].shift(90)
df_harian["oni_trend"]   = (df_harian["oni"] > df_harian["oni"].shift(30)).astype(int)
df_harian["enso_phase"]  = df_harian["oni"].apply(
    lambda x: 2 if x >= 1.0 else 1 if x >= 0.5 else -1 if x <= -0.5 else 0
)

# Dampak ke sektor (berdasarkan penelitian historis)
# El Nino = kekeringan Indonesia → CPO turun, beras naik
# La Nina = banjir → coal terganggu, CPO bisa naik
df_harian["dampak_cpo"]    = df_harian["oni"] * -0.3
df_harian["dampak_beras"]  = df_harian["oni"] * 0.2
df_harian["dampak_coal"]   = df_harian["oni"] * -0.1

df_harian = df_harian.dropna(how="all")
df_harian.index = df_harian.index.strftime("%Y-%m-%d")
df_harian.to_csv("data/enso/ENSO_GABUNGAN.csv")

print(f"  Total fitur ENSO: {len(df_harian.columns)}")
print(f"  Periode: {df_harian.index[0]} sampai {df_harian.index[-1]}")
print(f"\nFitur ENSO:")
for col in df_harian.columns:
    print(f"  - {col}")

# ── 4. Status ENSO sekarang ───────────────────────────────────
print("\nSTATUS ENSO SEKARANG:")
oni_terakhir = df_oni["oni"].iloc[-1]
if oni_terakhir >= 1.0:
    status = "EL NINO KUAT"
    dampak = "Kekeringan Indonesia, CPO terancam, beras naik"
elif oni_terakhir >= 0.5:
    status = "EL NINO LEMAH"
    dampak = "Curah hujan berkurang, waspada gagal panen"
elif oni_terakhir <= -1.0:
    status = "LA NINA KUAT"
    dampak = "Banjir Indonesia, coal terganggu, pangan melimpah"
elif oni_terakhir <= -0.5:
    status = "LA NINA LEMAH"
    dampak = "Curah hujan tinggi, waspada banjir"
else:
    status = "NETRAL"
    dampak = "Kondisi cuaca normal"

print(f"  ONI index  : {oni_terakhir:.2f}")
print(f"  Status     : {status}")
print(f"  Dampak     : {dampak}")
print(f"\nFile tersimpan: data/enso/ENSO_GABUNGAN.csv")
