package dev.waydroid.ssd;

/** Changes the logical display on stock composer HALs, without a physical reconnect. */
public final class DisplayResize {
    public static void main(String[] args) {
        try {
            if (args.length != 2) {
                throw new IllegalArgumentException("Expected width and height (0 0 resets)");
            }
            int width = Integer.parseInt(args[0]);
            int height = Integer.parseInt(args[1]);
            if ((width != 0 || height != 0) && (width < 200 || height < 200)) {
                throw new IllegalArgumentException("Invalid display size");
            }
            Object service = Class.forName("android.view.WindowManagerGlobal")
                    .getMethod("getWindowManagerService").invoke(null);
            Class<?> api = Class.forName("android.view.IWindowManager");
            if (width == 0 && height == 0) {
                api.getMethod("clearForcedDisplaySize", int.class).invoke(service, 0);
            } else {
                api.getMethod("setForcedDisplaySize", int.class, int.class, int.class)
                        .invoke(service, 0, width, height);
            }
        } catch (Exception error) {
            error.printStackTrace();
            System.exit(1);
        }
    }
}
