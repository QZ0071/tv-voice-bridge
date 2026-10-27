package io.github.qz0071.tvvoicebridge;

import android.content.*;
import android.os.*;
import android.util.Log;
import android.widget.Toast;

final class MovieSearch {
  static long launchedAt, generation;
  static String lastTitle = "";

  static void launch(Context context, String title) {
    long now = SystemClock.elapsedRealtime();
    if (title.equals(lastTitle) && now - launchedAt < 7000) return;
    Context app = context.getApplicationContext();
    BridgeConfig config = new BridgeConfig(app);
    if (!config.configured()) return;
    Intent home =
        new Intent()
            .setComponent(new ComponentName(config.targetPackage(), config.homeActivity()))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
    try {
      app.startActivity(home);
      lastTitle = title;
      launchedAt = now;
      Toast.makeText(app, "正在影视仓搜索：" + title, Toast.LENGTH_LONG).show();
      long request = ++generation;
      new Handler(Looper.getMainLooper())
          .postDelayed(
              () -> {
                if (request != generation) return;
                Intent search =
                    new Intent(config.searchAction())
                        .setComponent(
                            new ComponentName(config.targetPackage(), config.searchReceiver()))
                        .putExtra(config.searchExtra(), title);
                try {
                  app.sendBroadcast(search);
                  Log.i("TVVoiceBridge", "Movie search dispatched; characters=" + title.length());
                } catch (Exception error) {
                  Log.e("TVVoiceBridge", "Search receiver rejected request", error);
                  Toast.makeText(app, "目标应用不支持配置的搜索接口", Toast.LENGTH_LONG).show();
                }
              },
              config.searchDelay());
    } catch (Exception e) {
      Log.e("NativeVoice", "unable to open movie search", e);
      Toast.makeText(app, "无法打开影视仓，请确认已安装", Toast.LENGTH_LONG).show();
    }
  }
}
