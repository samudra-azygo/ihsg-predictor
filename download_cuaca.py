"""
download_cuaca.py
Download data cuaca historis 4 negara dari Open-Meteo API
Gratis, tidak perlu API key
"""
import requests, pandas as pd, os, time
from datetime import datetime, timedelta

os.makedirs("data/cuaca", exist_ok=True)

LOKASI = {
    "indonesia": {
        "lat": -1.5, "lon": 113.9,
        "nama": "Kalimantan (pusat sawit)",
        "relevan": ["AALI","SIMP","LSIP","CPO"],
    },
    "australia": {
        "lat": -23.4, "lon": 144.7,
        "nama": "Queensland (pusat coal)",
        "relevan": ["PTBA","ADRO","ITMG","COAL"],
    },
    "brasil": {
        "lat": -12.6, "lon": -55.5,
        "nama": "Mato Grosso (kedelai/jagung)",
        "relevan": ["ICBP","MYOR","CPIN","JPFA","KEDELAI","JAGUNG"],
    },
    "jerman": {
        "lat": 50.1, "lon": 8.7,
        "nama": "Frankfurt (gas/gandum Eropa)",
        "relevan": ["PGAS","GANDUM","OIL"],
    },
}

# Tanggal 3 tahun ke belakang
end_date   = datetime.now().strftime("%Y-%m-%d")
start_date = (datetime.now() - timedelta(days=3*365)).strftime("%Y-%m-%d")

print(f"Download cuaca {start_date} sampai {end_date}")
print("="*50)

semua_df = {}

for negara, info in LOKASI.items():
    try:
        url = (
            f"https://archive-api.open-meteo.com/v1/archive"
            f"?latitude={info['lat']}&longitude={info['lon']}"
            f"&start_date={start_date}&end_date={end_date}"
            f"&daily=temperature_2m_max,temperature_2m_min,"
            f"precipitation_sum,windspeed_10m_max,et0_fao_evapotranspiration"
        )
        r    = requests.get(url, timeout=30)
        data = r.json()

        if "daily" not in data:
            print(f"  GAGAL {negara}: {data.get('reason','unknown')}")
            continue

        daily = data["daily"]
        df    = pd.DataFrame({
            "date"     : daily["time"],
            "suhu_max" : daily["temperature_2m_max"],
            "suhu_min" : daily["temperature_2m_min"],
            "hujan"    : daily["precipitation_sum"],
            "angin"    : daily["windspeed_10m_max"],
            "evap"     : daily["et0_fao_evapotranspiration"],
        })
        df["date"] = pd.to_datetime(df["date"])
        df = df.dropna()

        # Fitur turunan
        df["suhu_range"]   = df["suhu_max"] - df["suhu_min"]
        df["hujan_7d"]     = df["hujan"].rolling(7).sum()
        df["hujan_30d"]    = df["hujan"].rolling(30).sum()
        df["suhu_anomali"] = df["suhu_max"] - df["suhu_max"].rolling(30).mean()
        df["kekeringan"]   = (df["hujan_7d"] < df["hujan_7d"].quantile(0.2)).astype(int)
        df["banjir"]       = (df["hujan"] > df["hujan"].quantile(0.9)).astype(int)

        df.to_csv(f"data/cuaca/CUACA_{negara.upper()}.csv", index=False)

        suhu_rata = df["suhu_max"].mean()
        hujan_rata = df["hujan"].mean()
        print(f"  OK {negara:12s} ({info['nama']})")
        print(f"      {len(df)} hari | suhu rata: {suhu_rata:.1f}C | hujan rata: {hujan_rata:.1f}mm/hari")
        print(f"      Relevan: {', '.join(info['relevan'])}")

        semua_df[negara] = df
        time.sleep(1)

    except Exception as e:
        print(f"  GAGAL {negara}: {e}")

# Gabungkan semua cuaca jadi satu file
print("\nGabungkan semua data cuaca...")
dfs_gabung = []
for negara, df in semua_df.items():
    df2 = df.set_index("date")
    # Rename kolom dengan prefix negara
    fitur = ["suhu_max","hujan","hujan_7d","hujan_30d","suhu_anomali","kekeringan","banjir"]
    df2 = df2[[f for f in fitur if f in df2.columns]]
    df2.columns = [f"{negara}_{c}" for c in df2.columns]
    dfs_gabung.append(df2)

if dfs_gabung:
    gabungan = pd.concat(dfs_gabung, axis=1)
    gabungan.index = gabungan.index.strftime("%Y-%m-%d")
    gabungan.to_csv("data/cuaca/CUACA_GABUNGAN.csv")
    print(f"Selesai! {len(gabungan.columns)} fitur cuaca dari {len(dfs_gabung)} negara")
    print(f"File: data/cuaca/CUACA_GABUNGAN.csv")
    print(gabungan.tail(3).iloc[:, :8].to_string())
else:
    print("Tidak ada data yang berhasil didownload!")
