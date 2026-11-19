# hwcomposer — build from the maintained source fork

The guest composer HAL (`/vendor/lib64/hw/hwcomposer.waydroid.so`) is built from
[yeoj34760/android_hardware_waydroid](https://github.com/yeoj34760/android_hardware_waydroid),
pinned by URL and full commit SHA in `pins.env`. The fork tracks upstream
`lineage-20` for the Android 13 images used here. Source changes and host regression
tests live in that repository; this directory holds the standalone NDK build glue.

The former 29-patch series is preserved in Git history and in the fork's individual
source commits. Patch 0009 is superseded by upstream `4aee4c8` (leave the service's
binder threadpool configuration alone). The vendor-image-only Android.bp change
for cross-GPU presentation is also included in the fork. No hwcomposer patches
are applied by this repository's builds.

## Build

```sh
hwcomposer/provision.sh          # pinned source, NDK, headers, host tools and link stubs
hwcomposer/build.sh              # build/hwcomposer-work/out/hwcomposer.waydroid.{so,stripped.so}
sh build/hwcomposer-work/tree/tests/hwcomposer/run.sh
```

The build extracts the pinned fork commit into `build/hwcomposer-work/tree`.
`out/SOURCE` records the source URL and commit. The host tests cover background
opacity, task geometry, child/IME routing, logical display resize, RGB565 read-back,
cleanup after partial buffer creation, and cursor visibility/image preservation
during touch drags and after clicks without mouse motion. They do not replace a live compositor
check. CI runs the same build and tests.

For local edits:

```sh
HWC_SRC=/path/to/android_hardware_waydroid hwcomposer/build.sh
sh /path/to/android_hardware_waydroid/tests/hwcomposer/run.sh
```

`HWC_SRC` builds the checkout directly and records its commit and tracked dirty
state in `SOURCE`. `HWC_PATCHES_UPTO` is retired; use a fork checkout at a chosen
commit for comparisons. Commit and push source changes in the fork before updating
`HWC_SHA`, so fresh package/CI builds can fetch that commit.

The prolapse vendor-image build checks out the same fork commit for
`hardware/waydroid`, then builds it with Soong. Stock reproduction and
SurfaceFlinger builds retain their historical source manifest. Updating the fork
pin invalidates the prolapse tree stamp.

## Dependencies

`pins.env` fixes NDK r29, Android 13 AOSP/LineageOS headers, Waydroid minigbm,
libffi, wayland, libxkbcommon, libdrm headers, wayland-protocols and image link
stubs. `provision.sh` fetches them and verifies the download hashes. It supports
individual stages (`ndk`, `clones`, `hidlgen`, `hidlout`, `staticdeps`, `protocols`,
`imagelibs`). The NDK build requires no AOSP source tree.

The optional [SSD resource overlay](ssd-overlay/README.md) hides Android's caption
when `persist.waydroid.window_decorations` is enabled. Single-window SSD on stock
HALs uses a logical display override; the fixed physical mode is intentional.

## Licences

Build glue adapted from the original waydroid-nvidia standalone build is MIT.
Fork source files retain their copyright and licence notices; migrated commit
messages retain the original patch attribution and licensing notes. Static guest
dependencies include wayland (MIT), libffi (MIT), libxkbcommon (MIT/X11-style).
