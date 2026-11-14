#!/usr/bin/env python3
"""Check stock-HAL logical resize projection and client-target cropping."""
from pathlib import Path
import subprocess
import sys
import tempfile
from test_background_opacity import block

root = Path(sys.argv[1]) / 'hwcomposer'
resize = (root / 'display-resize.cpp').read_text()
wayland = (root / 'wayland-hwc.cpp').read_text()
hwc = (root / 'hwcomposer.cpp').read_text()
harness = r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <chrono>
#include <condition_variable>
#include <thread>
#include <mutex>
struct hwc_rect_t { int left, top, right, bottom; };
struct hwc_frect_t { float left, top, right, bottom; };
struct display {
    std::mutex modes_mutex;
    int phys_width = 3840, phys_height = 2058;
    int logical_width = 0, logical_height = 0;
    int width = 1200, height = 800;
    double scale = 1.5, output_scale = 1.5;
    int present_x = 0, present_y = 0;
    std::atomic<bool> multiWindows{false};
    bool resizeFollowsWindow = true, resizeUsesReconnect = false;
    std::mutex resize_mutex;
    std::condition_variable resize_cond;
    std::chrono::steady_clock::time_point resize_deadline;
    int resize_width = -1, resize_height = -1;
    bool resize_armed = false, resize_quit = false;
    std::thread resize_thread;
};
struct device { struct display *display; };
constexpr int HWC_FRAMEBUFFER_TARGET = 3;
struct hwc_layer_1 {
    int compositionType, acquireFenceFd;
    hwc_rect_t displayFrame;
    hwc_frect_t sourceCropf;
};
''' + block(resize, 'hwc_rect_t display_content_frame(') + '\n' + block(wayland, 'static void\nfit_guest_display_to_window(') + r'''
void crop(device *pdev, hwc_layer_1 *hwc_layer) {
''' + block(hwc, 'if (!pdev->display->multiWindows.load(std::memory_order_relaxed) &&') + r'''
    if (!pdev->display->multiWindows) {
        assert(hwc_layer->displayFrame.left == 376);
        assert(hwc_layer->displayFrame.right == 3463);
        assert(hwc_layer->sourceCropf.left == 376);
        assert(hwc_layer->sourceCropf.right == 3463);
        assert(hwc_layer->acquireFenceFd == 42);
    }
}
int main() {
    display d;
    // The untouched native mode still fits with letterbox.
    fit_guest_display_to_window(&d);
    assert(d.present_y > 0 && d.present_x == 0);
    // Android's 1800x1200 logical display projects into [376,0,3463,2058].
    d.logical_width = 1800; d.logical_height = 1200;
    auto frame = display_content_frame(&d);
    assert(frame.left == 376 && frame.right == 3463 && frame.bottom == 2058);
    fit_guest_display_to_window(&d);
    assert(std::abs(d.scale - 2.5725) < .001);
    assert(std::abs(d.present_x + 146) <= 1 && d.present_y == 0);
    // Physical frame -> host -> physical input, including cropped origin.
    double host_x = d.present_x + frame.left / d.scale;
    assert(std::abs(host_x) < 1);
    assert(std::abs((host_x - d.present_x) * d.scale - frame.left) < .001);
    device pdev{&d};
    hwc_layer_1 layer{HWC_FRAMEBUFFER_TARGET, 42, {0,0,3840,2058}, {0,0,0,0}};
    crop(&pdev, &layer);
    assert(layer.acquireFenceFd == -1 && layer.displayFrame.left == 0);
    layer.acquireFenceFd = 42;
    d.multiWindows = true;
    crop(&pdev, &layer);
    assert(layer.acquireFenceFd == 42); // freeform composition remains untouched
    // Tall/narrow projection and an exact physical aspect.
    d.logical_width = 900; d.logical_height = 1800;
    frame = display_content_frame(&d);
    assert(frame.right - frame.left == 1029 && frame.bottom == 2058);
    d.logical_width = 3840; d.logical_height = 2058;
    d.width = 2560; d.height = 1372;
    fit_guest_display_to_window(&d);
    assert(d.scale == 1.5 && d.present_x == 0 && d.present_y == 0);
}
'''
# The production crop descriptor lives in its enclosing function.
harness = harness.replace('void crop(device *pdev, hwc_layer_1 *hwc_layer) {',
                          'void crop(device *pdev, hwc_layer_1 *hwc_layer) { hwc_layer_1 cropped;')
worker = r"""
static thread_local bool t_is_resize_thread = false;
constexpr int kResizeSettleDefaultMs = 20;
int property_get_int32(const char *, int fallback) { return fallback; }
std::atomic<int> logical_calls{0}, physical_calls{0}, resized_w{0}, resized_h{0};
void resize_logical_display(display *, int w, int h) { resized_w=w; resized_h=h; ++logical_calls; }
void announce_display_size(display *, int, int) { ++physical_calls; }
""" + block(resize, 'static void\nresize_worker(') + '\n' + block(resize, 'void\ndisplay_resize_arm(') + '\n' + block(resize, 'void\ndisplay_resize_stop(')
harness = harness.replace('int main() {', worker + r"""
int main() {
    display scheduled;
    scheduled.resize_thread = std::thread(resize_worker, &scheduled);
    display_resize_arm(&scheduled, 1000, 600);
    display_resize_arm(&scheduled, 1200, 800);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    assert(logical_calls == 1 && physical_calls == 0);
    assert(resized_w == 1200 && resized_h == 800);
    display_resize_arm(&scheduled, 1200, 800);
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    assert(logical_calls == 1); // no feedback loop from repeated configures
    display_resize_arm(&scheduled, 0, 0);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    assert(logical_calls == 2 && physical_calls == 0 && resized_w == 0 && resized_h == 0);
    display_resize_stop(&scheduled);
""")
with tempfile.TemporaryDirectory(prefix='hwc-display-resize-') as tmp:
    cpp = Path(tmp) / 'check.cpp'
    cpp.write_text(harness)
    exe = Path(tmp) / 'check'
    subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', str(cpp), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print('PASS: logical projection, uniform fit, cropped client target and input mapping')
