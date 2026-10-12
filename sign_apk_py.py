#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sign APK private langsung di PC tanpa Java (stdlib + cryptography).
- Buang signature lama (invalid setelah asset dipatch)
- Align .so ke 4096 byte (syarat load native lib di Android 6+)
- JAR-sign v1: MANIFEST.MF + CERT.SF + CERT.RSA (cukup untuk install langsung)
- Kunci debug dibuat sekali (ri-debug-key.pem, JANGAN push ke git)

Pakai: python sign_apk_py.py --in RI-Private-VPS.apk --out RI-Private-VPS-signed.apk
"""
import argparse, base64, hashlib, os, struct, sys, zipfile, zlib
import datetime
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

HERE = os.path.dirname(os.path.abspath(__file__))
STORE_EXT = (".so", ".png", ".jpg", ".jpeg", ".ogg", ".m4a", ".mp3", ".mp4", ".gz", ".zip")
SIG_TAILS = (".sf", ".rsa", ".dsa", ".ec", "manifest.mf")


def dos_time(dt):
    return ((dt[3] << 11) | (dt[4] << 5) | (dt[5] // 2),
            (((dt[0] - 1980) << 9) | (dt[1] << 5) | dt[2]))


def wrap76(b: bytes) -> bytes:
    out = b""
    while len(b) > 72:
        out += b[:72] + b"\r\n "
        b = b[72:]
    return out + b


def mf_section(name: str, digest_b64: str) -> bytes:
    return (wrap76(("Name: " + name).encode()) + b"\r\n" +
            wrap76(("SHA-256-Digest: " + digest_b64).encode()) + b"\r\n\r\n")


def load_or_make_key(path):
    if os.path.exists(path):
        return serialization.load_pem_private_key(open(path, "rb").read(), password=None)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    open(path, "wb").write(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass
    return key


def load_or_make_cert(path, key):
    if os.path.exists(path):
        return x509.load_pem_x509_certificate(open(path, "rb").read())
    now = datetime.datetime.now(datetime.timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "RI-Private Debug")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=30 * 365))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
                key_encipherment=False, data_encipherment=False, key_agreement=False,
                key_cert_sign=False, crl_sign=False, encipher_only=False,
                decipher_only=False), True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CODE_SIGNING]), False)
            .sign(key, hashes.SHA256()))
    open(path, "wb").write(cert.public_bytes(serialization.Encoding.PEM))
    return cert


def raw_deflate(data: bytes, level: int = 6) -> bytes:
    co = zlib.compressobj(level, zlib.DEFLATED, -15)  # raw deflate, tanpa header/adler
    return co.compress(data) + co.flush()


def align_extra(off, name_len, align):
    if align <= 1:
        return b""
    pad = (-(off + 30 + name_len)) % align
    if pad == 0:
        return b""
    while pad < 4:
        pad += align
    return struct.pack("<HH", 0xD935, pad - 4) + b"\x00" * (pad - 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--key", default=os.path.join(HERE, "ri-debug-key.pem"))
    ap.add_argument("--cert", default=os.path.join(HERE, "ri-debug-cert.pem"))
    a = ap.parse_args()

    key = load_or_make_key(a.key)
    cert = load_or_make_cert(a.cert, key)

    zin = zipfile.ZipFile(a.inp, "r")
    items = []  # (name, data, date_time, ext_attr, method, align)
    for info in zin.infolist():
        name = info.filename
        if name.endswith("/"):
            continue
        if name.upper().startswith("META-INF/") and name.lower().rsplit("/", 1)[-1].lower().endswith(SIG_TAILS):
            continue  # buang signature lama (digest-nya sudah invalid)
        data = zin.read(name)
        if name.lower().endswith(STORE_EXT):
            method, align = zipfile.ZIP_STORED, (4096 if name.lower().endswith(".so") else 4)
        else:
            method, align = zipfile.ZIP_DEFLATED, 1
        items.append((name, data, info.date_time, info.external_attr, method, align))
    zin.close()
    print(f"entri konten: {len(items)} (signature lama dibuang)")

    sections, out_entries = {}, []
    with open(a.out, "wb") as f:
        off = 0
        # 1) tulis semua entri konten
        for (name, data, dt, ext, method, align) in items:
            raw = data if method == zipfile.ZIP_STORED else raw_deflate(data)
            nb = name.encode("utf-8")
            extra = align_extra(off, len(nb), align)
            t, d = dos_time(dt)
            crc = zlib.crc32(data) & 0xFFFFFFFF
            f.write(struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0x800, method,
                                t, d, crc, len(raw), len(data), len(nb), len(extra)))
            f.write(nb)
            f.write(extra)
            f.write(raw)
            dg = base64.b64encode(hashlib.sha256(data).digest()).decode()
            sections[name] = mf_section(name, dg)
            out_entries.append((nb, extra, method, t, d, crc, len(raw), len(data), ext, off))
            off += 30 + len(nb) + len(extra) + len(raw)
        # 2) MANIFEST.MF
        mf = (b"Manifest-Version: 1.0\r\nCreated-By: RI-Private signer (python)\r\n\r\n" +
              b"".join(sections[n] for (n, *_) in items))
        # 3) CERT.SF
        sf = (b"Signature-Version: 1.0\r\nCreated-By: RI-Private signer (python)\r\n" +
              wrap76(("SHA-256-Digest-Manifest: " +
                      base64.b64encode(hashlib.sha256(mf).digest()).decode()).encode()) +
              b"\r\n\r\n" + b"".join(
                  mf_section(n, base64.b64encode(hashlib.sha256(sections[n]).digest()).decode())
                  for (n, *_rest) in items))
        # 4) CERT.RSA (CMS SignedData, konten = CERT.SF)
        rsa_der = pkcs7.PKCS7SignatureBuilder().set_data(sf).add_signer(
            cert, key, hashes.SHA256()).sign(serialization.Encoding.DER,
                                             [pkcs7.PKCS7Options.Binary])
        for (nb2, payload) in [(b"META-INF/MANIFEST.MF", mf),
                               (b"META-INF/CERT.SF", sf),
                               (b"META-INF/CERT.RSA", rsa_der)]:
            extra = b""
            t, d = dos_time((2026, 10, 12, 0, 0, 0))
            crc = zlib.crc32(payload) & 0xFFFFFFFF
            f.write(struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0x800,
                                zipfile.ZIP_STORED, t, d, crc, len(payload),
                                len(payload), len(nb2), 0))
            f.write(nb2)
            f.write(payload)
            out_entries.append((nb2, extra, zipfile.ZIP_STORED, t, d, crc,
                                len(payload), len(payload), (0o644 << 16), off))
            off += 30 + len(nb2) + len(payload)
        # 5) central directory + EOCD
        cd_off = off
        cd_parts = []
        for (nb, extra, method, t, d, crc, cs, us, ext, loff) in out_entries:
            cd_parts.append(struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 0x031E, 20,
                                   0x800, method, t, d, crc, cs, us, len(nb),
                                   len(extra), 0, 0, 0, ext, loff))
            cd_parts.append(nb)
            cd_parts.append(extra)
        cd = b"".join(cd_parts)
        f.write(cd)
        f.write(struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(out_entries),
                            len(out_entries), len(cd), cd_off, 0))
    print(f"ditulis: {a.out} ({os.path.getsize(a.out)//1048576} MB)")

    # ---- verifikasi ----
    z = zipfile.ZipFile(a.out, "r")
    bad = [i.filename for i in z.infolist()
           if not i.is_dir() and not i.filename.upper().startswith("META-INF/") and
           base64.b64encode(hashlib.sha256(z.read(i.filename)).digest()).decode()
           not in sections.get(i.filename, b"").decode(errors="ignore")]
    print("digest MANIFEST cocok semua:", not bad, bad[:3] if bad else "")
    # cek alignment .so
    fh = open(a.out, "rb")
    mis = 0
    for i in z.infolist():
        if i.filename.lower().endswith(".so"):
            fh.seek(i.header_offset)
            _sig, _v, _fl, _m, _t, _d, _c, _cs, _us, nl, el = struct.unpack(
                "<IHHHHHIIIHH", fh.read(30))
            if (i.header_offset + 30 + nl + el) % 4096 != 0:
                mis += 1
    fh.close()
    rsa_ok = z.read("META-INF/CERT.RSA")[:2] == b"\x30\x82" or \
        z.read("META-INF/CERT.RSA")[:1] == b"\x30"
    z.close()
    print(".so tidak align:", mis, "| CERT.RSA DER valid:", rsa_ok)
    assert not bad and mis == 0 and rsa_ok
    print("SELESAI — APK siap install langsung (uninstall versi resmi dulu, beda signature).")


if __name__ == "__main__":
    main()
