#!/usr/bin/env python3
"""Check the real resize/refit code without Android or a running compositor.

Usage: python3 hwcomposer/test_background_opacity.py PATCHED_HWC_TREE
"""
from pathlib import Path
import subprocess
import sys
import tempfile


def block(source, marker):
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def main():
    source = (Path(sys.argv[1]) / "hwcomposer/wayland-hwc.cpp").read_text()
    refit = block(source, "if (w->dedicated_background_surface && w->viewport && w->surface)")
    configure = block(source, "if (window->dedicated_background_surface && window->viewport)")
    helper = (block(source, "void window::update_background_geometry()")
              if "void window::update_background_geometry()" in source else "")
    harness = r"""
#include <cassert>
#include <initializer_list>
struct wl_region { bool opaque = false; };
struct wl_surface { bool opaque = false; };
struct wp_viewport { int width = 0, height = 0; };
struct display { int width = 1920, height = 1080; void *compositor = nullptr; };
struct window {
    struct display *display;
    bool dedicated_background_surface = true;
    bool background_opaque;
    wl_surface *surface;
    wp_viewport *viewport;
    void update_background_geometry();
};
wl_region *wl_compositor_create_region(void *) { return new wl_region; }
void wl_region_add(wl_region *r, int x, int y, int width, int height) {
    assert(x == 0 && y == 0 && width > 0 && height > 0);
    r->opaque = true;
}
void wl_surface_set_opaque_region(wl_surface *s, wl_region *r) { s->opaque = r->opaque; }
void wl_region_destroy(wl_region *r) { delete r; }
void wl_surface_commit(wl_surface *) {}
void wp_viewport_set_destination(wp_viewport *v, int width, int height) {
    v->width = width; v->height = height;
}
""" + helper + "\nvoid refit(window *w) { [[maybe_unused]] auto *display = w->display;\n" + refit + r"""
}
void configure(window *window) { [[maybe_unused]] auto *display = window->display;
""" + configure + r"""
}
int main() {
    for (bool opaque : {false, true}) {
        display d;
        wl_surface s;
        wp_viewport v;
        window w{&d, true, opaque, &s, &v};
        for (int size : {800, 1200, 640}) {
            d.width = size; d.height = size / 2;
            for (auto update : {configure, refit}) {
                // Simulate a stale region as well as a newly created parent.
                s.opaque = !opaque;
                update(&w);
                assert(s.opaque == opaque);
                assert(v.width == d.width && v.height == d.height);
            }
        }
    }
}
"""
    with tempfile.TemporaryDirectory(prefix="hwc-opacity-") as tmp:
        cpp = Path(tmp) / "check.cpp"
        executable = Path(tmp) / "check"
        cpp.write_text(harness)
        subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        str(cpp), "-o", str(executable)], check=True)
        subprocess.run([str(executable)], check=True)
    print("PASS: configure/refit preserve transparent and opaque backgrounds across resizes")


if __name__ == "__main__":
    main()
