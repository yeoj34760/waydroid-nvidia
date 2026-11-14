# Native desktop title bars

This optional Android 13 resource overlay removes Android's freeform caption,
including its invisible click targets. The existing hwcomposer property
`persist.waydroid.window_decorations=true` requests server-side decorations
(SSD) from the Wayland compositor. The overlay is loaded at boot only when
that same property is `true`; it does not change app pixels or display density.
The compositor must support `zxdg_decoration_manager_v1` (for example, KWin).
Install hwcomposer with patch 0022 as well: it fits the native window to each
task and translates layers to that window's origin. Without it, SSD frames the
whole Android display and the app appears as a small rectangle inside it.

Build with Android SDK build tools, a JDK (`javac`, `jar`, `keytool`) and Java installed:

```sh
bash hwcomposer/ssd-overlay/build.sh
```

`ANDROID_BUILD_TOOLS` selects the SDK build-tools directory. Alternatively set
`AAPT2` and `APKSIGNER_JAR` separately. The positional argument selects the
installed Waydroid `framework-res.apk`; the SDK's `android.jar` does not contain
Waydroid's private back/minimize/PiP IDs. Rebuild after updating the system image.

With a Waydroid session running, enable SSD and stop the whole container:

```sh
waydroid prop set persist.waydroid.window_decorations true
# Record the old value for rollback, then remove client-side shadow insets.
sudo waydroid shell -- settings get global render_shadows_in_compositor
sudo waydroid shell -- settings put global render_shadows_in_compositor 1
# Let SettingsProvider persist the change before stopping Android.
sleep 1
waydroid session stop
sudo waydroid container stop
sudo install -Dm644 build/ssd-overlay/WaydroidSSD.apk \
  /var/lib/waydroid/overlay/system/product/overlay/WaydroidSSD/WaydroidSSD.apk
sudo install -Dm644 build/ssd-overlay/waydroid-ssd.jar \
  /var/lib/waydroid/overlay/system/framework/waydroid-ssd.jar
sudo waydroid container start
waydroid session start
```

This uses Waydroid's filesystem overlay (`mount_overlays = True`), not `adb
install`: a framework layout overlay must be preinstalled on the system partition.
The original system image is kept intact. Check activation after boot:

```sh
sudo waydroid shell -- cmd overlay lookup --verbose android android:layout/decor_caption
# Best matching is from default configuration of dev.waydroid.nvidia.ssd
```

To return to Android's caption, set the property to `false` while the session is
running, restore the previous `render_shadows_in_compositor` setting (use
`settings delete global render_shadows_in_compositor` if it was `null`), and
restart the whole container. No APK removal is needed. SSD has no Android Back button.

The host compositor moves each native window independently. A settled native
resize, maximize or tiled size requests a resize of that Android task; it does not resize
the shared Android display or other apps. While the task produces its new
buffers, the viewports fit the old content uniformly and input follows the same
mapping. This temporary fit preserves aspect ratio; new app buffers use the
native client dimensions after Android relays out the task.
The Java helper calls `ActivityTaskManager.resizeTask` directly as the composer's
system UID. `cmd activity task resize` uses Binder's shell entry point, which
rejects that UID; it cannot be used by the composer even though it works in a
root Waydroid shell. The helper grants no additional privileges.
Android's built-in `render_shadows_in_compositor` setting removes client-side
shadow padding; newly created app windows pick it up. See
[PhoneWindow](https://github.com/LineageOS/android_frameworks_base/blob/lineage-20.0/core/java/com/android/internal/policy/PhoneWindow.java).
GNOME's Mutter does not provide this
SSD protocol, so keep the Android caption there.

With hwcomposer patch 0023, this JAR also enables automatic logical display resizing
when `persist.waydroid.multi_windows=false` and native decorations are enabled.
The window's client size at the output scale becomes Android's logical resolution
after a 250 ms settle delay (`persist.waydroid.resize_settle_ms`). Stock composer
HALs retain their physical mode: WindowManager applies the override, and hwcomposer
removes its projection's black bars without stretching app pixels. `wm size`
shows the resulting override. The helper calls `IWindowManager.setForcedDisplaySize`
as the system UID; it needs no shell/root privilege. Multi-window mode clears that
override and continues resizing individual tasks. Rebuild and reinstall the JAR
when upgrading from patch 0022. If removing the helper, first reset an outstanding
override with `sudo waydroid shell -- wm size reset`.
