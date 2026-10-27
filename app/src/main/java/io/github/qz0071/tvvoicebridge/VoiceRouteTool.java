package io.github.qz0071.tvvoicebridge;

import android.content.ComponentName;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.net.Uri;
import android.os.PatternMatcher;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

/** Package-manager operations executed with the existing authorized ADB shell identity. */
public final class VoiceRouteTool {
  public static void main(String[] args) throws Exception {
    Object manager =
        Class.forName("android.app.AppGlobals").getMethod("getPackageManager").invoke(null);
    Class<?> api = Class.forName("android.content.pm.IPackageManager");
    if (args.length > 0 && "clear".equals(args[0])) {
      for (Method method : api.getMethods()) {
        if (!method.getName().equals("clearPackagePreferredActivities")) continue;
        if (method.getParameterTypes().length == 1) method.invoke(manager, BridgeConfig.PACKAGE);
        else if (method.getParameterTypes().length == 2)
          method.invoke(manager, BridgeConfig.PACKAGE, 0);
        else continue;
        System.out.println("cleared");
        return;
      }
      throw new IllegalStateException("Unsupported package-manager clear API");
    }
    Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse("db_voice://db_launcher/control"));
    Method query =
        api.getMethod("queryIntentActivities", Intent.class, String.class, int.class, int.class);
    Object slice = query.invoke(manager, intent, null, PackageManager.MATCH_DEFAULT_ONLY, 0);
    @SuppressWarnings("unchecked")
    List<ResolveInfo> matches =
        (List<ResolveInfo>) slice.getClass().getMethod("getList").invoke(slice);
    List<ComponentName> components = new ArrayList<>();
    int bestMatch = 0;
    for (ResolveInfo match : matches) {
      components.add(new ComponentName(match.activityInfo.packageName, match.activityInfo.name));
      bestMatch = Math.max(bestMatch, match.match);
    }
    if (args.length == 0 || "describe".equals(args[0])) {
      System.out.println("handlers=" + components.size());
      return;
    }
    ComponentName selected = ComponentName.unflattenFromString(args[0]);
    if (!components.contains(selected))
      throw new IllegalArgumentException("Handler not in resolver results");
    IntentFilter filter = new IntentFilter(Intent.ACTION_VIEW);
    filter.addCategory(Intent.CATEGORY_DEFAULT);
    filter.addDataScheme("db_voice");
    filter.addDataAuthority("db_launcher", null);
    filter.addDataPath("/control", PatternMatcher.PATTERN_LITERAL);
    ComponentName[] set = components.toArray(new ComponentName[0]);
    for (Method method : api.getMethods()) {
      if (!method.getName().equals("addPreferredActivity")) continue;
      if (method.getParameterTypes().length == 5) {
        method.invoke(manager, filter, bestMatch, set, selected, 0);
      } else if (method.getParameterTypes().length == 6) {
        method.invoke(manager, filter, bestMatch, set, selected, 0, false);
      } else continue;
      System.out.println("preferred=" + selected.flattenToShortString());
      return;
    }
    throw new IllegalStateException("Unsupported package-manager preferred-activity API");
  }
}
