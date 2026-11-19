# Troubleshooting

The first thing to try for almost any problem is `sudo waydroid-nvidia-setup`. It re-checks the host, re-tests
the driver on your GPU and prints the reason and the fix when something is wrong.

## Is it working?

```sh
sudo waydroid shell dumpsys SurfaceFlinger | grep GLES
```

This should name your NVIDIA GPU. With `--native-gl on` it shows `waydroid-nvidia-prolapse (nvrm)`.

Two status reports list every check with PASS or FAIL:

```sh
sudo python3 /usr/lib/waydroid-nvidia/native/packaging/native/vendor_image.py status
python3 /usr/lib/waydroid-nvidia/native/dev/driver-mode status
```

## Common problems

| What you see | Why | What to do |
|---|---|---|
| Waydroid refuses to start after an NVIDIA driver or package update | the installed vendor image was tested on the old driver | `sudo waydroid-nvidia-setup` |
| Waydroid is not running after a reboot ("no /dev/nvidia<N> device node found") | 0.2.0-rc1 started the container before the NVIDIA driver finished loading | update, then `sudo waydroid-nvidia-setup` once; until then `sudo systemctl start waydroid-container` |
| Waydroid fails at boot with "NVIDIA GPU not up at container start" | the NVIDIA driver did not load within 90 s | check `journalctl -b -k \| grep -iE 'NVRM\|nvidia-drm'`, fix the driver, then `sudo systemctl start waydroid-container` |
| Waydroid refuses to start after `waydroid init` or `waydroid init -f` | init installs the official vendor image, not ours | `sudo waydroid-nvidia-setup` |
| Setup says "hardware video decode: not available on ..." | the GPU is older than RTX 20 / GTX 16 (Turing), where our decoder starts, or its decoder class is one our decoder has not been verified on yet (the message names the class) | nothing: video plays through Android's software decoders. After a GPU change run `sudo waydroid-nvidia-setup` again |
| Setup stops with "lxc-info cannot read the Waydroid container" | LXC rejects the container config (LXC's own message follows) | `sudo waydroid upgrade -o`, then the setup again; report it if LXC still refuses |
| Setup stops at `nvidia-drm.modeset` | without modeset the driver cannot share buffers at all | add `nvidia_drm.modeset=1` to the kernel command line or modprobe.d, reboot |
| Setup stops at a failing test case | the driver does not work on this GPU or driver version | the message names a log in `/var/lib/waydroid-nvidia/gate-*`; [report it](#reporting-a-problem) and use `sudo waydroid-nvidia-setup --mode venus` meanwhile |
| The display freezes or stutters on a monitor above about 333 Hz | Android's stock SurfaceFlinger merges vsyncs closer than 3 ms | `sudo waydroid-nvidia-setup --refresh 240` (`--refresh auto` removes the cap) |
| Black or missing window while the desktop runs on another GPU | the compositor cannot show buffers from the NVIDIA GPU | run the Wayland desktop on the NVIDIA GPU |
| Native mode stops after `[gbinder] Service manager ... has appeared` on a host with multiple NVIDIA GPUs | ANGLE can choose a different GPU from gralloc, dropping dma-buf support or failing EGL image imports | bind only the NVIDIA RM device matching gralloc's DRM render node; the mode generator now does this by PCI address and RM device minor, which need not have the same numbering |
| Waydroid keeps using old images after an update | Waydroid prefers images in `/etc/waydroid-extra/images` or `/usr/share/waydroid-extra/images` | move those images away |
| An app misbehaves only with `--native-gl on` | bug in our GL driver | report it; `--native-gl off` goes back to ANGLE |

## Keep inactive app windows live

Enable multi-window mode while the session is running, then restart the whole container:

```sh
waydroid prop set persist.waydroid.multi_windows true
waydroid session stop
sudo systemctl restart waydroid-container
waydroid session start
```

The composer reads this property at startup. Setting it without restarting can leave Android
and the composer using different window modes. In single-window mode, inactive app windows
are replaced with still snapshots; multi-window mode presents each visible task's layers
directly. An individual app can still pause its animation when it loses focus.

After restarting, `waydroid prop get persist.waydroid.multi_windows` should print `true`.
If composer logs still say `Making inactive window snapshot`, check that the full container
was restarted and that the compositor provides `wl_subcompositor` (otherwise multi-window
mode is disabled with a warning).

## Cursor disappears while dragging in games

Some Unity games, including Blue Archive, send a transparent custom cursor when
the mouse button is pressed. With `persist.waydroid.fake_touch` enabled, Android
can also remove its pointer sprite during touch input. The pinned hwcomposer fork
keeps the last visible cursor image during fake-touch drags and when a game sends
a fully transparent sprite after clicking, even without subsequent mouse motion.
This uses the default Wayland cursor path (`persist.waydroid.cursor_on_subsurface`
unset or `false`); pointer capture can still hide the cursor. After installing an
updated composer library, restart the entire container to load it.

## Venus mode

| What you see | What to do |
|---|---|
| "Venus render server socket ... not accepting connections" | `systemctl --user enable --now wd-venus.service` (without sudo; it is a user service) |
| Invisible cursor or black screenshots | log out and in once after installing (the udev rule grants `/dev/udmabuf` to the seated user) |
| Setup says the vendor image is too old | `sudo sed -i 's/^vendor_datetime.*/vendor_datetime = 0/' /var/lib/waydroid/waydroid.cfg`, `sudo rm /var/lib/waydroid/images/vendor.img`, `sudo waydroid init -f` (add `-s GAPPS` if you use GApps), then re-run setup |

Venus needs the open kernel module and an RTX 20 or newer GPU. To check a machine without installing anything:

```sh
gcc -O1 -o nvimportprobe tests/nvimportprobe.c -ldl && ./nvimportprobe
```

Exit code 0 means Venus mode can work here; 3 means it cannot, and the output says why.

## Reporting a problem

Open an issue at https://github.com/Shiro836/waydroid-nvidia/issues and include:

- your GPU, `cat /proc/driver/nvidia/version`, open or closed kernel module, distro and desktop;
- the mode and whether native GL is on, plus the output of both status commands above;
- for a failed setup, the `/var/lib/waydroid-nvidia/gate-*` directory it printed;
- the app and what happened, with `sudo waydroid logcat -d` and `sudo journalctl -k | grep -i xid` from around
  that time;
- whether the same app works with `--mode venus`.

Skim the logs for personal data before attaching them.
