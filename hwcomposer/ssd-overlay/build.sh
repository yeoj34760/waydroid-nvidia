#!/usr/bin/env bash
# Build against the installed Waydroid framework: its private caption IDs differ
# from the SDK's android.jar. No system-image rebuild or platform signing key.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
OUT=${SSD_OUT:-$REPO/build/ssd-overlay}
FRAMEWORK=${1:-/var/lib/waydroid/rootfs/system/framework/framework-res.apk}
SDK=${ANDROID_SDK_ROOT:-${ANDROID_HOME:-/opt/android-sdk}}
TOOLS=${ANDROID_BUILD_TOOLS:-$SDK/build-tools/36.0.0}
AAPT2=${AAPT2:-$TOOLS/aapt2}
SIGNER=${APKSIGNER_JAR:-$TOOLS/lib/apksigner.jar}
[[ -r "$FRAMEWORK" ]] || { echo "Missing Waydroid framework: $FRAMEWORK" >&2; exit 1; }
[[ -x "$AAPT2" && -r "$SIGNER" ]] || {
    echo "Set AAPT2 and APKSIGNER_JAR, or ANDROID_BUILD_TOOLS to installed SDK build tools" >&2
    exit 1
}
mkdir -p "$OUT"
"$AAPT2" compile --dir "$HERE/res" -o "$OUT/resources.zip"
"$AAPT2" link -o "$OUT/unsigned.apk" --manifest "$HERE/AndroidManifest.xml" \
    -I "$FRAMEWORK" --no-resource-deduping --no-resource-removal "$OUT/resources.zip"
if [[ ! -f "$OUT/overlay.jks" ]]; then
    keytool -genkeypair -keystore "$OUT/overlay.jks" -storepass android -keypass android \
        -alias overlay -keyalg RSA -keysize 2048 -validity 10000 -dname 'CN=Waydroid SSD overlay' -noprompt
fi
java -jar "$SIGNER" sign --ks "$OUT/overlay.jks" --ks-pass pass:android \
    --key-pass pass:android --v4-signing-enabled false --out "$OUT/WaydroidSSD.apk" "$OUT/unsigned.apk"
java -jar "$SIGNER" verify "$OUT/WaydroidSSD.apk"
mkdir -p "$OUT/classes" "$OUT/dex"
javac --release 8 -d "$OUT/classes" "$HERE/src/dev/waydroid/ssd/TaskResize.java"
jar cf "$OUT/task-classes.jar" -C "$OUT/classes" .
java -cp "$TOOLS/lib/d8.jar" com.android.tools.r8.D8 --min-api 33 \
    --output "$OUT/dex" "$OUT/task-classes.jar"
jar cf "$OUT/waydroid-ssd.jar" -C "$OUT/dex" classes.dex
echo "$OUT/WaydroidSSD.apk"
echo "$OUT/waydroid-ssd.jar"
