# IHSG Stock Predictor
## Sistem Prediksi & Ranking Saham IDX Berbasis 6 Sumber Data

---

## Struktur File

```
ihsg_predictor/
├── config.py               # Semua konfigurasi sistem
├── data_collector.py       # Pengumpulan 6 sumber data
├── feature_engineering.py  # Indikator teknikal & filter
├── model.py                # Training, scoring, backtesting
├── risk_manager.py         # Market regime, risiko, retrain
├── main_pipeline.py        # Pipeline operasional harian
└── README.md
```

---

## Instalasi

```bash
pip install pandas numpy scikit-learn requests beautifulsoup4
pip install yfinance xgboost hijri-converter
```

---

## Cara Pakai

### 1. Training awal (lakukan sekali)
```bash
# Kumpulkan data historis dulu
python main_pipeline.py --fase kumpul_data

# Latih model dari data historis 3 tahun
python main_pipeline.py --fase training

# Validasi dengan backtesting
python main_pipeline.py --fase backtesting
```

### 2. Operasional harian

```bash
# 04:00 — Kumpul data semalam
python main_pipeline.py --fase kumpul_data

# 06:00 — Hitung scoring 800+ saham
python main_pipeline.py --fase scoring

# 08:00 — Cek lampu & siapkan order
python main_pipeline.py --fase cek_lampu --modal 100000000 --vix 15.0

# 15:30 — Evaluasi setelah BEI tutup
python main_pipeline.py --fase evaluasi
```

### 3. Jalankan semua sekaligus (untuk testing)
```bash
python main_pipeline.py --fase semua --modal 100000000
```

---

## Automasi dengan Cron (Linux/Mac)

```bash
# Edit crontab
crontab -e

# Tambahkan jadwal:
0 4  * * 1-5  cd /path/to/ihsg_predictor && python main_pipeline.py --fase kumpul_data
0 6  * * 1-5  cd /path/to/ihsg_predictor && python main_pipeline.py --fase scoring
0 8  * * 1-5  cd /path/to/ihsg_predictor && python main_pipeline.py --fase cek_lampu
30 15 * * 1-5 cd /path/to/ihsg_predictor && python main_pipeline.py --fase evaluasi
```

---

## Konfigurasi Penting (config.py)

| Parameter | Default | Keterangan |
|---|---|---|
| `take_profit_pct` | 2.0% | Target profit per trade |
| `stop_loss_pct` | -1.0% | Batas loss per trade |
| `max_posisi` | 5 | Maks saham sekaligus |
| `min_kas_pct` | 20% | Cadangan kas minimum |
| `vix_merah` | 30 | VIX threshold lampu merah |
| `akurasi_min_hijau` | 60% | Akurasi min untuk trading |
| `drift_threshold` | 50% | Trigger retrain darurat |

---

## Sumber Data yang Dibutuhkan

| Sumber | API/Library | Gratis? |
|---|---|---|
| Harga saham OHLCV | yfinance | ✅ Gratis |
| Cuaca Jakarta | open-meteo.com | ✅ Gratis |
| Kalender Hijriah | hijri-converter | ✅ Gratis |
| Berita sentimen | beautifulsoup4 (scraping) | ✅ Gratis |
| Komoditas global | yfinance / Trading Economics | ⚠️ Sebagian berbayar |
| Foreign flow BEI | IDX API / RTI Business | ⚠️ Berbayar |

---

## Output Sistem

```
── TOP 10 SAHAM HARI INI ──

rank ticker  skor_total sinyal     skor_sd  skor_teknikal skor_komoditas
   1 ADRO        88.2   BELI KUAT    91.0         82.0           95.0
   2 BBRI        82.5   BELI KUAT    85.0         79.0           45.0
   3 INCO        79.1   BELI KUAT    76.0         74.0           88.0
   4 TLKM        61.3   PANTAU       55.0         68.0           40.0

LAMPU: HIJAU
Aksi : Trading normal · ambil Top 5 · posisi penuh

── ORDER SIAP HARI INI (3 saham) ──
  BUY ADRO     | Skor: 88 | Alokasi: Rp 20.0jt | TP: +2.0% | SL: -1.0%
  BUY BBRI     | Skor: 82 | Alokasi: Rp 20.0jt | TP: +2.0% | SL: -1.0%
  BUY INCO     | Skor: 79 | Alokasi: Rp 15.0jt | TP: +2.0% | SL: -1.0%
```

---

## Filosofi Sistem

- **Small gains konsisten** — target +1.5–3% per trade, bukan +20%
- **Stop loss wajib** — dipasang sebelum beli, tidak bisa dinegosiasi
- **Diam adalah posisi** — lampu merah = tidak trading, modal aman
- **Model belajar sendiri** — bobot ditentukan data, bukan tebakan
- **Retrain berkala** — model diperbarui setiap bulan atau saat drift
# force Thu Mar 26 05:09:32 WIB 2026
