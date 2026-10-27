package io.github.qz0071.tvvoicebridge;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

/** Small local IPC adapter to the engine already running on this projector. */
final class NativeBus implements AutoCloseable {
  interface Listener {
    void state(boolean ready);

    void event(String topic, String payload);
  }

  final Listener listener;
  final int port;
  volatile boolean closed;
  volatile Socket socket;
  OutputStream output;
  Thread reader;

  NativeBus(int port, Listener l) {
    this.port = port;
    listener = l;
  }

  void start() {
    reader = new Thread(this::run, "NativeVoiceEvents");
    reader.start();
  }

  void run() {
    int delay = 1000;
    while (!closed) {
      try {
        Socket current = new Socket();
        socket = current;
        current.connect(new InetSocketAddress("127.0.0.1", port), 2000);
        current.setSoTimeout(15000);
        current.setTcpNoDelay(true);
        output = current.getOutputStream();
        InputStream in = new BufferedInputStream(current.getInputStream());
        send("request", "/bus/join", "tv.voice.bridge");
        expectReply(in);
        send(
            "request",
            "/bus/subscribe",
            "asr.speech.result",
            "asr.speech.text",
            "sys.dialog.error");
        expectReply(in);
        delay = 1000;
        listener.state(true);
        while (!closed) {
          List<String> frame = read(in);
          if (frame.size() >= 3 && "publish".equals(frame.get(0)))
            listener.event(frame.get(1), frame.get(2));
        }
      } catch (Exception e) {
        if (!closed) listener.state(false);
      } finally {
        Socket s = socket;
        socket = null;
        output = null;
        if (s != null)
          try {
            s.close();
          } catch (Exception ignored) {
          }
      }
      if (!closed)
        try {
          Thread.sleep(delay);
          delay = Math.min(delay * 2, 15000);
        } catch (InterruptedException e) {
          break;
        }
    }
  }

  void expectReply(InputStream in) throws IOException {
    while (true) {
      List<String> f = read(in);
      if (f.size() > 0 && "response".equals(f.get(0))) {
        if (f.size() > 2 && !f.get(2).isEmpty())
          throw new IOException("local engine rejected subscription");
        return;
      }
    }
  }

  synchronized void send(String... fields) throws IOException {
    if (output == null) throw new IOException("not connected");
    ByteArrayOutputStream frame = new ByteArrayOutputStream();
    for (String value : fields) {
      byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
      frame.write(Integer.toString(bytes.length).getBytes(StandardCharsets.US_ASCII));
      frame.write('\r');
      frame.write('\n');
      frame.write(bytes);
      frame.write('\r');
      frame.write('\n');
    }
    frame.write('\r');
    frame.write('\n');
    output.write(frame.toByteArray());
    output.flush();
  }

  static String line(InputStream in) throws IOException {
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    int previous = -1;
    while (true) {
      int b = in.read();
      if (b < 0) throw new EOFException();
      if (previous == '\r' && b == '\n') break;
      out.write(b);
      previous = b;
      if (out.size() > 32) throw new IOException("invalid local frame header");
    }
    byte[] bytes = out.toByteArray();
    return new String(bytes, 0, Math.max(0, bytes.length - 1), StandardCharsets.US_ASCII);
  }

  static List<String> read(InputStream in) throws IOException {
    List<String> fields = new ArrayList<>();
    while (true) {
      String size = line(in);
      if (size.isEmpty()) return fields;
      int count;
      try {
        count = Integer.parseInt(size);
      } catch (Exception e) {
        throw new IOException("invalid local frame", e);
      }
      if (count < 0 || count > 131072 || fields.size() >= 16)
        throw new IOException("oversized local frame");
      byte[] data = new byte[count];
      int at = 0;
      while (at < count) {
        int n = in.read(data, at, count - at);
        if (n < 0) throw new EOFException();
        at += n;
      }
      if (in.read() != '\r' || in.read() != '\n')
        throw new IOException("invalid local frame ending");
      fields.add(new String(data, StandardCharsets.UTF_8));
    }
  }

  public void close() {
    closed = true;
    if (reader != null) reader.interrupt();
    Socket s = socket;
    if (s != null)
      try {
        s.close();
      } catch (Exception ignored) {
      }
  }
}
