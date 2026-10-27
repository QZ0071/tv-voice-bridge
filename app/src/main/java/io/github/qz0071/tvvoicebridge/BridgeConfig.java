package io.github.qz0071.tvvoicebridge;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.JSONObject;

/** Deployment settings contain component names, never service credentials. */
final class BridgeConfig {
  static final String PACKAGE = "io.github.qz0071.tvvoicebridge";
  static final String STATUS = PACKAGE + ".STATUS";
  static final String NATIVE_PACKAGE = "com.dangbei.lerad.rocky";
  static final String NATIVE_HANDLER = "com.dangbei.voice_business.VoiceCenterActivity";
  final SharedPreferences prefs;

  BridgeConfig(Context context) {
    prefs = context.getSharedPreferences("deployment", Context.MODE_PRIVATE);
  }

  boolean configured() {
    return prefs.getBoolean("configured", false);
  }

  int port() {
    return prefs.getInt("busPort", 50001);
  }

  String targetPackage() {
    return prefs.getString("targetPackage", "com.huawei.himovceie");
  }

  String homeActivity() {
    return prefs.getString("homeActivity", "com.github.tvbox.osc.ui.activity.HomeActivity");
  }

  String searchReceiver() {
    return prefs.getString("searchReceiver", "com.github.tvbox.osc.receiver.SearchReceiver");
  }

  String searchAction() {
    return prefs.getString("searchAction", "android.content.movie.search.Action");
  }

  String searchExtra() {
    return prefs.getString("searchExtra", "title");
  }

  int searchDelay() {
    return prefs.getInt("searchDelayMs", 5000);
  }

  int audioTransaction() {
    return prefs.getInt("audioTransaction", 0);
  }

  String profile() {
    return prefs.getString("profile", "");
  }

  void save(JSONObject json) throws Exception {
    String profile = json.getString("profile");
    if (!profile.equals("haqu-k1-pro") && !profile.equals("dangbei-dds-candidate")) {
      throw new IllegalArgumentException("Unknown adapter");
    }
    int port = json.optInt("busPort", 50001);
    int delay = json.optInt("searchDelayMs", 5000);
    int transaction = json.optInt("audioTransaction", 0);
    if (port < 1024
        || port > 65535
        || delay < 1000
        || delay > 15000
        || transaction < 0
        || transaction > 1000) {
      throw new IllegalArgumentException("Configuration outside supported bounds");
    }
    SharedPreferences.Editor out = prefs.edit();
    out.putString("profile", profile)
        .putInt("busPort", port)
        .putInt("searchDelayMs", delay)
        .putInt("audioTransaction", transaction);
    for (String key :
        new String[] {
          "targetPackage", "homeActivity", "searchReceiver", "searchAction", "searchExtra"
        }) {
      String value = json.getString(key);
      if (value.length() > 200 || !value.matches("[A-Za-z_][A-Za-z0-9_.]*")) {
        throw new IllegalArgumentException("Invalid " + key);
      }
      out.putString(key, value);
    }
    if (!out.putBoolean("configured", true).commit())
      throw new IllegalStateException("Save failed");
  }
}
