#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Repack XAPK: ganti base split dengan base-licfix, sign ulang semua, bungkus XAPK."""
import glob, json, os, shutil, subprocess, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
XAPK_IN = os.path.join(HERE, "RI-Private-v1.19.xapk")
BASE_FIX = os.path.join(HERE, "base-licfix.apk")
TOOLS = r"C:\Users\amuwa\AppData\Local\Temp\opencode\tools"
JAVA = os.path.join(TOOLS, "jre", "jdk-17.0.20.1+1-jre", "bin", "java.exe")
UBER = os.path.join(TOOLS, "uber-apk-signer.jar")

work = os.path.join(HERE, "_work_licfix")
if os.path.exists(work):
    shutil.rmtree(work)
os.makedirs(work)
xx = os.path.join(work, "xapk")
print("[1/4] extract XAPK private...")
with zipfile.ZipFile(XAPK_IN) as z:
    z.extractall(xx)
print("[2/4] ganti base split...")
shutil.copy2(BASE_FIX, os.path.join(xx, "com.renegadeImmortal.and.apk"))
print("[3/4] sign ulang semua split...")
sin = os.path.join(work, "sign_in")
os.makedirs(sin)
for f in glob.glob(os.path.join(xx, "*.apk")):
    shutil.copy2(f, sin)
r = subprocess.run([JAVA, "-jar", UBER, "-a", sin, "-o", os.path.join(work, "sign_out"),
                    "--allowResign"], capture_output=True, text=True)
print("  " + (r.stdout.strip().splitlines() or ["?"])[-1][:100])
assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
n = 0
for f in glob.glob(os.path.join(work, "sign_out", "*-aligned-debugSigned.apk")):
    shutil.copy2(f, os.path.join(xx, os.path.basename(f).replace("-aligned-debugSigned.apk", ".apk")))
    n += 1
print(f"  split di-sign: {n}")
print("[4/4] bungkus XAPK...")
mf_p = os.path.join(xx, "manifest.json")
mf = json.load(open(mf_p, encoding="utf-8"))
mf["total_size"] = sum(os.path.getsize(os.path.join(xx, f)) for f in os.listdir(xx) if f.endswith(".apk"))
json.dump(mf, open(mf_p, "w", encoding="utf-8"))
out = os.path.join(HERE, "RI-Private-v1.19.xapk")
if os.path.exists(out):
    os.remove(out)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
    for fn in sorted(os.listdir(xx)):
        zf.write(os.path.join(xx, fn), fn)
print(f"  {out} ({os.path.getsize(out)//1048576} MB)")
shutil.rmtree(work, ignore_errors=True)
print("SELESAI.")
