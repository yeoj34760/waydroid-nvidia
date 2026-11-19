#!/usr/bin/env python3
"""Check RGB565 read-back selection and partial buffer cleanup on the host."""
from pathlib import Path
import subprocess
import sys
import tempfile

from test_background_opacity import block


tree = Path(sys.argv[1]) / "hwcomposer"
harness = r"""
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <sys/mman.h>
#define ALOGE(...) ((void)0)
enum { HAL_PIXEL_FORMAT_RGB_565 = 4, HAL_PIXEL_FORMAT_RGBX_8888 = 2,
       HAL_PIXEL_FORMAT_RGBA_8888 = 1, WL_SHM_FORMAT_XRGB8888 = 1,
       WL_SHM_FORMAT_ARGB8888 = 0 };
struct wl_buffer {};
int destroyed = 0, unmapped = 0, released = 0;
void wl_buffer_destroy(wl_buffer *p) { assert(p); ++destroyed; }
void prime_release_source(void *) { ++released; }
int checked_munmap(void *p, int) {
    assert(p && p != MAP_FAILED); ++unmapped; return 0;
}
#define munmap checked_munmap
"""
harness += block((tree / "wayland-hwc.h").read_text(), "struct buffer {").replace(
    "    buffer_handle_t handle;", "").replace("    buffer_metadata metadata;", "") + ";\n"
harness += block((tree / "wayland-hwc.cpp").read_text(), "buffer::~buffer()")
harness += block((tree / "gralloc_handler.cpp").read_text(), "uint32_t ConvertHalFormatToShm(")
harness += r"""
int main() {
    assert(ConvertHalFormatToShm(HAL_PIXEL_FORMAT_RGB_565) == WL_SHM_FORMAT_XRGB8888);
    assert(ConvertHalFormatToShm(HAL_PIXEL_FORMAT_RGBA_8888) == WL_SHM_FORMAT_ARGB8888);
    assert(ConvertHalFormatToShm(999) == (uint32_t)-EINVAL);
    { buffer b{}; }
    { buffer b{}; b.isShm = true; b.shm_data = MAP_FAILED; }
    assert(destroyed == 0 && unmapped == 0);
    wl_buffer proxy;
    int pixels;
    { buffer b{}; b.isShm = true; b.shm_data = &pixels; b.wl_buffer = &proxy; }
    assert(destroyed == 1 && unmapped == 1);
    { buffer b{}; b.prime = true; b.wl_buffer = &proxy; }
    assert(destroyed == 1 && released == 1);
}
"""
with tempfile.TemporaryDirectory() as tmp:
    source = Path(tmp) / "check.cpp"
    binary = Path(tmp) / "check"
    source.write_text(harness)
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print("PASS: RGB565 read-back and partial buffer cleanup")
