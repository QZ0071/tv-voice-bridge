package io.github.qz0071.tvvoicebridge;

import android.accessibilityservice.AccessibilityService;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.Parcel;
import android.os.SystemClock;
import android.util.Log;
import android.view.Gravity;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import android.widget.TextView;
import java.util.List;
import org.json.JSONObject;

/** Passive native-ASR subscriber. It never records audio or starts/stops the ASR engine. */
public class VoiceInputService extends AccessibilityService {
  static final String STATUS = BridgeConfig.STATUS;
  static VoiceInputService instance;
  final Handler main = new Handler(Looper.getMainLooper());
  String status = "请先运行电脑端部署脚本";
  NativeBus bus;
  boolean ready, armed, inputSession, receiverRegistered, destroyed, choosingHandler;
  long session, voiceStarted;
  AccessibilityNodeInfo target;
  String previous = "";
  int selectionStart, selectionEnd;
  TextView overlay;
  WindowManager windows;

  final BroadcastReceiver keys =
      new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
          if ("com.dangbei.voicekey.down".equals(intent.getAction())) begin();
          else if (armed) report("正在识别，请稍候…", true);
        }
      };

  boolean isDictationSession() {
    return VoiceCommand.shouldDictate(inputSession, SystemClock.elapsedRealtime() - voiceStarted);
  }

  @Override
  protected void onServiceConnected() {
    instance = this;
    windows = (WindowManager) getSystemService(WINDOW_SERVICE);
    BridgeConfig config = new BridgeConfig(this);
    if (!config.configured()) {
      report(status, false);
      return;
    }
    ensureRemoteInput(config);
    NotificationManager notifications =
        (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
    notifications.createNotificationChannel(
        new NotificationChannel("voice", "TV语音桥", NotificationManager.IMPORTANCE_LOW));
    startForeground(
        5,
        new Notification.Builder(this, "voice")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentTitle("TV语音桥已启用")
            .setContentText("输入框听写 / 原生助手影片搜索分流")
            .build());
    bus =
        new NativeBus(
            config.port(),
            new NativeBus.Listener() {
              @Override
              public void state(boolean connected) {
                main.post(
                    () -> {
                      if (destroyed) return;
                      ready = connected;
                      report(connected ? "已就绪：原生语音双模式" : "正在连接原生语音服务…", false);
                    });
              }

              @Override
              public void event(String topic, String payload) {
                try {
                  JSONObject data = new JSONObject(payload);
                  if ("asr.speech.result".equals(topic)) {
                    String result = data.optString("text");
                    main.post(() -> acceptResult(result));
                  } else if ("asr.speech.text".equals(topic)) {
                    String partial = data.optString("var");
                    main.post(
                        () -> {
                          if (armed && !partial.isEmpty()) report("听写：" + partial, true);
                        });
                  } else if ("sys.dialog.error".equals(topic)) {
                    main.post(
                        () -> {
                          if (armed) {
                            armed = false;
                            report("原生识别失败，请重试", true);
                          }
                        });
                  }
                } catch (Exception ignored) {
                  Log.w("TVVoiceBridge", "Invalid local engine event");
                }
              }
            });
    bus.start();
    IntentFilter filter = new IntentFilter("com.dangbei.voicekey.down");
    filter.addAction("com.dangbei.voicekey.up");
    registerReceiver(keys, filter);
    receiverRegistered = true;
  }

  void ensureRemoteInput(BridgeConfig config) {
    // Never apply the board-specific audio workaround to an unverified TV.
    if (!"haqu-k1-pro".equals(config.profile())
        || config.audioTransaction() <= 0
        || Build.VERSION.SDK_INT != 28
        || !"marconi".equals(Build.DEVICE)
        || !"HQK1Pro".equals(Build.MODEL)) return;
    try {
      IBinder binder =
          (IBinder)
              Class.forName("android.os.ServiceManager")
                  .getMethod("getService", String.class)
                  .invoke(null, "audio");
      if (!"android.media.IAudioService".equals(binder.getInterfaceDescriptor())) return;
      Parcel request = Parcel.obtain(), reply = Parcel.obtain();
      try {
        request.writeInterfaceToken("android.media.IAudioService");
        request.writeInt(0x80000010); // Existing BLE remote input, not an output device.
        request.writeInt(1);
        request.writeString("");
        request.writeString("ble_audio");
        request.writeString(getPackageName());
        binder.transact(config.audioTransaction(), request, reply, 0);
        reply.readException();
      } finally {
        request.recycle();
        reply.recycle();
      }
    } catch (Exception error) {
      Log.e("TVVoiceBridge", "Remote input route unavailable", error);
    }
  }

  AccessibilityNodeInfo findInput() {
    for (AccessibilityWindowInfo window : getWindows()) {
      if (window.getType() != AccessibilityWindowInfo.TYPE_APPLICATION) continue;
      AccessibilityNodeInfo root = window.getRoot();
      if (root == null) continue;
      AccessibilityNodeInfo node = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
      if (node != null && node.isEditable()) return node;
    }
    return null;
  }

  String actualText(AccessibilityNodeInfo node) {
    return node.isShowingHintText() || node.getText() == null ? "" : node.getText().toString();
  }

  void begin() {
    if (target != null) target.recycle();
    target = findInput();
    inputSession = target != null;
    voiceStarted = SystemClock.elapsedRealtime();
    long token = ++session;
    armed = inputSession && !target.isPassword() && ready;
    if (armed) {
      previous = actualText(target);
      selectionStart = target.getTextSelectionStart();
      selectionEnd = target.getTextSelectionEnd();
      report("正在听写…", true);
    } else if (inputSession) {
      report(target.isPassword() ? "密码框不参与语音回填" : "语音服务尚未连接，请稍候", true);
    } else {
      main.removeCallbacks(hide);
      hide.run();
    }
    main.postDelayed(
        () -> {
          if (session == token && armed) {
            armed = false;
            report("本次听写超时，请重试", true);
          }
        },
        15000);
  }

  void acceptResult(String result) {
    if (destroyed || !armed || target == null || result.trim().isEmpty()) return;
    armed = false;
    long token = session;
    String value = VoiceCommand.bounded(result.trim());
    main.postDelayed(
        () -> {
          if (!destroyed && session == token) fill(value);
        },
        300);
  }

  void fill(String value) {
    if (target == null || !target.refresh()) {
      report("输入框已关闭", true);
      return;
    }
    AccessibilityNodeInfo current = findInput();
    if (current == null || current.getWindowId() != target.getWindowId()) {
      report("输入框已切换，未自动填入", true);
      return;
    }
    String text = actualText(target);
    if (!previous.equals(text)) {
      report("内容已变化，请重新听写", true);
      return;
    }
    int start =
        Math.max(0, Math.min(selectionStart < 0 ? text.length() : selectionStart, text.length()));
    int end = Math.max(start, Math.min(selectionEnd < 0 ? start : selectionEnd, text.length()));
    Bundle change = new Bundle();
    change.putCharSequence(
        AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
        text.substring(0, start) + value + text.substring(end));
    boolean inserted = target.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, change);
    if (inserted) {
      Bundle cursor = new Bundle();
      cursor.putInt(
          AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, start + value.length());
      cursor.putInt(
          AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, start + value.length());
      target.performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, cursor);
    }
    Log.i("TVVoiceBridge", "Dictation characters=" + value.length() + "; inserted=" + inserted);
    report(inserted ? "已填入：" + value : "此输入框不支持文字回填", true);
  }

  void report(String message, boolean visible) {
    if (destroyed) return;
    status = message;
    sendBroadcast(new Intent(STATUS).setPackage(getPackageName()).putExtra("message", message));
    if (!visible) return;
    if (overlay == null) {
      overlay = new TextView(this);
      overlay.setTextColor(-1);
      overlay.setTextSize(22);
      overlay.setPadding(30, 20, 30, 20);
      overlay.setBackgroundColor(0xee163447);
      WindowManager.LayoutParams layout =
          new WindowManager.LayoutParams(
              -2,
              -2,
              WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
              WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                  | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE,
              -3);
      layout.gravity = Gravity.TOP | Gravity.CENTER_HORIZONTAL;
      layout.y = 50;
      windows.addView(overlay, layout);
    }
    overlay.setText(message);
    main.removeCallbacks(hide);
    if (!armed) main.postDelayed(hide, 4500);
  }

  final Runnable hide =
      () -> {
        if (overlay != null) {
          try {
            windows.removeView(overlay);
          } catch (Exception ignored) {
          }
          overlay = null;
        }
      };

  @Override
  public void onAccessibilityEvent(AccessibilityEvent event) {
    if (choosingHandler
        || SystemClock.elapsedRealtime() > DeployReceiver.chooseHandlerUntil
        || !"android".contentEquals(event.getPackageName() == null ? "" : event.getPackageName()))
      return;
    AccessibilityNodeInfo root = getRootInActiveWindow();
    if (root == null
        || root.findAccessibilityNodeInfosByViewId("android:id/resolver_list").isEmpty()) return;
    List<AccessibilityNodeInfo> labels = root.findAccessibilityNodeInfosByText("TV语音桥");
    if (labels.isEmpty()) return;
    AccessibilityNodeInfo item = labels.get(0);
    while (item != null && !item.isClickable()) item = item.getParent();
    if (item == null || !item.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return;
    choosingHandler = true;
    main.postDelayed(
        () -> {
          AccessibilityNodeInfo screen = getRootInActiveWindow();
          if (screen != null && "android".contentEquals(screen.getPackageName())) {
            List<AccessibilityNodeInfo> buttons =
                screen.findAccessibilityNodeInfosByViewId("android:id/button_always");
            if (!buttons.isEmpty()
                && buttons.get(0).isEnabled()
                && buttons.get(0).performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
              DeployReceiver.chooseHandlerUntil = 0;
            }
          }
          choosingHandler = false;
        },
        200);
  }

  @Override
  public void onInterrupt() {
    armed = false;
  }

  @Override
  public void onDestroy() {
    destroyed = true;
    armed = false;
    main.removeCallbacksAndMessages(null);
    hide.run();
    if (receiverRegistered)
      try {
        unregisterReceiver(keys);
      } catch (Exception ignored) {
      }
    if (bus != null) bus.close();
    if (target != null) target.recycle();
    instance = null;
    super.onDestroy();
  }
}
