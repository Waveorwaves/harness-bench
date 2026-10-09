"""Screenshots a page from the workspace with a headless Chromium-family browser.

Runs inside the sandbox with the workspace as its working directory:

    capture.py --path index.html --width 1280 --height 800 --times 1000,3000 [--probe "<js>"] [--clip-ms 2500]
               [--script steps.json]

Writes frame-<ms>.png, optional clip-NNN.jpg frames and capture.json to $HB_CAPTURE. The browser comes from $HB_BROWSER,
or the first of chromium / chromium-browser / google-chrome on PATH. It is driven over the
DevTools protocol, so uncaught errors and failed requests are reported exactly.
Standard library only.
"""

import argparse
import base64
import functools
import http.server
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import struct
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import zlib


def read_png(path):
    """Decode an 8-bit RGB or RGBA PNG into (width, height, rows of bytes, channels)."""
    data = Path(path).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    position, chunks, header = 8, [], None
    while position < len(data):
        length, kind = struct.unpack(">I4s", data[position:position + 8])
        body = data[position + 8:position + 8 + length]
        position += 12 + length
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            chunks.append(body)
    width, height, depth, color, _, _, interlace = header
    if depth != 8 or color not in (2, 6) or interlace:
        raise ValueError("unsupported PNG layout")
    channels = 3 if color == 2 else 4
    stride = width * channels
    raw = zlib.decompress(b"".join(chunks))
    rows, previous = [], bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        kind, line = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        for x in range(stride):
            left = line[x - channels] if x >= channels else 0
            up = previous[x]
            corner = previous[x - channels] if x >= channels else 0
            if kind == 1:
                line[x] = (line[x] + left) & 255
            elif kind == 2:
                line[x] = (line[x] + up) & 255
            elif kind == 3:
                line[x] = (line[x] + (left + up) // 2) & 255
            elif kind == 4:
                estimate = left + up - corner
                near = min((abs(estimate - left), 0, left), (abs(estimate - up), 1, up), (abs(estimate - corner), 2, corner))
                line[x] = (line[x] + near[2]) & 255
        rows.append(line)
        previous = line
    return width, height, rows, channels


def sample(image, step=4):
    width, height, rows, channels = image
    return [tuple(rows[y][x * channels:x * channels + 3]) for y in range(0, height, step) for x in range(0, width, step)]


def describe(path):
    image = read_png(path)
    pixels = sample(image)
    coarse = {}
    for red, green, blue in pixels:
        key = (red >> 4, green >> 4, blue >> 4)
        coarse[key] = coarse.get(key, 0) + 1
    return {"width": image[0], "height": image[1], "distinct_colors": len(coarse),
            "dominant_share": round(max(coarse.values()) / len(pixels), 4)}, pixels


def changed_fraction(first, second):
    if len(first) != len(second):
        return 1.0
    changed = sum(1 for a, b in zip(first, second) if max(abs(a[i] - b[i]) for i in range(3)) > 16)
    return round(changed / len(first), 4)


class Unavailable(RuntimeError):
    """The browser could not be found or started: a fault in the setup, not in the page."""


def find_browser():
    configured = os.environ.get("HB_BROWSER")
    if configured:
        return configured
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        if shutil.which(name):
            return name
    raise Unavailable("no browser: set HB_BROWSER or install chromium in the sandbox image")


class WebSocket:
    """Just enough of RFC 6455 to talk to the browser's debugging port."""

    def __init__(self, url):
        parsed = urllib.parse.urlparse(url)
        self.socket = socket.create_connection((parsed.hostname, parsed.port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        self.socket.sendall((f"GET {parsed.path} HTTP/1.1\r\nHost: {parsed.netloc}\r\nUpgrade: websocket\r\n"
                             f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.socket.recv(4096)
            if not chunk:
                raise ConnectionError("the browser closed the debugging connection during the handshake")
            response += chunk
        head, self.buffer = response.split(b"\r\n\r\n", 1)
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError("the browser refused the debugging connection")
        self.message = b""

    def send(self, text):
        payload = text.encode()
        mask = os.urandom(4)
        size = len(payload)
        if size < 126:
            header = bytes([0x81, 0x80 | size])
        elif size < 65536:
            header = bytes([0x81, 0x80 | 126]) + struct.pack(">H", size)
        else:
            header = bytes([0x81, 0x80 | 127]) + struct.pack(">Q", size)
        self.socket.sendall(header + mask + bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload)))

    def frame(self):
        """Take one complete frame off the buffer, or return None and leave the buffer untouched."""
        data = self.buffer
        if len(data) < 2:
            return None
        size, offset = data[1] & 0x7F, 2
        if size == 126:
            if len(data) < 4:
                return None
            size, offset = struct.unpack(">H", data[2:4])[0], 4
        elif size == 127:
            if len(data) < 10:
                return None
            size, offset = struct.unpack(">Q", data[2:10])[0], 10
        if len(data) < offset + size:
            return None
        self.buffer = data[offset + size:]
        return bool(data[0] & 0x80), data[0] & 0x0F, data[offset:offset + size]

    def receive(self, timeout):
        """The next text message, or None if none arrives in time."""
        deadline = time.monotonic() + timeout
        while True:
            parsed = self.frame()
            if parsed is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self.socket.settimeout(remaining)
                try:
                    chunk = self.socket.recv(1 << 16)
                except (socket.timeout, TimeoutError):
                    return None
                if not chunk:
                    raise ConnectionError("the browser closed the debugging connection")
                self.buffer += chunk
                continue
            final, opcode, payload = parsed
            if opcode == 8:
                raise ConnectionError("the browser closed the debugging connection")
            if opcode in (0, 1, 2):
                self.message += payload
                if final:
                    text, self.message = self.message.decode(errors="replace"), b""
                    return text


class Page:
    """A browser tab driven over the Chrome DevTools Protocol."""

    def __init__(self, connection):
        self.connection, self.sent, self.events, self.dialogs = connection, 0, [], 0

    def record(self, message):
        self.events.append(message)
        if message.get("method") == "Page.javascriptDialogOpening":
            # An alert or confirm would freeze the page until answered. Say yes, without waiting for the reply.
            self.dialogs += 1
            self.connection.send(json.dumps({"id": 1_000_000 + self.dialogs, "method": "Page.handleJavaScriptDialog",
                                             "params": {"accept": True}}))

    def call(self, method, params=None, timeout=30):
        self.sent += 1
        self.connection.send(json.dumps({"id": self.sent, "method": method, "params": params or {}}))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            text = self.connection.receive(deadline - time.monotonic())
            if text is None:
                break
            message = json.loads(text)
            if message.get("id") == self.sent:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error'].get('message')}")
                return message.get("result", {})
            self.record(message)
        raise TimeoutError(f"{method} did not answer")

    def listen(self, seconds, until=None):
        """Collect events for a while; stop early when an event named `until` arrives."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            text = self.connection.receive(deadline - time.monotonic())
            if text is None:
                break
            self.record(json.loads(text))
            if until and self.events[-1].get("method") == until:
                return True
        return False

    def requests(self, origin):
        """What the page asked for: paths on its own server, and anything it tried to reach elsewhere."""
        local, external = [], []
        for event in self.events:
            if event.get("method") != "Network.requestWillBeSent":
                continue
            url = event["params"]["request"]["url"]
            if url.startswith(origin + "/"):
                local.append(url[len(origin):].split("?")[0])
            elif not url.startswith(("data:", "blob:", "about:")):
                external.append(url[:200])
        return list(dict.fromkeys(local)), list(dict.fromkeys(external))

    def errors(self):
        found = []
        for event in self.events:
            params = event.get("params", {})
            if event.get("method") == "Runtime.exceptionThrown":
                details = params.get("exceptionDetails", {})
                found.append((details.get("exception") or {}).get("description") or details.get("text", "exception"))
            elif event.get("method") == "Runtime.consoleAPICalled" and params.get("type") == "error":
                found.append("console.error: " + " ".join(str(a.get("value", a.get("description", ""))) for a in params.get("args", [])))
            elif event.get("method") == "Log.entryAdded" and params.get("entry", {}).get("level") == "error":
                entry = params["entry"]
                found.append(f"{entry.get('text', '')} {entry.get('url', '')}".strip())
        # Browsers ask for a favicon on their own; its absence is not the page's fault.
        return list(dict.fromkeys(message.splitlines()[0][:300] for message in found
                                  if message and "favicon.ico" not in message))


KEYS = {"Enter": (13, "\r"), "Escape": (27, None), "Tab": (9, None), "Backspace": (8, None), "Delete": (46, None),
        " ": (32, " "), "ArrowLeft": (37, None), "ArrowUp": (38, None), "ArrowRight": (39, None), "ArrowDown": (40, None),
        "Home": (36, None), "End": (35, None)}

LOCATE = """(() => {
  const all = [...document.querySelectorAll(%s)];
  const sized = (element) => { const box = element.getBoundingClientRect(); return box.width > 0 && box.height > 0; };
  // Prefer the first match a person could see; a page may keep hidden copies of a control.
  let element = all.find(sized) || all[0];
  if (!element) return null;
  // A control with no size of its own (a checkbox hidden behind its styled label) is used through its label.
  if (!sized(element) && element.labels && element.labels.length && sized(element.labels[0])) element = element.labels[0];
  let shown = element;
  while (shown && !sized(shown)) shown = shown.parentElement;
  if (!shown) return null;
  shown.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });  // a smooth scroll would still be moving
  const centre = (target) => { const box = target.getBoundingClientRect(); return { x: box.left + box.width / 2, y: box.top + box.height / 2 }; };
  return { ...centre(element), visible: sized(element), near: centre(shown) };
})()"""

# Lets the page finish what it started: two animation frames and a short pause.
SETTLE = "new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(done, 40))))"


def interact(page, steps):
    """Use the page the way a person would: real clicks, typing and key presses, and reloads.

    Each step is {"do": ...}. `click`, `dblclick`, `type` and `clear` take a CSS `selector`;
    `type` takes `text`; `press` takes a `key`, optionally with `shift`; `eval` runs a
    JavaScript expression and stores its value under `name`; `reload` reloads the page;
    `wait` pauses for `ms`. A step that cannot be carried out is recorded and the rest go on,
    so one broken control fails its own checks, not everything after it.
    Returns (values by name, problems).
    """
    values, problems = {}, []

    def evaluate(expression):
        answer = page.call("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
        if answer.get("exceptionDetails"):
            raise RuntimeError(answer["exceptionDetails"].get("exception", {}).get("description", "script error").splitlines()[0])
        return answer.get("result", {}).get("value")

    def settle():
        try:
            page.call("Runtime.evaluate", {"expression": SETTLE, "awaitPromise": True}, timeout=5)
        except (RuntimeError, TimeoutError):
            page.listen(0.1)

    def point(selector):
        spot = evaluate(LOCATE % json.dumps(selector))
        if spot and not spot["visible"]:
            # Some controls only appear when the pointer is over their row; move there as a person would.
            page.call("Input.dispatchMouseEvent", {"type": "mouseMoved", **spot["near"]})
            settle()
            spot = evaluate(LOCATE % json.dumps(selector))
        if not spot or not spot["visible"]:
            raise RuntimeError(f"nothing visible matches {selector}")
        page.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": spot["x"], "y": spot["y"]})
        return spot

    def mouse(spot, clicks):
        for kind in ("mousePressed", "mouseReleased"):
            page.call("Input.dispatchMouseEvent", {"type": kind, "x": spot["x"], "y": spot["y"], "button": "left",
                                                   "clickCount": clicks})

    for index, step in enumerate(steps):
        action = step.get("do")
        try:
            if action == "click":
                mouse(point(step["selector"]), 1)
            elif action == "dblclick":
                spot = point(step["selector"])
                mouse(spot, 1)
                mouse(spot, 2)
            elif action in ("type", "clear"):
                mouse(point(step["selector"]), 1)
                if action == "clear" or step.get("replace"):
                    evaluate("document.activeElement && document.activeElement.select && document.activeElement.select()")
                    page.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8})
                    page.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8})
                if action == "type":
                    page.call("Input.insertText", {"text": step["text"]})
            elif action == "press":
                key = step["key"]
                code, text = KEYS.get(key, (ord(key.upper()) if len(key) == 1 else 0, key if len(key) == 1 else None))
                event = {"key": key, "code": "Space" if key == " " else key, "windowsVirtualKeyCode": code,
                         "modifiers": 8 if step.get("shift") else 0}
                page.call("Input.dispatchKeyEvent", {"type": "keyDown", **event, **({"text": text} if text else {})})
                page.call("Input.dispatchKeyEvent", {"type": "keyUp", **event})
            elif action == "eval":
                values[step["name"]] = evaluate(step["script"])
            elif action == "reload":
                page.listen(0.5)  # a page may save a moment after the last change, as many do
                page.call("Page.reload")
                page.listen(15, until="Page.loadEventFired")
                page.listen(0.3)
            elif action == "wait":
                page.listen(step.get("ms", 100) / 1000)
            else:
                raise RuntimeError(f"unknown action {action!r}")
            if action not in ("eval", "wait"):
                settle()
        except (RuntimeError, KeyError, TimeoutError) as error:
            problems.append(f"step {index + 1} ({action} {step.get('selector') or step.get('name') or step.get('key') or ''}): {error}"[:300])
    return values, problems


def open_page(browser, profile, width, height):
    try:
        process = _launch(browser, profile, width, height)
    except OSError as error:
        raise Unavailable(f"the browser could not be launched: {error}") from error
    return _attach(process, profile)


def _launch(browser, profile, width, height):
    return subprocess.Popen(
        [browser, "--headless=new", "--no-sandbox", "--no-first-run", "--no-default-browser-check",
         "--hide-scrollbars", "--mute-audio", "--remote-debugging-port=0", f"--user-data-dir={profile}",
         f"--window-size={width},{height}",
         # WebGL must work with or without a GPU; an image can override these through HB_BROWSER_FLAGS.
         *os.environ.get("HB_BROWSER_FLAGS", "--ignore-gpu-blocklist --enable-unsafe-swiftshader").split(),
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def _attach(process, profile):
    port_file = Path(profile) / "DevToolsActivePort"
    deadline = time.monotonic() + 30
    while not port_file.exists() or not port_file.read_text().strip():
        if time.monotonic() > deadline or process.poll() is not None:
            process.kill()
            raise Unavailable("the browser did not start")
        time.sleep(0.1)
    port = int(port_file.read_text().split()[0])
    for _ in range(50):
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as response:
            tabs = [tab for tab in json.load(response) if tab.get("type") == "page"]
        if tabs:
            return process, Page(WebSocket(tabs[0]["webSocketDebuggerUrl"]))
        time.sleep(0.1)
    process.kill()
    raise Unavailable("the browser opened no page")


# Counts animation frames for one second. Software rendering makes this a rough figure.
FRAME_RATE = """new Promise((resolve) => {
  let frames = 0;
  const start = performance.now();
  const tick = () => { frames += 1; performance.now() - start < 1000 ? requestAnimationFrame(tick) : resolve(frames); };
  requestAnimationFrame(tick);
})"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="index.html")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--times", default="1000,3000")
    parser.add_argument("--probe", help="JavaScript expression evaluated in the page after the last frame")
    parser.add_argument("--script", help="JSON file of interaction steps to carry out on the page (see interact)")
    parser.add_argument("--color-scheme", choices=("light", "dark", "system"), default="light",
                        help="the light or dark preference the page is told about (default light)")
    parser.add_argument("--clip-ms", type=int, default=0, help="also record a clip of this length after the stills")
    parser.add_argument("--clip-frames", type=int, default=20)
    parser.add_argument("--clip-scale", type=float, default=0.5)
    parser.add_argument("--clip-quality", type=int, default=70)
    args = parser.parse_args()
    out = Path(os.environ["HB_CAPTURE"])
    result = {"ok": False, "frames": [], "console_errors": [], "changed_fraction": None, "error": None}
    server = None
    try:
        if not Path(args.path).is_file():
            raise RuntimeError(f"{args.path} does not exist")
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=os.getcwd()))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f"http://127.0.0.1:{server.server_address[1]}"
        url = f"{origin}/{args.path}"
        samples = []
        with tempfile.TemporaryDirectory() as profile:
            process, page = open_page(find_browser(), profile, args.width, args.height)
            try:
                for domain in ("Page", "Runtime", "Log", "Network"):
                    page.call(f"{domain}.enable")
                page.call("Emulation.setDeviceMetricsOverride",
                          {"width": args.width, "height": args.height, "deviceScaleFactor": 1, "mobile": False})
                if args.color_scheme != "system":
                    # A page may follow the machine's light or dark setting; pin it so captures match everywhere.
                    page.call("Emulation.setEmulatedMedia",
                              {"features": [{"name": "prefers-color-scheme", "value": args.color_scheme}]})
                page.call("Page.navigate", {"url": url})
                result["loaded"] = page.listen(20, until="Page.loadEventFired")
                loaded_at = time.monotonic()
                # Frames are taken in real time after load, so an animation has visibly moved between them.
                for at_ms in [int(value) for value in args.times.split(",")]:
                    page.listen(max(0, loaded_at + at_ms / 1000 - time.monotonic()))
                    shot = page.call("Page.captureScreenshot", {"format": "png"})
                    target = out / f"frame-{at_ms}.png"
                    target.write_bytes(base64.b64decode(shot["data"]))
                    details, pixels = describe(target)
                    # A compact copy for galleries; the PNG stays the one that is measured and judged.
                    compact = page.call("Page.captureScreenshot", {"format": "jpeg", "quality": 85})
                    (out / f"frame-{at_ms}.jpg").write_bytes(base64.b64decode(compact["data"]))
                    result["frames"].append({"at_ms": at_ms, "file": target.name, "compact": f"frame-{at_ms}.jpg", **details})
                    samples.append(pixels)
                if args.clip_ms:
                    # A short run of small frames, so a person can see the motion and not just one still.
                    region = {"x": 0, "y": 0, "width": args.width, "height": args.height, "scale": args.clip_scale}
                    started, clip = time.monotonic(), []
                    while len(clip) < args.clip_frames and time.monotonic() - started < args.clip_ms / 1000:
                        offset = round((time.monotonic() - started) * 1000)
                        shot = page.call("Page.captureScreenshot", {"format": "jpeg", "quality": args.clip_quality, "clip": region})
                        name = f"clip-{len(clip):03d}.jpg"
                        (out / name).write_bytes(base64.b64decode(shot["data"]))
                        clip.append({"file": name, "offset_ms": offset})
                        page.listen(max(0, started + len(clip) * args.clip_ms / args.clip_frames / 1000 - time.monotonic()))
                    result["clip"] = clip
                counted = page.call("Runtime.evaluate", {"awaitPromise": True, "returnByValue": True, "expression": FRAME_RATE})
                result["frames_per_second"] = counted.get("result", {}).get("value")
                result["console_errors"] = page.errors()
                local, external = page.requests(origin)
                result["local_requests"] = [path for path in local if path not in ("/favicon.ico", "/" + args.path)]
                result["external_requests"] = external
                if args.probe:
                    answer = page.call("Runtime.evaluate", {"expression": args.probe, "returnByValue": True})
                    result["probe"] = answer.get("result", {}).get("value")
                if args.script:
                    # Errors and requests are read before this point, so the page is judged as it loaded
                    # and again after it has been used.
                    steps = json.loads(Path(args.script).read_text(encoding="utf-8"))
                    result["interaction"], result["interaction_problems"] = interact(page, steps)
                    result["console_errors_after_use"] = page.errors()
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass
                process.wait()
        if len(samples) > 1:
            result["changed_fraction"] = changed_fraction(samples[0], samples[-1])
        result["ok"] = True
    except Exception as error:  # the report must be written whatever goes wrong
        result["error"] = f"{type(error).__name__}: {error}"
        result["infrastructure"] = isinstance(error, Unavailable)
    finally:
        if server:
            server.shutdown()
        (out / "capture.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
