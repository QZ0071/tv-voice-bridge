package io.github.qz0071.tvvoicebridge;

import java.lang.reflect.Field;

/** Read-only by default; --disconnect restores this board's input route after rollback. */
public final class AudioRouteProbe {
  public static void main(String[] args) throws Exception {
    if (android.os.Build.VERSION.SDK_INT != 28
        || !"marconi".equals(android.os.Build.DEVICE)
        || !"HQK1Pro".equals(android.os.Build.MODEL)) {
      throw new IllegalStateException("Audio workaround is limited to the validated board");
    }
    Field field =
        Class.forName("android.media.IAudioService$Stub")
            .getDeclaredField("TRANSACTION_setWiredDeviceConnectionState");
    field.setAccessible(true);
    if (args.length == 1 && "--disconnect".equals(args[0])) {
      android.os.IBinder binder =
          (android.os.IBinder)
              Class.forName("android.os.ServiceManager")
                  .getMethod("getService", String.class)
                  .invoke(null, "audio");
      android.os.Parcel request = android.os.Parcel.obtain(), reply = android.os.Parcel.obtain();
      try {
        request.writeInterfaceToken("android.media.IAudioService");
        request.writeInt(0x80000010);
        request.writeInt(0);
        request.writeString("");
        request.writeString("ble_audio");
        request.writeString("tv-voice-bridge-restore");
        binder.transact(field.getInt(null), request, reply, 0);
        reply.readException();
      } finally {
        request.recycle();
        reply.recycle();
      }
    }
    System.out.println("{\"wiredTransaction\":" + field.getInt(null) + "}");
  }
}
