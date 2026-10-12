#!/bin/bash
# Sign APK di VPS (Java tersedia). Pakai: bash sign_apk.sh RI-Private-v1.19.apk
set -e
APK="${1:-RI-Private-v1.19.apk}"
KEY=ri-debug.keystore
ALIGNED="${APK%.apk}.aligned.apk"
SIGNED="${APK%.apk}.signed.apk"
[ -f "$KEY" ] || keytool -genkeypair -keystore "$KEY" -alias ri -keyalg RSA -keysize 2048 -validity 10950 -storepass android -keypass android -dname "CN=RI Private" >/dev/null
zipalign -f 4 "$APK" "$ALIGNED"
apksigner sign --ks "$KEY" --ks-pass:android --key-pass:android --out "$SIGNED" "$ALIGNED"
echo "OK -> $SIGNED"
apksigner verify --print-certs "$SIGNED" | head -5
