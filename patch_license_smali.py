#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patch bypass license check Renegade Immortal (pairip LicenseClient).
- initializeLicenseCheck() -> langsung set FULL_CHECK_OK, return.
- handleError() -> no-op (tidak ada dialog "Dapatkan game ini di Play").
- performLocalInstallerCheck() -> selalu true (lapis kedua).

Pakai: python patch_license_smali.py <folder-hasil-apktool-decode-base>
"""
import re, sys, os

INIT_OK = """.method public initializeLicenseCheck()V
    .locals 1
    sget-object v0, Lcom/pairip/licensecheck/LicenseClient$LicenseCheckState;->FULL_CHECK_OK:Lcom/pairip/licensecheck/LicenseClient$LicenseCheckState;
    sput-object v0, Lcom/pairip/licensecheck/LicenseClient;->licenseCheckState:Lcom/pairip/licensecheck/LicenseClient$LicenseCheckState;
    return-void
.end method
"""

HANDLE_OK = """.method private handleError(Lcom/pairip/licensecheck/LicenseCheckException;)V
    .locals 1
    .annotation system Ldalvik/annotation/MethodParameters;
        accessFlags = {
            0x0
        }
        names = {
            "ex"
        }
    .end annotation
    return-void
.end method
"""

LOCAL_OK = """.method private performLocalInstallerCheck()Z
    .locals 1
    const/4 v0, 0x1
    return v0
.end method
"""


def patch_method(src, sig, repl):
    pat = re.compile(r'\.method [^\n]*' + re.escape(sig) + r'\n.*?\.end method\n', re.S)
    new, n = pat.subn(repl, src, count=1)
    return new, n


def main():
    base = sys.argv[1]
    f = os.path.join(base, "smali_classes2", "com", "pairip", "licensecheck",
                     "LicenseClient.smali")
    src = open(f, encoding="utf-8").read().replace("\r\n", "\n")
    total = 0
    for sig, repl in [("initializeLicenseCheck()V", INIT_OK),
                      ("handleError(Lcom/pairip/licensecheck/LicenseCheckException;)V", HANDLE_OK),
                      ("performLocalInstallerCheck()Z", LOCAL_OK)]:
        src, n = patch_method(src, sig, repl)
        print(f"{sig}: {'OK' if n else 'GAGAL'}")
        total += n
    assert total == 3, "patch tidak lengkap!"
    open(f, "w", encoding="utf-8").write(src)
    print("LicenseClient terpatch: license selalu OK, dialog Play mati.")


if __name__ == "__main__":
    main()
