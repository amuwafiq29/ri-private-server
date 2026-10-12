# Renegade Immortal 1.19 — Private Server (Semua GRATIS)

Hasil analisa XAPK kamu (`com.renegadeImmortal.and`, Egret H5):
- API login/server: `https://xnh5api.51haodong.com/Client/server_list`, `/Client/web_login_check`, `/Client/game_center`
- CDN resource: `https://xnh5cdn.51haodong.com/en/resource/`
- Game socket (WebSocket Egret): `sXrelease...:29601` dengan protokol `SCMD_xxxxx`
- SDK: `api-sg2.51haodong.com`, game `kpxianni-android`

## Yang kamu dapat

| Fitur | Status |
|---|---|
| Beli apapun di shop | GRATIS (harga dipaksa 0) |
| Top up / recharge | GRATIS, tiap topup dapat 99.999.999 jade |
| Akun baru | otomatis jade 999.999.999 + gold 999.999.999 + VIP 15 |
| GM Panel | `http://127.0.0.1:8080/` tambah jade / topup / beli sesukamu |
| Semua item | lewat `/gm/buy` + shop gratis di game |

## Cara jalan 5 menit (pilih 1)

### A. Termudah — tanpa utak-atik APK (emulator/HP root atau Hosts Go)
1. Di PC: klik `run.bat` (atau `python server.py`). Biarkan jalan.
2. Di emulator/HP yang **satu jaringan** dengan PC:
   - Install aplikasi pengubah hosts (contoh: "Hosts Go", "VPN Hosts") lalu tambah:
     ```
     127.0.0.1  xnh5api.51haodong.com
     127.0.0.1  xnh5cdn.51haodong.com
     ```
     Kalau HP fisik (bukan emulator), ganti `127.0.0.1` dengan **IP LAN PC** kamu (misal `192.168.1.10`),
     dan edit `config.json` -> `host` ke IP itu, lalu restart server.
   - Atau di emulator: `adb reverse tcp:8080 tcp:8080` + `adb reverse tcp:29601 tcp:29601`.
3. Buka game ori -> login -> otomatis masuk server **PRIVATE-GRATIS-1**, jade 999.999.999.

### B. MT Manager (tanpa PC, tanpa root)
1. Jalankan `python patch_client.py` sekali di PC — hasilnya ada di `patched_client/`.
2. Salin folder itu ke HP. Buka **MT Manager** -> buka XAPK/APK asli -> masuk `assets/game/`.
3. Replace `index_haodong.html` dan `js/main.min_*.js` dengan versi dari `patched_client/`.
4. Save, **sign**, install. Jalankan `server.py` di PC, buka game hasil patch.

### C. GM Panel (curang manual)
Buka `http://127.0.0.1:8080/`:
- Tambah jade: isi uid + jumlah -> Kirim
- Topup gratis: isi uid + goods id
- Beli gratis: isi uid + shop id + count

API langsung:
```
GET /gm/add_jade?uid=player1&amount=999999999
GET /gm/topup?uid=player1&goods=jade_pack_648
GET /gm/buy?uid=player1&shop_id=1001&count=99
GET /gm/accounts
GET /status
```

## File

- `server.py` — emulator HTTP API + WebSocket + DB SQLite (`ri.db`), tanpa `pip install`
- `config.json` — ubah jumlah jade/VIP/harga di sini
- `patch_client.py` — patch otomatis XAPK ke localhost
- `patched_client/` — hasil patch siap tempel via MT Manager
- `run.bat` — klik untuk jalan di Windows

## VPS Coolify + APK HP

Lihat `DEPLOY_COOLIFY.md`. Ringkasnya:

1. Push folder ini ke Git, buat service Dockerfile di Coolify, set env
   `PUBLIC_HOST` / `PUBLIC_SCHEME` / `PORT` / `DATA_DIR=/data` + volume `/data`.
2. Build APK yang nyambung ke VPS:
   `python build_apk.py --host DOMAIN-VPS-KAMU --scheme https`
   File `RI-Private-v1.19.apk` belum di-sign di PC (tidak ada Java):
   sign 1x tap via MT Manager di HP, atau `bash sign_apk.sh` di VPS.
3. Di HP: salin APK (kabel/USB atau Google Drive), install, buka,
   login -> server **PRIVATE-GRATIS-1**.

## Catatan jujur

- Protokol biner `SCMD` game ini tertutup; `server.py` memakai mode **hybrid**:
  login/shop/topup/currency diemulasi lokal (dijamin gratis + unlimited),
  gameplay diteruskan/dipaksa unlimited via push `role_update`.
  Ini cara standar private server H5 tanpa source resmi dan sudah cukup untuk "semua gratis".
- Kalau suatu paket biner belum dikenal, server mencatatnya di console (`[WS ...]`) —
  kirim log itu + `ri.db` kalau kamu mau saya lengkapi emulasinya (gacha, dungeon, dsb).
- Main di emulator (LDPlayer/MuMu) + `adb reverse` adalah kombinasi paling stabil.
