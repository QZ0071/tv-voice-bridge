package io.github.qz0071.tvvoicebridge;

import org.json.JSONObject;

final class VoiceCommand {
  static boolean shouldDictate(boolean inputSession, long elapsedMs) {
    return inputSession && elapsedMs >= 0 && elapsedMs < 20000;
  }

  static String movieTitle(JSONObject params) {
    try {
      Object raw = params.opt("originalData");
      JSONObject original =
          raw instanceof JSONObject ? (JSONObject) raw : new JSONObject(String.valueOf(raw));
      JSONObject dm = original.optJSONObject("dm");
      JSONObject command = dm == null ? null : dm.optJSONObject("command");
      JSONObject fields = command == null ? null : command.optJSONObject("param");
      String title = fields == null ? "" : fields.optString("title").trim();
      if (!title.isEmpty()) return bounded(title);
    } catch (Exception ignored) {
    }
    String title = params.optString("title").trim();
    if (!title.isEmpty()) return bounded(title);
    return bounded(
        params
            .optString("input")
            .replaceFirst("^(我想看|我要看|我想观看|帮我搜索|帮我找|搜索|播放|看一下)\\s*", "")
            .trim());
  }

  static String bounded(String text) {
    return text.length() > 200 ? text.substring(0, 200) : text;
  }
}
