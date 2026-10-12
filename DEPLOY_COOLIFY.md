# Deploy Private Server ke Coolify (VPS)

Server ini 1 container Python tanpa dependensi. Coolify cukup expose **1 port HTTP**.

## 1. Push ke Git

```bash
cd "ri-private-server"
git init && git add server.py config.json Dockerfile docker-compose.yml .dockerignore
git commit -m "ri private server"
# push ke GitHub/GitLab kamu
```

## 2. Buat service di Coolify

1. Coolify -> New Resource -> **Docker Image / Dockerfile** -> pilih repo di atas, branch main.
2. Build Pack: **Dockerfile**. Port: `8080`.
3. Domain: isi misal `https://ri.kamu.com` (aktifkan HTTPS/Let's Encrypt).
4. Environment variables (wajib):
   ```
   PUBLIC_HOST=ri.kamu.com
   PUBLIC_SCHEME=https
   PORT=8080
   WS_PORT=29601
   WS_PUBLIC_PORT=29601
   DATA_DIR=/data
   ```
5. Persistent Storage: mount volume `/data` (supaya `ri.db` akun tidak hilang tiap redeploy).
6. Deploy. Cek `https://ri.kamu.com/status` harus `{"ok":true,...}` dan `https://ri.kamu.com/` buka GM Panel.

## 3. WebSocket game (2 opsi)

- **Opsi A — tanpa setting tambahan (disarankan):** client yang support `connectByUrl` pakai `wss://ri.kamu.com/ws` (sudah disediakan server, field `ws_url` di server_list).
- **Opsi B — port TCP 29601:** di VPS/Coolify expose juga port `29601` ke container (TCP). Client Egret `connect(host,port)` pakai `ws://ri.kamu.com:29601`. Kalau provider VPS blokir port, pakai opsi A.

## 4. Build APK yang nyambung ke VPS

Di PC (butuh XAPK asli di folder atas):

```bash
python build_apk.py --host ri.kamu.com --scheme https
```

Hasil: `RI-Private-v1.19.apk` (~300MB, URL resmi 0 sisa, sudah mengarah ke VPS).
File belum di-sign (PC tanpa Java):

- **Di HP (termudah):** MT Manager -> klik APK -> Sign -> Install.
- **Di VPS:** upload APK lalu `bash sign_apk.sh RI-Private-v1.19.apk`, download versi `.signed.apk`, install di HP.

Lalu di HP buka `https://ri.kamu.com/status` dulu (pastikan konek), baru buka game -> server **PRIVATE-GRATIS-1** -> jade 999.999.999, shop + topup gratis.
