#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
破甲修改器 · 图形界面
================================================================================

本机网页 UI，零第三方依赖：只起一个 127.0.0.1 的 http.server，把按钮动作转成
对核心脚本的命令行调用，再把它的输出原样流回页面。

两种运行形态：
  · 源码态 —— `python src/pojia_gui.py`，每个动作拉起 `python -u pojia.py …`。
  · 打包态 —— 由单文件包里的 `--gui` 用 runpy 在核心进程内跑起来（本文件是打包时
    塞进去的数据文件）。包里没有解释器，所以每个动作直接把**自己的 exe** 当命令行，
    而 `--version` 这类要读源码的地方改成问自己一次。

为什么用网页而不是 tkinter：
  · tkinter 的 ttk 主题在 Windows 上很难做出「现代极简」的观感 —— 圆角、阴影、
    过渡都要自己用 Canvas 画；网页这边几行 CSS 就够，而且天然支持深色终端区。
  · 仍然是零依赖：http.server / webbrowser / subprocess 全在标准库。

安全边界：
  · 只绑定 127.0.0.1，不接受外部连接；
  · 每次启动生成随机 token，页面地址带 token，接口校验 token —— 防止本机其他
    网页/程序直接 POST 到端口上触发破坏性操作；
  · 破甲 / 还原必须在页面里二次确认，服务端还会再校验一次 confirm 字段。

用法：
    python src/pojia_gui.py            # 起界面并自动打开浏览器
    python src/pojia_gui.py --no-open  # 只起服务，自己开地址
    pojia-modifier.exe --gui               # 打包版（POJIA_GUI_NO_OPEN=1 可关掉自动开浏览器）
"""

import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    HERE = os.path.dirname(os.path.abspath(sys.executable))
    CORE = ""
else:
    HERE = os.path.dirname(os.path.abspath(__file__))
    CORE = os.path.join(HERE, "pojia.py")
IS_WIN = (os.name == "nt")
TOKEN = secrets.token_urlsafe(18)
REPO_NAME = "Mladery/pojia-modifier"
REPO_URL = "https://github.com/" + REPO_NAME
_VER_CACHE = []


def _spawn_flags():
    if IS_WIN:
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def ui_dir():
    """界面文件（app.html / app.css / app.js）在哪个目录。

    打包后是 PyInstaller 解出来的 <_MEIPASS>/ui（6.x 里就是 _internal/ui），
    源码里是 src/ui。两边同名，所以这里只找「有 app.html 的那一个」。
    """
    cands = []
    _mp = getattr(sys, "_MEIPASS", "") or ""
    if _mp:
        cands.append(os.path.join(_mp, "ui"))
    cands.append(os.path.join(HERE, "ui"))
    for d in cands:
        if os.path.isfile(os.path.join(d, "app.html")):
            return d
    return cands[-1]


def asset(name):
    """读一个界面文件。读不到返回空串 —— 由调用方决定怎么兜。"""
    try:
        with open(os.path.join(ui_dir(), name), "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _frozen_version():
    if _VER_CACHE:
        return _VER_CACHE[0]
    ver = ""
    cands = [os.path.join(HERE, "_version.txt")]
    _mp = getattr(sys, "_MEIPASS", "") or ""
    if _mp:
        cands.insert(0, os.path.join(_mp, "_version.txt"))
    for path in cands:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                ver = f.read().strip().splitlines()[0].strip()
        except (OSError, IndexError):
            continue
        if ver:
            break
    if not ver:
        ver = "?"
        try:
            r = subprocess.run(
                [sys.executable, "--version"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=180, creationflags=_spawn_flags(),
            )
            txt = (r.stdout or b"").decode("utf-8", "replace")
            m = re.search(r"(\d+\.\d+(?:-[A-Za-z0-9.]+)?)", txt)
            if m:
                ver = m.group(1)
        except Exception:
            pass
    _VER_CACHE.append(ver)
    return ver


def core_version():
    if FROZEN:
        return _frozen_version()
    try:
        with open(CORE, "r", encoding="utf-8", errors="ignore") as f:
            txt = f.read()
        # 界面上一律显示带后缀的那个（1.01.3-beta），跟 Release tag 对得上；
        # 老版本只有 VERSION，退回它。
        m = re.search(r'^DISPLAY_VERSION\s*=\s*"([^"]+)"', txt, re.M) or \
            re.search(r'^VERSION\s*=\s*"([^"]+)"', txt, re.M)
        if m:
            return m.group(1)
    except OSError:
        pass
    return "?"


_UPDATE_LINE = re.compile(
    r"最新发布：\s*([0-9][0-9.]*(?:-(?:alpha|beta|mod))?)")
_UPDATE_JSON = "#update "
_SETTINGS_JSON = "#settings "
# 一条流结束前补上的退出码。前端只认这个前缀，用它判断成败，不显示。
# 为什么另发而不是看最后一行：只读动作（体检）本来就会打 [!] 提示，按字样判会误报。
EXIT_SENTINEL = "__POJIA_EXIT__:"
# 通道从后缀读：1.01.3-beta -> beta，没有后缀就是稳定版
_CH_RANK = {"alpha": 0, "beta": 1, "mod": 2}


def _channel_of(text):
    m = re.search(r"-(alpha|beta|mod)\b", str(text or "").lower())
    return m.group(1) if m else "mod"


def _newer(latest, cur):
    """跟核心 update_newer 同一条规则：稳定版盖过同系列的测试版。

    只在读不到核心那行 `#update`（老版本输出）时才走到这儿。稳定版 1.01-mod
    数字上小于它的上游 1.01.9-beta，纯数字比会让人被劝「升级」回自己的测试版；
    反过来 1.02.1-beta 的数字又大于 1.02-mod，测试版用户会收不到同系列稳定版。
    所以同一系列里稳定版恒为新，两个方向都成立。
    """
    latest_v = _dotted(latest)
    cur_v = _dotted(cur)
    if latest_v[:2] == cur_v[:2]:
        if _channel_of(cur) == "mod" and _channel_of(latest) in ("alpha", "beta"):
            return False
        if _channel_of(latest) == "mod" and _channel_of(cur) in ("alpha", "beta"):
            return True
    if not latest_v > cur_v:
        return False
    return True


def _core_args(extra):
    return ([sys.executable] if FROZEN else [sys.executable, "-u", CORE]) + list(extra)


def _run_core(extra, timeout=15):
    """跑一次核心脚本，返回合并后的输出。失败返回空串。"""
    try:
        r = subprocess.run(_core_args(extra), stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout,
                           creationflags=_spawn_flags())
    except (OSError, subprocess.SubprocessError):
        return ""
    return (r.stdout or b"").decode("utf-8", "replace")


def _grab_json(text, prefix):
    """从输出里挑出标记行后面的 JSON。找不到返回 None。"""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(prefix):
            try:
                data = json.loads(line[len(prefix):])
            except ValueError:
                continue
            if isinstance(data, dict):
                return data
    return None


def _dotted(s):
    """1.01.2-beta -> (1,1,2)。跟核心那边的 version_tuple 保持同一套口径。"""
    m = re.search(r"\d+(?:\.\d+)*", str(s or ""))
    if not m:
        return (0, 0, 0)
    parts = [int(p) for p in m.group(0).split(".")][:3]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def check_update(timeout=15):
    text = _run_core(["--check-update"], timeout=timeout)
    if not text.strip():
        return {"ok": False, "note": "检查失败：没拿到输出"}
    data = _grab_json(text, _UPDATE_JSON)
    if data:
        latest = str(data.get("latest") or "")
        cur = str(data.get("current") or core_version())
        ch = str(data.get("channel") or _channel_of(cur))
        return {"ok": True, "latest": latest, "current": cur,
                "newer": bool(data.get("newer")),
                "channel": ch,
                "channel_name": str(data.get("channel_name") or ""),
                "note": ""}
    # 老板本的输出没有那行 JSON，靠人看的字兜一下
    m = _UPDATE_LINE.search(text)
    if not m:
        return {"ok": False, "note": "没读到版本号"}
    latest, cur = m.group(1), core_version()
    return {"ok": True, "latest": latest, "current": cur,
            "newer": _newer(latest, cur),
            "channel": _channel_of(cur), "channel_name": "", "note": ""}


def read_settings(spec=""):
    """读设置。传 spec（如 channel=beta）就是改完再读回来。"""
    text = _run_core(["--settings"] + ([spec] if spec else []), timeout=12)
    data = _grab_json(text, _SETTINGS_JSON)
    if data:
        return data
    return {"version": core_version(), "channel": _channel_of(core_version()),
            "auto_check": True, "channels": [], "note": "读不到设置"}


REGISTRY = [
    ("dsh", "DeepSeek Harness"),
    ("wb", "WorkBuddy"),
    ("wbintl", "WorkBuddy 国际版"),
    ("zcode", "ZCode"),
    ("codex", "Codex CLI"),
    ("cursor", "Cursor"),
    ("claude", "Claude Code"),
    ("antigravity", "Antigravity"),
    ("qwen", "Qwen Code"),
    ("iflow", "iFlow"),
    ("trae", "Trae"),
    ("codebuddy", "CodeBuddy"),
    ("opencode", "OpenCode"),
    ("windsurf", "Windsurf"),
    ("cline", "Cline"),
    ("copilot", "Copilot CLI"),
    ("kiro", "Kiro"),
    ("reasonix", "Reasonix"),
    ("traecn", "Trae CN"),
    ("qodercn", "Qoder CN"),
]

ACTIONS = [
    ("status", "检测状态", "看看每个软件现在是什么状态（只看不改）", "read"),
    ("diagnose", "诊断详情", "逐个文件列出补丁与备份状态", "read"),
    ("check", "体检", "磁盘 / 凭证 / 自证就绪度", "read"),
    ("dryrun", "先预演", "只列出会改哪些文件，不动手", "read"),
    ("apply", "一键破甲", "按选中的软件执行修改", "write"),
    ("revert", "还原成原版", "改错了点这里，按备份恢复", "write"),
    ("snapshot", "生成快照", "把当前提示词存一份基准", "read"),
    ("compare", "对比快照", "看提示词有没有被改过", "read"),
]

DSH_MODES = ("inject", "preset")


def pick_options(payload):
    if not isinstance(payload, dict):
        return "inject", False
    mode = payload.get("dsh_mode")
    return (mode if mode in DSH_MODES else "inject"), bool(payload.get("git_bash"))


def build_cmd(action, targets, dsh_mode="inject", git_bash=False):
    base = [sys.executable] if FROZEN else [sys.executable, "-u", CORE]
    t = ",".join(targets) if targets else "all"

    extra = []
    if action in ("dryrun", "apply") and (not targets or "dsh" in targets):
        m = (dsh_mode or "inject").strip().lower()
        extra += ["--dsh-mode", m if m in DSH_MODES else "inject"]
        if IS_WIN and git_bash:
            extra += ["--git-bash"]

    if action == "status":
        return base + ["--status", "--target", t]
    if action == "diagnose":
        return base + ["--diagnose", "--target", t]
    if action == "check":
        return base + ["--check"]
    if action == "dryrun":
        return base + ["--dry-run", "--apply", "--target", t] + extra
    if action == "apply":
        return base + ["--apply", "--yes", "--target", t] + extra
    if action == "revert":
        return base + ["--revert", "--yes", "--target", t]
    if action == "snapshot":
        return base + ["--snapshot"]
    if action == "compare":
        return base + ["--compare"]
    if action == "update":
        return base + ["--update"]
    return None


_SHELL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>破甲修改器</title>
<style>
__CSS__
</style>
</head>
<body>
__BODY__
<script>
__JS__
</script>
</body>
</html>
"""

_MISSING = (
    "<!DOCTYPE html><meta charset='utf-8'>"
    "<body style=\"font:14px/1.7 system-ui,sans-serif;padding:32px;max-width:52ch\">"
    "<h3 style=\"margin:0 0 8px\">界面文件没找到</h3>"
    "<p>程序要读同目录下的 <code>ui/app.html</code>、<code>app.css</code>、<code>app.js</code>，"
    "这三个文件没跟过来。重新解压一次安装包即可；直接跑源码的话，"
    "确认 <code>src/ui/</code> 跟 <code>src/pojia.py</code> 在同一层。</p>"
    "</body>"
)


def render_page():
    """把三个界面文件拼成一张页。牌子、仓库地址这类每次启动都可能变的，现填。"""
    css, body, js = asset("app.css"), asset("app.html"), asset("app.js")
    if not body:
        return _MISSING
    return (_SHELL
            .replace("__CSS__", css)
            .replace("__BODY__", body)
            .replace("__JS__", js)
            .replace("__VERSION__", core_version())
            .replace("__TOKEN__", TOKEN)
            .replace("__TARGETS__", json.dumps(REGISTRY, ensure_ascii=False))
            .replace("__ACTIONS__", json.dumps(ACTIONS, ensure_ascii=False))
            .replace("__REPO__", REPO_URL)
            .replace("__REPO_NAME__", REPO_NAME)
            .replace("__ISWIN__", "true" if IS_WIN else "false"))


class Handler(BaseHTTPRequestHandler):
    server_version = "PojiaGUI"

    def log_message(self, fmt, *a):
        pass

    def _authorized(self):
        q = self.path.split("t=", 1)
        return len(q) == 2 and q[1].split("&")[0] == TOKEN

    def _json(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._authorized():
            self.send_error(403, "bad token")
            return
        if self.path.startswith("/api/update"):
            self._json(json.dumps(check_update(), ensure_ascii=False).encode("utf-8"))
            return
        if self.path.startswith("/api/settings"):
            self._json(json.dumps(read_settings(), ensure_ascii=False).encode("utf-8"))
            return
        body = render_page().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self._authorized():
            self.send_error(403, "bad token")
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, OSError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        if self.path.startswith("/api/settings"):
            spec = []
            ch = str(payload.get("channel") or "").lower()
            if ch in _CH_RANK:
                spec.append("channel=" + ch)
            if "auto_check" in payload:
                spec.append("auto=" + ("on" if payload.get("auto_check") else "off"))
            data = read_settings(" ".join(spec))
            self._json(json.dumps(data, ensure_ascii=False).encode("utf-8"))
            return
        action = payload.get("action") or ""
        targets = payload.get("targets") or []
        if not isinstance(targets, list):
            targets = []
        targets = [t for t in targets if t in dict(REGISTRY)]
        dsh_mode, git_bash = pick_options(payload)
        cmd = build_cmd(action, targets, dsh_mode, git_bash)
        if not cmd:
            self.send_error(400, "bad action")
            return
        if action in ("apply", "revert") and not payload.get("confirm"):
            self.send_error(400, "confirm required")
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        # 告诉核心「这次是界面在跑」：下载时才吐 #progress 行给进度条用，
        # CLI 那边不吐，免得命令行里冒出一串机器格式。
        env["POJIA_GUI"] = "1"
        cwd = HERE if FROZEN else (os.path.dirname(HERE) or HERE)
        try:
            proc = subprocess.Popen(
                cmd, cwd=cwd, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                bufsize=0, creationflags=_spawn_flags(),
            )
        except OSError as e:
            self.wfile.write(("启动失败：%s\n" % e).encode("utf-8"))
            return
        tail = []
        saw_armed = False
        try:
            while True:
                chunk = proc.stdout.readline()
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
                line = chunk.decode("utf-8", "replace")
                tail.append(line)
                del tail[:-20]
                # 滑窗只有 20 行，下载进度一多就可能把「已安排」挤出去。
                # 退场判定单独累积，不依赖窗口还留着那行。
                if "已安排" in line:
                    saw_armed = True
        except (BrokenPipeError, ConnectionResetError):
            proc.kill()
        finally:
            try:
                proc.stdout.close()
            except Exception:
                pass
        code = proc.wait()

        # 最后补一行退出码（前端认得这个前缀，只在内部用、不显示）。
        # 成败以它为准：体检这类只读动作本来就会打 [!] 提示，
        # 按字样判会把「看完了，有两处要注意」当成失败。
        try:
            self.wfile.write(("\n%s%d\n" % (EXIT_SENTINEL, code)).encode("utf-8"))
            self.wfile.flush()
        except Exception:
            pass

        # 升级安排好了：这个进程得自己退场，否则批处理永远等不到文件解锁，
        # 用户的印象就是「点了没反应」。批处理那边还有 taskkill 兜底，
        # 这里先体面地走 —— 页面上的最后一行说明它会自己重开。
        # 两种换装都算：「已安排升级」（装过的，走安装器）和「已安排替换」
        # （绿色版，直接挪文件）。两条路都必须让这个进程先退场。
        if action == "update" and code == 0 and saw_armed:
            try:
                self.wfile.write(
                    "\n程序即将退出，安装完成后会自动重新打开。\n".encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass
            threading.Timer(1.5, os._exit, (0,)).start()


def main():
    if not FROZEN and not os.path.isfile(CORE):
        print("找不到核心脚本：%s" % CORE)
        return 1
    host = "127.0.0.1"
    srv = ThreadingHTTPServer((host, 0), Handler)
    port = srv.server_address[1]
    url = "http://%s:%d/?t=%s" % (host, port, TOKEN)
    print("=" * 66, flush=True)
    print(" 破甲修改器 · 图形界面   v%s%s"
          % (core_version(), "（打包版）" if FROZEN else ""), flush=True)
    print(" 地址：%s" % url, flush=True)
    print(" 关闭窗口或按 Ctrl+C 退出", flush=True)
    print("=" * 66, flush=True)
    quiet_open = ("--no-open" in sys.argv) or os.environ.get("POJIA_GUI_NO_OPEN")
    if not quiet_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
