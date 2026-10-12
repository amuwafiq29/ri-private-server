#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build APK private Renegade Immortal 1.19 yang langsung nyambung ke VPS kamu.
- Input : Renegade+Immortal_1.19_APKPure.xapk (sefolder di atas)
- Output: RI-Private-v1.19.apk (single APK, sudah dipatch ke host VPS)
- Lib stdlib saja. Hasil BELUM di-sign di PC ini (tidak ada Java) -> sign 1x tap
  di HP via MT Manager, atau jalankan sign_apk.sh di VPS (ada Java).

Pakai:  python build_apk.py --host ri.contoh.com --scheme https
        python build_apk.py --host 192.168.1.20 --scheme http --http-port 8080
"""
import argparse, os, shutil, sys, zipfile, glob

HERE = os.path.dirname(os.path.abspath(__file__))
XAPK = os.path.join(os.path.dirname(HERE), "Renegade+Immortal_1.19_APKPure.xapk")

OFFICIAL_APIS = ["https://xnh5api.51haodong.com", "https://xnh5api2.btshidai.com",
    "https://xnh5api5.btshidai.com", "https://xnh5api.mcjdhjj.com",
    "https://xnh5api.rongrongnet.com"]
OFFICIAL_CDNS = ["https://xnh5cdn.51haodong.com/en/resource/", "https://xnh5cdn.51haodong.com/",
    "https://xnh5cdn3.btshidai.com/xiwan", "https://xnh5cdn.btshidai.com/banshu",
    "https://xnh5cdn.rongrongnet.com/xiwan", "https://xnh5release.mcjdhjj.com"]
# ekstensi yang sudah terkompresi (jangan dikompres ulang biar cepat + kecil)
STORE_EXT = (".so", ".png", ".jpg", ".jpeg", ".ogg", ".m4a", ".mp3", ".mp4", ".gz", ".zip")

def patch_bytes(data: bytes, api_base: str):
    t = data.decode("utf-8", errors="ignore")
    orig = t
    for u in OFFICIAL_APIS:
        t = t.replace(u, api_base)
    for u in OFFICIAL_CDNS:
        t = t.replace(u, api_base + "/resource/")
    return (t.encode(), t != orig)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True, help="domain/IP VPS, cth: ri.contoh.com")
    ap.add_argument("--scheme", default="https", choices=["http", "https"])
    ap.add_argument("--http-port", default="", help="kosongkan bila https standar (443)")
    ap.add_argument("--ws-port", default="29601")
    ap.add_argument("--out", default="RI-Private-v1.19.apk")
    a = ap.parse_args()
    api_base = f"{a.scheme}://{a.host}" + (f":{a.http_port}" if a.http_port else "")
    if not os.path.exists(XAPK):
        print(f"XAPK tidak ketemu: {XAPK}"); sys.exit(1)

    work = os.path.join(HERE, "_work_apk")
    if os.path.exists(work): shutil.rmtree(work)
    os.makedirs(work)
    print(f"[1/5] extract XAPK ({os.path.getsize(XAPK)//1048576} MB)...")
    with zipfile.ZipFile(XAPK) as z: z.extractall(os.path.join(work, "xapk"))
    base_apk = os.path.join(work, "xapk", "com.renegadeImmortal.and.apk")
    with zipfile.ZipFile(base_apk) as z: z.extractall(os.path.join(work, "base"))
    cfg_apk = os.path.join(work, "xapk", "config.arm64_v8a.apk")
    with zipfile.ZipFile(cfg_apk) as z: z.extractall(os.path.join(work, "cfg"))
    pack_apk = os.path.join(work, "xapk", "install_time_asset_pack.apk")
    with zipfile.ZipFile(pack_apk) as z: z.extractall(os.path.join(work, "pack"))

    print(f"[2/5] patch URL client -> {api_base} ...")
    n = 0
    for f in glob.glob(os.path.join(work, "pack", "assets", "game", "*.html")):
        d = open(f, "rb").read(); nd, ch = patch_bytes(d, api_base)
        if ch: open(f, "wb").write(nd); n += 1; print(f"  {os.path.basename(f)} OK")
    for f in glob.glob(os.path.join(work, "pack", "assets", "game", "js", "*.js")):
        d = open(f, "rb").read(); nd, ch = patch_bytes(d, api_base)
        if ch: open(f, "wb").write(nd); n += 1; print(f"  {os.path.basename(f)} OK ({len(d)//1024} KB)")
    # validasi: tidak boleh ada sisa URL resmi di main js
    mainjs = glob.glob(os.path.join(work, "pack", "assets", "game", "js", "main.min_*.js"))[0]
    sisa = sum(open(mainjs, "rb").read().count(u.encode()) for u in OFFICIAL_APIS)
    print(f"  file dipatch: {n}, sisa URL resmi di main js: {sisa}")
    assert sisa == 0, "patch gagal, masih ada URL resmi!"

    print("[3/5] gabung base + lib arm64 + assets jadi single APK...")
    base = os.path.join(work, "base")
    # copy .so arm64
    for src in glob.glob(os.path.join(work, "cfg", "lib", "arm64-v8a", "*.so")):
        dst = os.path.join(base, "lib", "arm64-v8a", os.path.basename(src))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    # copy assets game hasil patch
    pack_assets = os.path.join(work, "pack", "assets")
    for root, _, files in os.walk(pack_assets):
        for fn in files:
            src = os.path.join(root, fn)
            rel = os.path.relpath(src, os.path.join(work, "pack"))
            dst = os.path.join(base, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

    print("[4/5] zip ulang jadi APK...")
    out = os.path.join(HERE, a.out)
    if os.path.exists(out): os.remove(out)
    with zipfile.ZipFile(out, "w") as zf:
        for root, _, files in os.walk(base):
            for fn in files:
                fp = os.path.join(root, fn)
                ar = os.path.relpath(fp, base).replace(os.sep, "/")
                comp = zipfile.ZIP_STORED if ar.lower().endswith(STORE_EXT) else zipfile.ZIP_DEFLATED
                zf.write(fp, ar, comp)
    print(f"  {out} ({os.path.getsize(out)//1048576} MB)")

    print("[5/5] sign...")
    import shutil as sh
    if sh.which("apksigner") and sh.which("zipalign"):
        print("  apksigner ketemu, lihat sign_apk.sh untuk perintah sign di VPS.")
    else:
        print("  BELUM di-sign (PC ini tidak ada Java/apksigner).")
        print("  Cara sign 1 menit di HP: buka MT Manager -> klik APK -> Sign -> install.")
        print("  Atau di VPS (ada Java): bash sign_apk.sh RI-Private-v1.19.apk")
    print("SELESAI. Install APK di HP, buka, login -> server PRIVATE-GRATIS-1.")
    shutil.rmtree(work, ignore_errors=True)

if __name__ == "__main__":
    main()
