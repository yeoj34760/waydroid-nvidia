package dev.waydroid.ssd;

/** Runs as the composer's system UID; Binder shellCommand only accepts root/shell. */
public final class TaskResize {
    public static void main(String[] args) {
        try {
            if (args.length != 5) {
                throw new IllegalArgumentException("Expected task ID, left, top, right, bottom");
            }
            int task = Integer.parseInt(args[0]);
            int left = Integer.parseInt(args[1]);
            int top = Integer.parseInt(args[2]);
            int right = Integer.parseInt(args[3]);
            int bottom = Integer.parseInt(args[4]);
            if (task <= 0 || left < 0 || top < 0 || right <= left || bottom <= top) {
                throw new IllegalArgumentException("Invalid task or bounds");
            }
            // These are Android 13 framework APIs, absent from the public SDK.
            Class<?> rect = Class.forName("android.graphics.Rect");
            Object bounds = rect.getConstructor(int.class, int.class, int.class, int.class)
                    .newInstance(left, top, right, bottom);
            Object service = Class.forName("android.app.ActivityTaskManager")
                    .getMethod("getService").invoke(null);
            Class.forName("android.app.IActivityTaskManager")
                    .getMethod("resizeTask", int.class, rect, int.class)
                    .invoke(service, task, bounds, 0);
        } catch (Exception error) {
            error.printStackTrace();
            System.exit(1);
        }
    }
}
