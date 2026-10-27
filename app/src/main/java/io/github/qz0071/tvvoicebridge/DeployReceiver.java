package io.github.qz0071.tvvoicebridge;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.SystemClock;
import org.json.JSONObject;

/** The manifest requires DUMP: ordinary third-party apps cannot reconfigure the bridge. */
public final class DeployReceiver extends BroadcastReceiver {
  static volatile long chooseHandlerUntil;

  @Override
  public void onReceive(Context context, Intent intent) {
    try {
      if ((BridgeConfig.PACKAGE + ".CONFIGURE").equals(intent.getAction())) {
        new BridgeConfig(context).save(new JSONObject(intent.getStringExtra("json")));
        setResultCode(0);
        setResultData("configured");
      } else if ((BridgeConfig.PACKAGE + ".CHOOSE_HANDLER").equals(intent.getAction())) {
        chooseHandlerUntil = SystemClock.elapsedRealtime() + 20000;
        setResultCode(0);
        setResultData("chooser-enabled");
      } else {
        setResultCode(1);
        setResultData("unsupported-action");
      }
    } catch (Exception error) {
      setResultCode(1);
      setResultData("configuration-rejected");
    }
  }
}
