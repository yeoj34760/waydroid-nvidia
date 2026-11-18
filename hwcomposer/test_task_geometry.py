#!/usr/bin/env python3
"""Exercise patched task bounds, native geometry and layer placement on the host.

Usage: python3 hwcomposer/test_task_geometry.py PATCHED_HWC_TREE
"""
from pathlib import Path
import subprocess
import sys
import tempfile

from test_background_opacity import block


def main():
    root = Path(sys.argv[1]) / "hwcomposer"
    source = (root / "wayland-hwc.cpp").read_text()
    mode = (root / "modes/multi-window.cpp").read_text()
    harness = r"""
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <map>
#include <mutex>
#include <set>
#include <string>
#include <thread>
#include <vector>
struct hwc_rect_t { int left, top, right, bottom; };
struct layerFrame { int x, y; double scale_x = 0, scale_y = 0; };
struct wl_surface {};
struct wp_viewport {};
struct xdg_surface {};
struct wl_buffer {};
struct window;
struct open_windows {
    std::map<std::string, window *> entries;
    template<class F> void erase_if(F predicate) {
        for (auto it = entries.begin(); it != entries.end();) {
            if (predicate(*it)) it = entries.erase(it);
            else ++it;
        }
    }
};
struct display {
    bool wantDecorations = true;
    bool resizeFollowsWindow = false, resizeUsesReconnect = false;
    std::atomic<bool> multiWindows{true};
    double scale = 2, output_scale = 2;
    int present_x = 0, present_y = 0;
    int width = 1920, height = 1080;
    std::map<wl_surface *, layerFrame> layers;
    open_windows windows;
    std::set<std::string> ignored_apps;
};
struct window {
    struct display *display;
    std::string taskID;
    std::mutex content_mutex;
    hwc_rect_t content_frame{};
    int host_width = 0, host_height = 0;
    std::thread task_resize_thread;
    std::condition_variable task_resize_cond;
    bool task_resize_quit = false, task_resize_pending = false;
    std::chrono::steady_clock::time_point task_resize_deadline;
    std::chrono::steady_clock::time_point task_relayout_deadline{};
    std::atomic<int> resize_count{0}, resized_width{0}, resized_height{0};
    struct xdg_surface *xdg_surface = nullptr;
    bool dedicated_background_surface = true;
    wp_viewport *viewport = nullptr;
    wl_surface *surface = nullptr;
    wl_buffer *bg_buffer = nullptr;
    bool uses_task_geometry() const;
    bool awaiting_task_relayout();
    void set_content_frame(hwc_rect_t);
    hwc_rect_t task_layer_frame(hwc_rect_t);
    void configure_task(int, int);
    void stop_task_resize();
    void resize_task(int w, int h) { resized_width = w; resized_height = h; ++resize_count; }
    ~window() { stop_task_resize(); }
};
int native_w, native_h, background_w, background_h;
std::atomic<int> refreshes{0};
void request_refresh(display *) { ++refreshes; }
int background_attaches = 0;
void wl_surface_attach(wl_surface *, wl_buffer *, int, int) { ++background_attaches; }
void xdg_surface_set_window_geometry(xdg_surface *, int x, int y, int w, int h) {
    assert(x == 0 && y == 0); native_w = w; native_h = h;
}
void wp_viewport_set_destination(wp_viewport *, int w, int h) {
    background_w = w; background_h = h;
}
enum class LayerSplitType { TID, RawName, Empty };
struct info { LayerSplitType type; std::string tid; const std::string &key() const { return tid; } };
struct hwc_layer_1 { int compositionType, flags; void *handle; hwc_rect_t displayFrame; };
constexpr int HWC_IS_CURSOR_LAYER = 1;
struct hwc_display_contents_1_t { hwc_layer_1 *hwLayers; size_t numHwLayers; };
struct waydroid_hwc_composer_device_1 { struct display *display; };
struct split_layer_names_helper {
    std::vector<info> values;
    info &operator[](size_t i) { return values.at(i); }
    void setup(waydroid_hwc_composer_device_1 *, hwc_layer_1 *, size_t) {}
};
void display_resize_arm(display *, int, int) {}
struct multi_window_mode {
    split_layer_names_helper layer_infos;
    std::map<std::string, hwc_rect_t> content_frames;
    static bool can_handle_layer(const hwc_layer_1 &l) { return l.compositionType == 1; }
    int setup_set(waydroid_hwc_composer_device_1 *, hwc_display_contents_1_t *);
    int cleanup_stale_windows(waydroid_hwc_composer_device_1 *, hwc_display_contents_1_t *);
};
"""
    harness += block(source, "bool window::uses_task_geometry() const") + "\n"
    harness += block(source, "bool window::awaiting_task_relayout()") + "\n"
    harness += block(source, "void window::set_content_frame(hwc_rect_t frame)") + "\n"
    harness += block(mode, "int multi_window_mode::setup_set(") + "\n"
    harness += block(mode, "int multi_window_mode::cleanup_stale_windows(") + "\n"
    harness += block(source, "void window::configure_task(") + "\n"
    harness += block(source, "void window::stop_task_resize()") + "\n"
    harness += block(source, "hwc_rect_t window::task_layer_frame(") + "\n"
    harness += block(source, "static void transform_input_coordinates(") + "\n"
    harness += "void map_background(window *window) {\n" + block(
        source, "if (!window->uses_task_geometry())") + "\n}\n"
    harness += r"""
void await_resize(window &w, int count) {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    while (w.resize_count < count && std::chrono::steady_clock::now() < deadline)
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    assert(w.resize_count == count);
}
int main() {
    display d;
    waydroid_hwc_composer_device_1 pdev{&d};
    void *handle = &d;
    hwc_layer_1 layers[] = {
        {1, 0, handle, {1200, 500, 1800, 1500}},
        {1, 0, handle, {1700, 700, 1900, 900}}, // same task popup
        {1, 0, handle, {20, 40, 420, 840}},   // another task
        {1, HWC_IS_CURSOR_LAYER, handle, {0, 0, 32, 32}},
        {0, 0, handle, {0, 0, 3840, 2160}}   // client target
    };
    hwc_display_contents_1_t contents{layers, 5};
    multi_window_mode mode;
    mode.layer_infos.values = {{LayerSplitType::TID, "13"}, {LayerSplitType::TID, "13"},
        {LayerSplitType::TID, "14"}, {LayerSplitType::TID, "13"}, {LayerSplitType::Empty, ""}};
    mode.setup_set(&pdev, &contents);
    assert(mode.content_frames.size() == 2);
    auto frame = mode.content_frames.at("13");
    assert(frame.left == 1200 && frame.top == 500 && frame.right == 1900 && frame.bottom == 1500);
    // Bounds belong to this frame, not the union of every previous frame.
    // Shrink/move a task after maximizing it and remove the other task.
    layers[0].displayFrame = {100, 200, 500, 800};
    layers[1].handle = nullptr;
    layers[2].handle = nullptr;
    mode.setup_set(&pdev, &contents);
    assert(mode.content_frames.size() == 1);
    auto current = mode.content_frames.at("13");
    assert(current.left == 100 && current.top == 200 && current.right == 500 && current.bottom == 800);
    // A closed task must not leave bounds behind when its window is recreated.
    layers[0].handle = nullptr;
    mode.setup_set(&pdev, &contents);
    assert(mode.content_frames.empty());
    layers[0].handle = handle;
    mode.setup_set(&pdev, &contents);
    window reopened{&d, "13"};
    xdg_surface reopened_xdg;
    wl_buffer background;
    reopened.xdg_surface = &reopened_xdg;
    reopened.bg_buffer = &background;
    map_background(&reopened);
    assert(background_attaches == 0); // no display-sized map before the first task frame
    reopened.set_content_frame(mode.content_frames.at("13"));
    assert(native_w == 200 && native_h == 300);
    assert(background_attaches == 1);
    reopened.set_content_frame(mode.content_frames.at("13"));
    assert(background_attaches == 1); // attach once, with the first task frame
    window w{&d, "13"};
    xdg_surface xdg; wp_viewport viewport; wl_surface surface;
    w.xdg_surface = &xdg; w.viewport = &viewport; w.surface = &surface;
    w.set_content_frame(frame);
    assert(native_w == 350 && native_h == 500);
    assert(background_w == native_w && background_h == native_h);
    assert(d.layers.at(&surface).x == 1200 && d.layers.at(&surface).y == 500);
    auto positioned = w.task_layer_frame(layers[1].displayFrame);
    assert(positioned.left == 250 && positioned.top == 100);
    w.configure_task(350, 500); assert(w.resize_count == 0);
    assert(!w.awaiting_task_relayout());
    w.configure_task(700, 500);
    assert(w.awaiting_task_relayout()); // keep the same toplevel through missing task layers
    d.windows.entries["13"] = &w;
    hwc_display_contents_1_t gap{nullptr, 0};
    mode.cleanup_stale_windows(&pdev, &gap);
    assert(d.windows.entries.at("13") == &w);
    mode.cleanup_stale_windows(&pdev, &contents);
    assert(d.windows.entries.at("13") == &w); // returning task keeps identity
    // Old Android frames cannot snap an interactive native resize back.
    w.set_content_frame(frame);
    assert(native_w == 700 && native_h == 500);
    // A wider host window must not stretch the old portrait buffer sideways.
    auto preview = w.task_layer_frame(frame);
    assert(preview.left == 175 && preview.right == 525 && preview.top == 0 && preview.bottom == 500);
    positioned = w.task_layer_frame(layers[1].displayFrame);
    assert(positioned.left == 425 && positioned.top == 100);
    int x = 200, y = 20;
    transform_input_coordinates(&d, &surface, x, y);
    assert(x == 1250 && y == 540); // inverse of the fitted parent viewport
    await_resize(w, 1);
    assert(w.resized_width == 700 && w.resized_height == 500);
    // Matching new buffers must keep the compositor's chosen size.
    w.set_content_frame({1200, 500, 2600, 1500});
    assert(native_w == 700 && native_h == 500);
    w.configure_task(700, 500); assert(w.resize_count == 1);
    w.configure_task(1920, 1080);
    w.configure_task(1920, 1080);
    w.configure_task(400, 600);
    await_resize(w, 2); // coalesce a burst, including a non-interactive/tiled resize
    assert(w.resized_width == 400 && w.resized_height == 600);
    assert(w.awaiting_task_relayout());
    // Expiry must request a frame even when Android has stopped drawing.
    {
        std::scoped_lock lock(w.content_mutex);
        w.task_relayout_deadline = std::chrono::steady_clock::now();
        w.task_resize_cond.notify_one();
    }
    const auto expiry = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    while (!refreshes && std::chrono::steady_clock::now() < expiry)
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    assert(refreshes == 1 && !w.awaiting_task_relayout());
    mode.cleanup_stale_windows(&pdev, &gap);
    assert(d.windows.entries.empty()); // a truly closed task is eventually removed
    // Non-task surfaces retain the original display-scale mapping.
    d.layers[&surface] = {10, 20}; x = 5; y = 8;
    transform_input_coordinates(&d, &surface, x, y);
    assert(x == 20 && y == 36);
    w.taskID = "0"; assert(!w.uses_task_geometry());
    w.taskID = "none"; assert(!w.uses_task_geometry());
    w.taskID = "13"; d.multiWindows = false; assert(!w.uses_task_geometry());
    d.multiWindows = true; d.wantDecorations = false; assert(!w.uses_task_geometry());
    map_background(&w);
    assert(background_attaches == 2); // preserve bootstrap for other window modes
}
"""
    with tempfile.TemporaryDirectory(prefix="hwc-task-") as tmp:
        cpp = Path(tmp) / "check.cpp"
        exe = Path(tmp) / "check"
        cpp.write_text(harness)
        subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        "-Wno-missing-field-initializers", str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
    print("PASS: separate task bounds, SSD/background size and local layer placement")


if __name__ == "__main__":
    main()
