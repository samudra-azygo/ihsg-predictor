"""
buat_kalender_lengkap.py
Kalender lengkap untuk model IHSG dengan skor berbobot:
- Libur Islam diberi bobot lebih tinggi (mayoritas penduduk Indonesia)
- Libur nasional lainnya bobot sedang
- Efek musiman (window dressing, January effect, dll)
"""
import pandas as pd
import numpy as np
import os

os.makedirs("data/enso", exist_ok=True)

BOBOT = {
    "lebaran"           : 1.0,
    "lebaran_cuti"      : 0.9,
    "pra_lebaran"       : 0.8,
    "ramadan"           : 0.5,
    "idul_adha"         : 0.8,
    "isra_miraj"        : 0.6,
    "maulid_nabi"       : 0.6,
    "tahun_baru_hijriah": 0.5,
    "natal"             : 0.7,
    "natal_cuti"        : 0.6,
    "wafat_yesus"       : 0.5,
    "kenaikan_yesus"    : 0.4,
    "waisak"            : 0.3,
    "nyepi"             : 0.4,
    "tahun_baru"        : 0.7,
    "imlek"             : 0.5,
    "kemerdekaan"       : 0.6,
    "may_day"           : 0.4,
    "pancasila"         : 0.3,
}

LIBUR_NASIONAL = {
    "2022-01-01":"tahun_baru","2022-02-01":"imlek","2022-03-03":"isra_miraj",
    "2022-04-15":"wafat_yesus","2022-05-01":"lebaran","2022-05-02":"lebaran",
    "2022-05-03":"lebaran","2022-05-16":"waisak","2022-05-26":"kenaikan_yesus",
    "2022-06-01":"pancasila","2022-07-10":"idul_adha","2022-07-30":"tahun_baru_hijriah",
    "2022-08-17":"kemerdekaan","2022-10-08":"maulid_nabi","2022-12-25":"natal","2022-12-26":"natal_cuti",
    "2023-01-01":"tahun_baru","2023-01-22":"imlek","2023-02-18":"isra_miraj",
    "2023-03-22":"nyepi","2023-04-07":"wafat_yesus","2023-04-22":"lebaran",
    "2023-04-23":"lebaran","2023-04-24":"lebaran","2023-04-25":"lebaran_cuti",
    "2023-05-01":"may_day","2023-05-18":"kenaikan_yesus","2023-05-24":"waisak",
    "2023-06-01":"pancasila","2023-06-29":"idul_adha","2023-07-19":"tahun_baru_hijriah",
    "2023-08-17":"kemerdekaan","2023-09-28":"maulid_nabi","2023-12-25":"natal","2023-12-26":"natal_cuti",
    "2024-01-01":"tahun_baru","2024-02-08":"imlek","2024-02-14":"isra_miraj",
    "2024-03-11":"nyepi","2024-03-29":"wafat_yesus","2024-04-10":"lebaran",
    "2024-04-11":"lebaran","2024-04-12":"lebaran","2024-04-15":"lebaran_cuti",
    "2024-05-01":"may_day","2024-05-09":"kenaikan_yesus","2024-05-23":"waisak",
    "2024-06-01":"pancasila","2024-06-17":"idul_adha","2024-07-07":"tahun_baru_hijriah",
    "2024-08-17":"kemerdekaan","2024-09-16":"maulid_nabi","2024-12-25":"natal","2024-12-26":"natal_cuti",
    "2025-01-01":"tahun_baru","2025-01-27":"isra_miraj","2025-01-29":"imlek",
    "2025-03-28":"nyepi","2025-03-31":"lebaran","2025-04-01":"lebaran",
    "2025-04-02":"lebaran","2025-04-03":"lebaran_cuti","2025-04-04":"lebaran_cuti",
    "2025-04-18":"wafat_yesus","2025-05-01":"may_day","2025-05-12":"waisak",
    "2025-05-29":"kenaikan_yesus","2025-06-01":"pancasila","2025-06-06":"idul_adha",
    "2025-06-27":"tahun_baru_hijriah","2025-08-17":"kemerdekaan","2025-09-05":"maulid_nabi",
    "2025-12-25":"natal","2025-12-26":"natal_cuti",
    "2026-01-01":"tahun_baru","2026-01-17":"isra_miraj","2026-02-17":"imlek",
    "2026-03-17":"nyepi","2026-03-20":"lebaran","2026-03-21":"lebaran",
    "2026-03-22":"lebaran","2026-03-23":"lebaran_cuti","2026-04-03":"wafat_yesus",
    "2026-05-01":"may_day","2026-05-14":"kenaikan_yesus","2026-05-26":"idul_adha",
    "2026-05-31":"waisak","2026-06-01":"pancasila","2026-06-16":"tahun_baru_hijriah",
    "2026-08-17":"kemerdekaan","2026-08-25":"maulid_nabi","2026-12-25":"natal","2026-12-26":"natal_cuti",
}

LIBUR_ISLAM   = ["lebaran","lebaran_cuti","idul_adha","isra_miraj","maulid_nabi","tahun_baru_hijriah"]
LIBUR_KRISTEN = ["natal","natal_cuti","wafat_yesus","kenaikan_yesus"]

idx = pd.date_range("2022-01-01", "2026-12-31", freq="D")
df  = pd.DataFrame(index=idx)

df["bulan"]       = df.index.month
df["kuartal"]     = df.index.quarter
df["hari_minggu"] = df.index.dayofweek
df["hari_tahun"]  = df.index.dayofyear
df["is_weekend"]  = (df["hari_minggu"] >= 5).astype(int)
df["is_libur"]          = 0
df["is_libur_islam"]    = 0
df["is_libur_kristen"]  = 0
df["is_libur_lain"]     = 0
df["bobot_libur"]       = 0.0

for tgl, nama in LIBUR_NASIONAL.items():
    try:
        t = pd.Timestamp(tgl)
        if t in df.index:
            bobot = BOBOT.get(nama, 0.3)
            df.loc[t, "is_libur"]    = 1
            df.loc[t, "bobot_libur"] = bobot
            if nama in LIBUR_ISLAM:
                df.loc[t, "is_libur_islam"]   = 1
            elif nama in LIBUR_KRISTEN:
                df.loc[t, "is_libur_kristen"] = 1
            else:
                df.loc[t, "is_libur_lain"]    = 1
    except:
        pass

df["is_trading"] = ((df["is_weekend"] == 0) & (df["is_libur"] == 0)).astype(int)

df["is_ramadan"]    = 0
df["is_lebaran"]    = 0
df["pra_lebaran"]   = 0
df["pasca_lebaran"] = 0

ramadan_dates = {
    "2022":("2022-04-02","2022-04-30"),"2023":("2023-03-23","2023-04-21"),
    "2024":("2024-03-11","2024-04-09"),"2025":("2025-03-01","2025-03-30"),
    "2026":("2026-02-18","2026-03-19"),
}
lebaran_dates = {
    "2022":("2022-05-01","2022-05-03"),"2023":("2023-04-22","2023-04-25"),
    "2024":("2024-04-10","2024-04-15"),"2025":("2025-03-31","2025-04-04"),
    "2026":("2026-03-20","2026-03-23"),
}

for yr in ramadan_dates:
    r_start = pd.Timestamp(ramadan_dates[yr][0])
    r_end   = pd.Timestamp(ramadan_dates[yr][1])
    l_start = pd.Timestamp(lebaran_dates[yr][0])
    l_end   = pd.Timestamp(lebaran_dates[yr][1])
    df.loc[r_start:r_end, "is_ramadan"]  = 1
    df.loc[l_start:l_end, "is_lebaran"]  = 1
    df.loc[r_end-pd.Timedelta(days=6):r_end, "pra_lebaran"] = 1
    df.loc[l_end+pd.Timedelta(days=1):l_end+pd.Timedelta(days=14), "pasca_lebaran"] = 1

df["window_dressing"] = ((df["bulan"] == 12) & (df.index.day >= 15)).astype(int)
df["january_effect"]  = ((df["bulan"] == 1)  & (df.index.day <= 15)).astype(int)
df["akhir_kuartal"]   = (df["bulan"].isin([3,6,9,12]) & (df.index.day >= 25)).astype(int)
df["awal_kuartal"]    = (df["bulan"].isin([1,4,7,10]) & (df.index.day <= 5)).astype(int)
df["pra_libur"]       = df["is_libur"].shift(-1).fillna(0).astype(int)

df["dampak_ritel"] = (
    df["is_ramadan"]    * 0.6 +
    df["pra_lebaran"]   * 1.2 +
    df["is_lebaran"]    * 0.8 +
    df["pasca_lebaran"] * (-0.4)
)
df["dampak_konsumer"] = (
    df["is_ramadan"]    * 0.5 +
    df["pra_lebaran"]   * 1.0 +
    df["pasca_lebaran"] * (-0.3)
)
df["dampak_perbankan"] = (
    df["window_dressing"] * 0.3 +
    df["january_effect"]  * 0.4 +
    df["akhir_kuartal"]   * 0.2 +
    df["is_libur_islam"]  * (-0.2)
)
df["dampak_semua"] = (
    df["window_dressing"] * 0.3 +
    df["january_effect"]  * 0.2 +
    df["bobot_libur"]     * (-0.6) +
    df["pra_libur"]       * (-0.2)
)

df.index = df.index.strftime("%Y-%m-%d")
df.to_csv("data/enso/KALENDER.csv")

print(f"Selesai: {len(df.columns)} fitur kalender")
print(f"\nBobot libur (makin tinggi = makin sepi pasarnya):")
print(f"  Lebaran         : {BOBOT['lebaran']:.1f} --- tertinggi")
print(f"  Idul Adha       : {BOBOT['idul_adha']:.1f} ---")
print(f"  Isra Miraj      : {BOBOT['isra_miraj']:.1f} --")
print(f"  Maulid Nabi     : {BOBOT['maulid_nabi']:.1f} --")
print(f"  Tahun Baru H    : {BOBOT['tahun_baru_hijriah']:.1f} -")
print(f"  Natal           : {BOBOT['natal']:.1f} --")
print(f"  Tahun Baru      : {BOBOT['tahun_baru']:.1f} --")
print(f"  Kemerdekaan     : {BOBOT['kemerdekaan']:.1f} --")
print(f"  Waisak          : {BOBOT['waisak']:.1f} -")
print(f"  Pancasila       : {BOBOT['pancasila']:.1f} - terendah")

if "2026-03-28" in df.index:
    h = df.loc["2026-03-28"]
    print(f"\nStatus 28 Mar 2026:")
    print(f"  Is trading    : {int(h['is_trading'])}")
    print(f"  Pasca lebaran : {int(h['pasca_lebaran'])}")
    print(f"  Dampak ritel  : {h['dampak_ritel']:.2f}")

libur_2026 = df[(df.index.str.startswith("2026")) & (df["is_libur"] == "1" if False else df["is_libur"] == 1)]
print(f"\nTotal libur 2026: {len(libur_2026)} hari")
print(f"File: data/enso/KALENDER.csv")
