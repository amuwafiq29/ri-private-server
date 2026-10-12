#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patcher client Renegade Immortal 1.19 -> arahkan ke private server lokal.
- Ambil XAPK, extract base APK + asset pack
- Patch assets/game/index_haodong.html (resPath -> http://127.0.0.1:8080/resource/)
- Patch assets/game/js/main.min_*.js (ganti https://xnh5api.51haodong.com -> http://127.0.0.1:8080)
- Salin hasil ke patched_client/ siap repack (apktool / MT Manager / manual zip)
Standar lib saja.
"""
import os, sys, json, shutil, zipfile, glob

HERE = os.path.dirname(os.path.abspath(__file__))
WS_ROOT = os.path.dirname(HERE)
XAPK = os.path.join(WS_ROOT, "Renegade+Immortal_1.19_APKPure.xapk")
OUT = os.path.join(HERE, "patched_client")
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
LOCAL_HTTP = f"http://{CFG.get('host','127.0.0.1')}:{CFG.get('http_port',8080)}"

OFFICIAL_APIS = ["https://xnh5api.51haodong.com", "https://xnh5api2.btshidai.com",
    "https://xnh5api5.btshidai.com", "https://xnh5api.mcjdhjj.com",
    "https://xnh5api.rongrongnet.com"]
OFFICIAL_CDNS = ["https://xnh5cdn.51haodong.com/en/resource/", "https://xnh5cdn.51haodong.com/",
    "https://xnh5cdn3.btshidai.com/xiwan", "https://xnh5cdn.btshidai.com/banshu",
    "https://xnh5cdn.rongrongnet.com/xiwan", "https://xnh5release.mcjdhjj.com"]

def patch_text(data: bytes):
    t = data.decode("utf-8", errors="ignore")
    orig = t
    for u in OFFICIAL_APIS:
        t = t.replace(u, LOCAL_HTTP)
    for u in OFFICIAL_CDNS:
        t = t.replace(u, LOCAL_HTTP + "/resource/")
    # aktifkan tombol GM bila ada flag showGm tersembunyi (non-destruktif: tambah localTest)
    # jangan ubah logika lain; hanya tambah penanda agar GameConfig.showGm true via plat config override
    return (t.encode(), t != orig)

def main():
    if not os.path.exists(XAPK):
        print(f"XAPK tidak ketemu: {XAPK}"); sys.exit(1)
    work = os.path.join(HERE, "_work")
    if os.path.exists(work): shutil.rmtree(work)
    os.makedirs(work); os.makedirs(OUT, exist_ok=True)
    print(f"[1/5] extract XAPK ({os.path.getsize(XAPK)//1048576} MB)...")
    with zipfile.ZipFile(XAPK) as z: z.extractall(os.path.join(work, "xapk"))
    base_apk = os.path.join(work, "xapk", "com.renegadeImmortal.and.apk")
    pack_apk = os.path.join(work, "xapk", "install_time_asset_pack.apk")
    with zipfile.ZipFile(base_apk) as z: z.extractall(os.path.join(work, "base"))
    with zipfile.ZipFile(pack_apk) as z: z.extractall(os.path.join(work, "pack"))
    n = 0
    # patch index html
    for f in glob.glob(os.path.join(work, "pack", "assets", "game", "*.html")):
        d = open(f, "rb").read(); nd, ch = patch_text(d)
        if ch: open(f, "wb").write(nd); n += 1; print(f"  patched {os.path.basename(f)}")
    # patch js
    for f in glob.glob(os.path.join(work, "pack", "assets", "game", "js", "*.js")):
        d = open(f, "rb").read(); nd, ch = patch_text(d)
        if ch: open(f, "wb").write(nd); n += 1; print(f"  patched {os.path.basename(f)} ({len(d)//1024} KB)")
    print(f"[2/5] total file dipatch: {n}")
    # salin file patch penting ke patched_client/ agar user bisa pakai MT Manager tanpa repack penuh
    for f in glob.glob(os.path.join(work, "pack", "assets", "game", "*.html")):
        shutil.copy2(f, OUT)
    for f in glob.glob(os.path.join(work, "pack", "assets", "game", "js", "main.min_*.js")):
        shutil.copy2(f, OUT)
    print(f"[3/5] file patch disalin ke {OUT}/")
    # tulis ulang pack apk yang sudah dipatch (unsigned, perlu sign)
    patched_pack = os.path.join(OUT, "install_time_asset_pack.patched.apk")
    def zipdir(src, zf):
        for r, _, fs in os.walk(src):
            for fn in fs:
                fp = os.path.join(r, fn); ar = os.path.relpath(fp, src)
                zf.write(fp, ar, zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(patched_pack, "w", zipfile.ZIP_DEFLATED) as zf:
        zipdir(os.path.join(work, "pack"), zf)
    print(f"[4/5] {patched_pack} ({os.path.getsize(patched_pack)//1048576} MB)")
    print("[5/5] SELESAI.")
    print("--- Cara pakai (pilih 1) ---")
    print("A. Tanpa repack (termudah, root/emulator): jalankan server.py, lalu di HP/emulator")
    print(f"   arahkan hosts: xnh5api.51haodong.com -> 127.0.0.1  (app Hosts Go / VPN Hosts).")
    print("   Game ori langsung bicara ke private server. Shop & topup jadi gratis.")
    print("B. MT Manager (no PC): buka APK asli -> assets/game/ -> replace index_haodong.html")
    print(f"   dan js/main.min_*.js dengan file dari {OUT}/ -> save, sign, install.")
    print("C. Repack penuh: ganti file di _work/pack lalu zip jadi APK + sign dengan apksigner.")
    print(f"Pastikan server.py jalan di IP yang sama dengan HP (ganti {LOCAL_HTTP} ke IP LAN bila di HP fisik).")

if __name__ == "__main__":
    main()
