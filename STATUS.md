# IHSG Predictor Bot — Status Update (9 April 2026)

## Info Bot
- Bot Telegram: @axygoz_bot
- Railway: airy-playfulness/production
- GitHub: https://github.com/samudra-azygo/ihsg-predictor
- Token: 8744135725:AAEv4foDXkJVogWJqr4d_xeICJ0dL64en-8
- TELEGRAM_CHAT_ID: 828736755

## Jadwal Railway (UTC → WIB)
- 21:00 UTC = 04:00 WIB → swing_scanner() kirim sinyal + tombol
- 00:00 UTC = 07:00 WIB → brain v3 training_loop()
- 01:00 UTC = 08:00 WIB → download_data()
- 01:15 UTC = 08:15 WIB → scoring_harian()
- 08:30 UTC = 15:30 WIB → evaluasi()
- 15:00 UTC = 22:00 WIB → kirim_laporan()

## Model
- model_swing.pkl: GradientBoosting CV=64.81% target 1-3 hari
- models_latest.pkl: RF-Deep CV=61.41% scoring biasa
- model_rebound.pkl: mode krisis BEAR
- Backtest: win rate 71.2%, avg return +9.71%, 730 trade

## File Utama
- main.py: bot + jadwal + tombol konfirmasi BELI/SKIP
- brain.py: v3, swing 1-3 hari + uji korelasi + data Indonesia
- scoring_improved.py: 60 saham + mode krisis rebound
- scoring_swing.py: swing scanner 345 saham IDX
- download_idx500.py: download 345 saham
- train_swing.py: training model swing
- backtest_swing.py: backtest model

## Brain v3
- Fokus 100% swing 1-3 hari (model 20 hari dinonaktifkan)
- 12 sumber data Indonesia: IHSG, CPO, batubara, nikel, emas, brent, VIX, SP500, USD/IDR, Asia, USBond, DXY
- Uji korelasi otomatis tiap hari (Pearson + Spearman)
- 5 strategi: GB-Fast, GB-Deep, GB-ManyTrees, RF-Balanced, RF-Deep
- Target CV: 70%

## Korelasi Signifikan (top)
- Volatilitas_10hr: r=+0.1357 (TERKUAT)
- Volatilitas_5hr: r=+0.1169
- Dekat_high20: r=-0.0610
- BB_di_bawah_lower: r=+0.0436
- TIDAK signifikan: MACD_cross, Golden_cross, Pola_Hammer, Breakout

## Tombol Konfirmasi Telegram
- 04:00 WIB bot kirim sinyal + tombol BELI/SKIP
- User tap tombol → bot catat di logs/posisi_aktif.json
- User beli manual di aplikasi sekuritas
- Sinyal jual: tombol JUAL/TAHAN
- Command: /cekposisi

## Auto Trading
- Semua sekuritas Indonesia BELUM punya API publik
- Mirae: sedang disidik OJK Maret 2026
- Solusi: tombol konfirmasi Telegram + manual

## TODO
- Fitur stop loss monitor tiap 30 menit jam bursa
- Target CV brain v3: 70%
- Tunggu sekuritas buka API
