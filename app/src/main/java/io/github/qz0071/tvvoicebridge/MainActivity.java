package io.github.qz0071.tvvoicebridge;

import android.app.Activity;
import android.content.*;
import android.graphics.Color;
import android.os.Bundle;
import android.view.WindowManager;
import android.widget.*;

public class MainActivity extends Activity {
  TextView state;
  final BroadcastReceiver receiver =
      new BroadcastReceiver() {
        public void onReceive(Context c, Intent i) {
          state.setText(i.getStringExtra("message"));
        }
      };

  public void onCreate(Bundle b) {
    super.onCreate(b);
    LinearLayout root = new LinearLayout(this);
    root.setOrientation(1);
    root.setPadding(80, 45, 80, 35);
    root.setBackgroundColor(Color.rgb(12, 22, 38));
    TextView title = new TextView(this);
    title.setText("原生语音输入 · 复用投影仪识别引擎");
    title.setTextSize(29);
    title.setTextColor(Color.WHITE);
    root.addView(title);
    TextView info = new TextView(this);
    info.setText("选中输入框：按住麦克风键听写文字，说完松开。\n没有选中输入框：说‘我想看××’，打开影视仓搜索。其他指令保留原生助手。");
    info.setTextSize(20);
    info.setTextColor(0xffbac6d8);
    root.addView(info);
    EditText test = new EditText(this);
    test.setTextColor(Color.WHITE);
    test.setHintTextColor(0xff9eacc0);
    test.setTextSize(27);
    test.setHint("空白测试输入框");
    test.setSingleLine(true);
    root.addView(test, new LinearLayout.LayoutParams(-1, 100));
    state = new TextView(this);
    state.setTextColor(0xff60ded0);
    state.setTextSize(20);
    state.setText("正在连接原生语音服务…");
    root.addView(state);
    Button settings = new Button(this);
    settings.setText("无障碍服务设置");
    settings.setOnClickListener(
        v -> startActivity(new Intent(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS)));
    root.addView(settings);
    setContentView(root);
    test.requestFocus();
    getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_HIDDEN);
  }

  protected void onResume() {
    super.onResume();
    registerReceiver(receiver, new IntentFilter(VoiceInputService.STATUS));
    if (VoiceInputService.instance != null) state.setText(VoiceInputService.instance.status);
  }

  protected void onPause() {
    unregisterReceiver(receiver);
    super.onPause();
  }
}
