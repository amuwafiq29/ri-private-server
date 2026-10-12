#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build XAPK private dari XAPK ori: patch asset pack ke VPS, sign ULANG semua
split dengan 1 kunci debug yang sama (syarat install split Android),
bungkus lagi jadi .xapk siap install via APKPure / XAPK Installer.

Pakai: python build_xapk.py --host DOMAIN-VPS --scheme http --out RI-Private-v1.19.xapk
Butuh: Java + uber-apk-signer.jar (otomatis dipakai dari folder tools bila ada).
"""
import argparse, glob, json, os, shutil, subprocess, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
XAPK = os.path.join(os.path.dirname(HERE), "Renegade+Immortal_1.19_APKPure.xapk")
TOOLS = r"C:\Users\amuwa\AppData\Local\Temp\opencode\tools"
JAVA = os.path.join(TOOLS, "jre", "jdk-17.0.20.1+1-jre", "bin", "java.exe")
UBER = os.path.join(TOOLS, "uber-apk-signer.jar")

OFFICIAL_APIS = ["https://xnh5api.51haodong.com", "https://xnh5api2.btshidai.com",
    "https://xnh5api5.btshidai.com", "https://xnh5api.mcjdhjj.com",
    "https://xnh5api.rongrongnet.com"]
OFFICIAL_CDNS = ["https://xnh5cdn.51haodong.com/en/resource/", "https://xnh5cdn.51haodong.com/",
    "https://xnh5cdn3.btshidai.com/xiwan", "https://xnh5cdn.btshidai.com/banshu",
    "https://xnh5cdn.rongrongnet.com/xiwan", "https://xnh5release.mcjdhjj.com"]


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
    ap.add_argument("--host", required=True)
    ap.add_argument("--scheme", default="https", choices=["http", "https"])
    ap.add_argument("--http-port", default="")
    ap.add_argument("--out", default="RI-Private-v1.19.xapk")
    a = ap.parse_args()
    api_base = f"{a.scheme}://{a.host}" + (f":{a.http_port}" if a.http_port else "")
    if not os.path.exists(XAPK):
        print(f"XAPK ori tidak ketemu: {XAPK}")
        sys.exit(1)

    work = os.path.join(HERE, "_work_xapk")
    if os.path.exists(work):
        shutil.rmtree(work)
    os.makedirs(work)
    print(f"[1/5] extract XAPK ori ({os.path.getsize(XAPK)//1048576} MB)...")
    with zipfile.ZipFile(XAPK) as z:
        z.extractall(os.path.join(work, "xapk"))
    xx = os.path.join(work, "xapk")

    print(f"[2/5] patch asset pack -> {api_base} ...")
    pack_apk = os.path.join(xx, "install_time_asset_pack.apk")
    pd = os.path.join(work, "pack")
    with zipfile.ZipFile(pack_apk) as z:
        z.extractall(pd)
    n = 0
    for f in glob.glob(os.path.join(pd, "assets", "game", "*.html")):
        d = open(f, "rb").read()
        nd, ch = patch_bytes(d, api_base)
        if ch:
            open(f, "wb").write(nd)
            n += 1
            print(f"  {os.path.basename(f)} OK")
    for f in glob.glob(os.path.join(pd, "assets", "game", "js", "*.js")):
        d = open(f, "rb").read()
        nd, ch = patch_bytes(d, api_base)
        if ch:
            open(f, "wb").write(nd)
            n += 1
            print(f"  {os.path.basename(f)} OK ({len(d)//1024} KB)")
    mainjs = glob.glob(os.path.join(pd, "assets", "game", "js", "main.min_*.js"))[0]
    sisa = sum(open(mainjs, "rb").read().count(u.encode()) for u in OFFICIAL_APIS)
    print(f"  sisa URL resmi: {sisa}")
    assert sisa == 0, "patch gagal!"
    # zip ulang asset pack (isi berubah, signature lama invalid -> sign ulang semua di bawah)
    if os.path.exists(pack_apk):
        os.remove(pack_apk)
    with zipfile.ZipFile(pack_apk, "w", zipfile.ZIP_DEFLATED) as zf:
        for r, _, fs in os.walk(pd):
            for fn in fs:
                fp = os.path.join(r, fn)
                zf.write(fp, os.path.relpath(fp, pd))

    print("[3/5] sign ulang SEMUA split dengan 1 kunci (syarat install split)...")
    if not (os.path.exists(JAVA) and os.path.exists(UBER)):
        print("  Java/uber-apk-signer tidak ketemu, lewati sign (XAPK unsigned).")
    else:
        sign_in = os.path.join(work, "sign_in")
        os.makedirs(sign_in)
        for f in glob.glob(os.path.join(xx, "*.apk")):
            shutil.copy2(f, sign_in)
        r = subprocess.run([JAVA, "-jar", UBER, "-a", sign_in, "-o",
                            os.path.join(work, "sign_out"), "--allowResign"],
                           capture_output=True, text=True)
        print("  " + (r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "")[:100])
        if r.returncode != 0:
            print(r.stdout[-2000:] + r.stderr[-2000:])
            sys.exit("uber-apk-signer gagal")
        for f in glob.glob(os.path.join(work, "sign_out", "*-aligned-debugSigned.apk")):
            orig_name = os.path.basename(f).replace("-aligned-debugSigned.apk", ".apk")
            shutil.copy2(f, os.path.join(xx, orig_name))
        print(f"  split di-sign: {len(glob.glob(os.path.join(work, 'sign_out', '*-aligned-debugSigned.apk')))}")

    print("[4/5] bungkus ulang XAPK...")
    out = os.path.join(HERE, a.out)
    if os.path.exists(out):
        os.remove(out)
    manifest_p = os.path.join(xx, "manifest.json")
    mf = json.load(open(manifest_p, encoding="utf-8"))
    total = sum(os.path.getsize(os.path.join(xx, f)) for f in os.listdir(xx)
                if f.endswith(".apk"))
    mf["total_size"] = total
    json.dump(mf, open(manifest_p, "w", encoding="utf-8"))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for fn in sorted(os.listdir(xx)):
            zf.write(os.path.join(xx, fn), fn)
    print(f"  {out} ({os.path.getsize(out)//1048576} MB, total_size={total})")

    print("[5/5] verifikasi...")
    z = zipfile.ZipFile(out)
    names = z.namelist()
    print("  isi:", len(names), "file | manifest.json:", "manifest.json" in names,
          "| icon:", "icon.png" in names)
    z.close()
    shutil.rmtree(work, ignore_errors=True)
    print("SELESAI. Install via aplikasi APKPure / XAPK Installer di HP.")


if __name__ == "__main__":
    main()
