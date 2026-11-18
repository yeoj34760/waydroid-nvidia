#!/usr/bin/env python3
"""Run the patched layer-name routing on the host: TEST PATCHED_HWC_TREE."""
from pathlib import Path
import subprocess
import sys
import tempfile

from test_background_opacity import block


def main():
    source = (Path(sys.argv[1]) / "hwcomposer/modes/waydroid_mode.cpp").read_text()
    harness = r"""
#include <cassert>
#include <string>
#include <vector>
constexpr int HWC_FRAMEBUFFER_TARGET = 3;
struct hwc_layer_1 { int compositionType = 1; };
struct display { std::vector<std::string> layer_names; };
struct waydroid_hwc_composer_device_1 { struct display *display; };
enum class LayerSplitType { TID, RawName, Empty };
struct layer_info {
    LayerSplitType type;
    std::string aid, tid, component;
};
class split_layer_names_helper {
    std::vector<layer_info> layer_infos;
    static layer_info split_layer_name(const std::string &);
public:
    void setup(waydroid_hwc_composer_device_1 *, const hwc_layer_1 *, size_t);
    layer_info &operator[](size_t i) { return layer_infos.at(i); }
    size_t size() const { return layer_infos.size(); }
};
"""
    harness += block(source, "layer_info split_layer_names_helper::split_layer_name(")
    harness += block(source, "void split_layer_names_helper::setup(")
    harness += r"""
int main() {
    display d{{"com.android.chrome/ChromeChildSurface#190",
               "TID:54#com.android.chrome/com.google.android.apps.chrome.Main#180",
               "TID:54#com.android.chrome/Background#176",
               "TID:52#com.android.vending/Main#192",
               "InputMethod#42", "com.android.chromex/Other#1", "stale-target"}};
    hwc_layer_1 layers[7];
    layers[6].compositionType = HWC_FRAMEBUFFER_TARGET;
    waydroid_hwc_composer_device_1 pdev{&d};
    split_layer_names_helper helper;
    helper.setup(&pdev, layers, 7);
    assert(helper[0].type == LayerSplitType::TID);
    assert(helper[0].tid == "54" && helper[0].aid == "com.android.chrome");
    assert(helper[0].component == "ChromeChildSurface");
    assert(helper[1].tid == "54" && helper[3].tid == "52");
    assert(helper[4].type == LayerSplitType::RawName && helper[4].aid == "InputMethod");
    assert(helper[5].type == LayerSplitType::RawName); // exact package match
    assert(helper[6].type == LayerSplitType::Empty);
    // Another task for the same package makes inference unsafe, in any order.
    d.layer_names[2] = "TID:55#com.android.chrome/OtherActivity#200";
    helper.setup(&pdev, layers, 7);
    assert(helper.size() == 7 && helper[0].type == LayerSplitType::RawName);
    assert(helper[1].tid == "54" && helper[2].tid == "55");
    // Do not keep an owner from a previous frame after its task disappears.
    d.layer_names = {"com.android.chrome/ChromeChildSurface#201"};
    helper.setup(&pdev, layers, 1);
    assert(helper.size() == 1 && helper[0].type == LayerSplitType::RawName);
}
"""
    with tempfile.TemporaryDirectory(prefix="hwc-child-") as tmp:
        cpp = Path(tmp) / "check.cpp"
        exe = Path(tmp) / "check"
        cpp.write_text(harness)
        subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        "-Wno-missing-field-initializers", str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
    print("PASS: untagged child routing, ambiguous tasks, system layers and frame reuse")


if __name__ == "__main__":
    main()
