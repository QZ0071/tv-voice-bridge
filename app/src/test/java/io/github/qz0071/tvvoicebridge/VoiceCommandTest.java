package io.github.qz0071.tvvoicebridge;

import static org.junit.Assert.*;

import org.json.JSONObject;
import org.junit.Test;

public class VoiceCommandTest {
  @Test
  public void nativeSemanticTitleTakesPrecedenceOverSpokenPrefix() throws Exception {
    JSONObject nativeData =
        new JSONObject()
            .put(
                "dm",
                new JSONObject()
                    .put(
                        "command",
                        new JSONObject().put("param", new JSONObject().put("title", "熊出没"))));
    JSONObject params =
        new JSONObject().put("input", "我想看熊出没").put("originalData", nativeData.toString());
    assertEquals("熊出没", VoiceCommand.movieTitle(params));
  }

  @Test
  public void malformedNativeJsonStillAllowsBoundedFallback() throws Exception {
    assertEquals(
        "喜羊羊与灰太狼",
        VoiceCommand.movieTitle(
            new JSONObject().put("originalData", "invalid").put("input", "我想看喜羊羊与灰太狼")));
    assertEquals(200, VoiceCommand.bounded(new String(new char[250]).replace('\0', 'a')).length());
  }

  @Test
  public void recentlyCompletedDictationCannotBecomeMovieSearch() {
    assertTrue(VoiceCommand.shouldDictate(true, 800));
    assertFalse(VoiceCommand.shouldDictate(false, 800));
    assertFalse(VoiceCommand.shouldDictate(true, 20000));
    assertFalse(VoiceCommand.shouldDictate(true, -1));
  }
}
