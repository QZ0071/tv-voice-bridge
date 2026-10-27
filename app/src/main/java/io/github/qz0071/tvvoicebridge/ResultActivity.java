package io.github.qz0071.tvvoicebridge;

import android.app.Activity;
import android.content.*;
import android.os.Bundle;
import android.os.Handler;
import org.json.JSONObject;

public class ResultActivity extends Activity {
  public void onCreate(Bundle b) {
    super.onCreate(b);
    Intent original = getIntent();
    JSONObject params = null;
    try {
      params = new JSONObject(original.getData().getQueryParameter("params"));
    } catch (Exception ignored) {
    }
    finish();
    overridePendingTransition(0, 0);
    if (params == null) return;
    VoiceInputService service = VoiceInputService.instance;
    if (service != null && service.isDictationSession()) {
      // Dictation is accepted only from the existing local ASR subscription.
      // An exported deep link must not inject text into an input field.
      return;
    }
    if ("rocky_video_search".equals(params.optString("event"))) {
      String title = VoiceCommand.movieTitle(params);
      if (!title.isEmpty()) {
        new Handler().postDelayed(() -> MovieSearch.launch(getApplicationContext(), title), 150);
        return;
      }
    }
    // All other native assistant routes keep their original destination.
    try {
      Intent forward =
          new Intent(original)
              .setComponent(
                  new ComponentName(
                      "com.dangbei.leard.leradlauncher",
                      "com.dangbei.voice_business.VoiceCenterActivity"))
              .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
      forward.setFlags(forward.getFlags() & ~Intent.FLAG_ACTIVITY_CLEAR_TASK);
      startActivity(forward);
    } catch (Exception ignored) {
    }
  }

  static String movieTitle(JSONObject params) {
    try {
      JSONObject original = new JSONObject(params.optString("originalData"));
      JSONObject dm = original.optJSONObject("dm");
      JSONObject command = dm == null ? null : dm.optJSONObject("command");
      JSONObject fields = command == null ? null : command.optJSONObject("param");
      String title = fields == null ? "" : fields.optString("title").trim();
      if (!title.isEmpty()) return title;
    } catch (Exception ignored) {
    }
    String title = params.optString("title").trim();
    if (!title.isEmpty()) return title;
    return params
        .optString("input")
        .replaceFirst("^(我想看|我要看|我想观看|帮我搜索|帮我找|搜索|播放|看一下)\\s*", "")
        .trim();
  }
}
