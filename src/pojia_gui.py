#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
破甲一键通 · 图形界面（社区版）
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
  · 上游早期的 GUI 也是本机网页，用户习惯一致。
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
        m = re.search(r'^VERSION\s*=\s*"([^"]+)"', txt, re.M)
        e = re.search(r'^EDITION\s*=\s*"([^"]+)"', txt, re.M)
        if m:
            return m.group(1) + ("-" + e.group(1) if e else "")
    except OSError:
        pass
    return "?"


_UPDATE_LINE = re.compile(r"最新发布：\s*([0-9][0-9.]*)\s+当前：\s*([0-9][0-9.]*)")


def _core_args(extra):
    return ([sys.executable] if FROZEN else [sys.executable, "-u", CORE]) + list(extra)


def _dotted(s):
    m = re.search(r"(\d+)\.(\d+)", str(s or ""))
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def check_update(timeout=15):
    try:
        r = subprocess.run(_core_args(["--check-update"]), stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout,
                           creationflags=_spawn_flags())
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "note": "检查失败：%s" % e}
    m = _UPDATE_LINE.search((r.stdout or b"").decode("utf-8", "replace"))
    if not m:
        return {"ok": False, "note": "没读到版本号"}
    latest, cur = m.group(1), m.group(2)
    return {"ok": True, "latest": latest, "current": cur,
            "newer": _dotted(latest) > _dotted(cur), "note": ""}


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


PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>破甲一键通 · 社区版</title>
<style>
  /* 纸墨：暖纸底 + 墨色字 + 一个靛青强调色。
     圆角三档：容器 12 / 控件 8 / 胶囊 999。
     强调色只有一个（靛青），朱红只用于「会改文件」的语义，翠绿只用于「一切正常」。 */
  :root{
    --paper:#f4f1e9;
    --surface:#fdfcf8;
    --surface-2:#efebe1;
    --ink:#1c1a16;
    --ink-2:#5a5346;
    --ink-3:#786f60;
    --line:#e2dbcc;
    --line-2:#cec5b1;
    --accent:#2b3f6b;
    --accent-2:#1d2c4d;
    --accent-soft:#e7eaf2;
    --danger:#a92a1d;
    --danger-soft:#f6e8e4;
    --ok:#2f6b4f;
    --ok-soft:#e6efe8;
    --console-bg:#1a1813;
    --console-ink:#e5ddce;
    --console-dim:#7d7566;
    --r:12px; --r-sm:8px;
  }
  @media (prefers-color-scheme: dark){
    :root{
      --paper:#131210;
      --surface:#1a1815;
      --surface-2:#221f1a;
      --ink:#efe9dc;
      --ink-2:#b3aa99;
      --ink-3:#9a9182;
      --line:#2d2922;
      --line-2:#3c362d;
      --accent:#a7bade;
      --accent-2:#c2d0ee;
      --accent-soft:#232a3a;
      --danger:#e08a7c;
      --danger-soft:#2e211d;
      --ok:#74c39b;
      --ok-soft:#1c2a23;
      --console-bg:#100f0c;
      --console-ink:#ded6c6;
      --console-dim:#6f6859;
    }
  }
  *{box-sizing:border-box}
  html,body{margin:0; min-height:100%}
  body{
    background:var(--paper); color:var(--ink);
    font:14px/1.62 -apple-system,BlinkMacSystemFont,"Segoe UI Variable Text","Segoe UI",
         "PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
    -webkit-font-smoothing:antialiased;
  }
  .mono{font-family:ui-monospace,SFMono-Regular,"Cascadia Mono",Menlo,Consolas,monospace;
        font-variant-numeric:tabular-nums}
  .shell{max-width:1080px; margin:0 auto; padding:20px 24px 28px}

  /* ── 顶栏 ───────────────────────────────────────────── */
  .topbar{
    display:flex; align-items:center; gap:12px;
    padding:0 2px 13px; border-bottom:1px solid var(--line);
  }
  .seal{width:20px; height:20px; flex:none; border-radius:4px; background:var(--accent); position:relative}
  .seal::after{
    content:""; position:absolute; inset:6px 5px; border-radius:1px;
    background:var(--surface); clip-path:polygon(0 0,100% 38%,0 76%);
  }
  .brand{display:flex; align-items:baseline; gap:9px; min-width:0}
  .brand b{font-size:15px; font-weight:640; letter-spacing:-.01em}
  .brand .tag{font-size:11px; color:var(--ink-3); letter-spacing:.06em;
              border-left:1px solid var(--line-2); padding-left:9px}
  .brand .ver{font-size:11.5px; color:var(--ink-3)}
  .grow{flex:1}

  /* ── 更新条：查到了才出现，装不装由你点 ───────────────── */
  .updatebar{
    display:flex; align-items:center; gap:10px; flex-wrap:wrap;
    margin:12px 0 0; padding:9px 12px; border-radius:var(--r-sm);
    border:1px solid var(--line-2); background:var(--accent-soft);
    font-size:13px; color:var(--ink-2);
  }
  .updatebar[hidden]{display:none}
  .u-dot{width:7px; height:7px; flex:none; border-radius:50%; background:var(--accent)}
  .u-text{min-width:0}
  .u-text b{color:var(--ink); font-weight:600}
  .state{
    display:inline-flex; align-items:center; gap:7px;
    padding:4px 11px 4px 9px; border-radius:999px;
    border:1px solid var(--line-2); background:var(--surface);
    font-size:12px; color:var(--ink-2); white-space:nowrap;
    transition:border-color .15s ease, color .15s ease, background .15s ease;
  }
  .state i{width:6px; height:6px; border-radius:50%; background:var(--ok); flex:none}
  .state.busy{border-color:var(--accent); color:var(--accent); background:var(--accent-soft)}
  .state.busy i{background:var(--accent); animation:blip 1.05s ease-in-out infinite}
  .state.bad{border-color:var(--danger); color:var(--danger); background:var(--danger-soft)}
  .state.bad i{background:var(--danger)}
  .state.good{border-color:var(--ok); color:var(--ok); background:var(--ok-soft)}
  @keyframes blip{0%,100%{opacity:1}50%{opacity:.25}}

  /* ── 顶部引导 ───────────────────────────────────────── */
  .hero{padding:26px 2px 6px}
  .hero h1{
    margin:0 0 7px; font-size:23px; line-height:1.3; font-weight:640;
    letter-spacing:-.02em; text-wrap:balance;
  }
  .hero .lede{
    margin:0 0 18px; max-width:60ch;
    font-size:13.5px; line-height:1.7; color:var(--ink-2);
  }
  .cta{display:flex; align-items:center; gap:10px; flex-wrap:wrap}
  .hint{
    margin:10px 0 0; font-size:12px; color:var(--ink-3);
    display:flex; align-items:center; gap:6px;
  }
  .hint b{font-weight:560; color:var(--ink-2)}

  /* ── 按钮 ───────────────────────────────────────────── */
  .btn{
    padding:8px 15px; border-radius:var(--r-sm); cursor:pointer;
    border:1px solid var(--line-2); background:var(--surface);
    font:inherit; font-size:13px; color:var(--ink);
    transition:background .12s ease, border-color .12s ease, opacity .12s ease;
  }
  .btn:hover{background:var(--surface-2)}
  .btn:disabled{opacity:.45; cursor:not-allowed}
  .btn:disabled:hover{background:var(--surface)}
  .btn.primary{background:var(--accent); border-color:var(--accent); color:#fbf9f4}
  .btn.primary:hover{background:var(--accent-2); border-color:var(--accent-2)}
  .btn.primary:disabled:hover{background:var(--accent)}
  .btn.danger{background:var(--danger); border-color:var(--danger); color:#fbf9f4}
  .btn.danger:hover{filter:brightness(1.07)}
  .btn.lg{
    padding:11px 22px; font-size:14px; font-weight:560; letter-spacing:.01em;
    border-radius:var(--r-sm);
    box-shadow:0 1px 2px rgba(28,26,22,.12);
  }
  @media (prefers-color-scheme: dark){
    .btn.primary,.btn.danger{color:#131210}
  }
  :focus-visible{outline:2px solid var(--accent); outline-offset:2px}

  /* ── 帮助折叠 ───────────────────────────────────────── */
  .help{
    margin:14px 0 0; border:1px solid var(--line); border-radius:var(--r);
    background:var(--surface); overflow:hidden;
  }
  .help > summary{
    cursor:pointer; padding:11px 15px; font-size:12.5px; color:var(--ink-2);
    list-style:none; display:flex; align-items:center; gap:8px;
  }
  .help > summary::-webkit-details-marker{display:none}
  .help > summary::before{
    content:""; width:5px; height:5px; flex:none; border-right:1.5px solid var(--ink-3);
    border-bottom:1.5px solid var(--ink-3); transform:rotate(-45deg); transition:transform .15s ease;
  }
  .help[open] > summary::before{transform:rotate(45deg)}
  .help > summary:hover{color:var(--ink)}
  .help .body{padding:0 15px 15px; display:grid; gap:11px}
  .help .q{font-size:12.5px; font-weight:560; margin:0 0 2px}
  .help .a{margin:0; font-size:12.5px; line-height:1.7; color:var(--ink-2)}

  /* ── 主栅格 ─────────────────────────────────────────── */
  .grid{
    display:grid; grid-template-columns:296px minmax(0,1fr); gap:0;
    margin-top:16px; border:1px solid var(--line); border-radius:var(--r);
    background:var(--surface); overflow:hidden;
  }
  @media (max-width:860px){ .grid{grid-template-columns:1fr} }
  /* 两列都是 flex 列：DSH 那块收起来后右列会变短，让摘要钉在底部，
     空出来的地方读作留白，而不是「下面漏了什么」。 */
  .col{min-width:0; display:flex; flex-direction:column}
  .col + .col{border-left:1px solid var(--line)}
  @media (max-width:860px){ .col + .col{border-left:0; border-top:1px solid var(--line)} }

  .head{
    display:flex; align-items:center; gap:10px;
    padding:12px 16px 10px; border-bottom:1px solid var(--line);
    background:var(--surface-2);
  }
  .head h2{margin:0; font-size:11.5px; font-weight:640; letter-spacing:.08em; color:var(--ink-2)}
  .head .aside{margin-left:auto; font-size:11.5px; color:var(--ink-3)}

  /* ── 软件清单 ───────────────────────────────────────── */
  /* 不做内滚动：17 项一屏放得下，整页滚比嵌套滚动直观 —— 小白看到列表被切掉一半
     会以为「就这些」，然后漏勾。窄屏靠整页滚动兜住。 */
  .list{padding:5px 0}
  .row{
    display:flex; align-items:center; gap:10px; width:100%;
    padding:7px 16px; border:0; background:none; cursor:pointer;
    font:inherit; color:var(--ink); text-align:left;
  }
  .row:hover{background:var(--surface-2)}
  .row .box{
    width:13px; height:13px; flex:none; border-radius:3px;
    border:1.5px solid var(--line-2); background:transparent;
    position:relative; transition:background .12s ease, border-color .12s ease;
  }
  .row[aria-pressed="true"] .box{background:var(--accent); border-color:var(--accent)}
  .row[aria-pressed="true"] .box::after{
    content:""; position:absolute; left:3.5px; top:1px; width:4px; height:7px;
    border-right:1.8px solid var(--surface); border-bottom:1.8px solid var(--surface);
    transform:rotate(40deg);
  }
  .row .lbl{flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:13px}
  .row[aria-pressed="true"] .lbl{font-weight:560}
  .row .badge{
    font-size:10.5px; letter-spacing:.04em; color:var(--accent);
    border:1px solid var(--accent); border-radius:999px; padding:0 6px; flex:none;
  }
  .foot{
    display:flex; align-items:center; gap:16px; margin-top:auto;
    padding:10px 16px; border-top:1px solid var(--line); background:var(--surface-2);
  }
  .foot .tip{margin-left:auto; font-size:11.5px; color:var(--ink-3)}
  .link{
    background:none; border:0; padding:0; cursor:pointer; font:inherit;
    font-size:12.5px; color:var(--ink-2); transition:color .12s ease;
  }
  .link:hover{color:var(--accent)}

  /* ── DSH 选项 ───────────────────────────────────────── */
  .opts{padding:13px 16px 15px; border-bottom:1px solid var(--line)}
  .choice{
    display:flex; gap:11px; padding:11px 13px; cursor:pointer;
    border:1px solid var(--line); border-radius:var(--r-sm); background:var(--surface);
    transition:border-color .12s ease, background .12s ease;
  }
  .choice + .choice{margin-top:8px}
  .choice:hover{border-color:var(--line-2); background:var(--surface-2)}
  .choice.on{border-color:var(--accent); background:var(--accent-soft)}
  .choice input{
    appearance:none; -webkit-appearance:none; margin:3px 0 0;
    width:14px; height:14px; flex:none; border-radius:50%; cursor:pointer;
    border:1.5px solid var(--line-2); background:transparent;
    transition:border-color .12s ease, background .12s ease, box-shadow .12s ease;
  }
  .choice input:checked{border-color:var(--accent); background:var(--accent);
    box-shadow:inset 0 0 0 3px var(--surface)}
  .choice .ct{font-size:13px; font-weight:560; display:flex; align-items:center; gap:7px}
  .choice .ct .tag{
    font-size:10.5px; font-weight:400; letter-spacing:.04em;
    color:var(--ink-3); border:1px solid var(--line-2); border-radius:999px; padding:0 6px;
  }
  .choice .cd{margin:2px 0 0; font-size:12px; line-height:1.62; color:var(--ink-2)}
  .choice.on .cd{color:var(--ink-2)}

  .switchrow{
    display:flex; align-items:flex-start; gap:11px;
    margin-top:14px; padding-top:13px; border-top:1px dashed var(--line-2);
    cursor:pointer;
  }
  .switchrow input{position:absolute; opacity:0; width:0; height:0}
  .track{
    width:34px; height:19px; flex:none; margin-top:2px; border-radius:999px;
    background:var(--line-2); position:relative; transition:background .14s ease;
  }
  .track::after{
    content:""; position:absolute; top:2px; left:2px; width:15px; height:15px;
    border-radius:50%; background:var(--surface); transition:transform .14s ease;
  }
  .switchrow input:checked + .track{background:var(--accent)}
  .switchrow input:checked + .track::after{transform:translateX(15px)}
  .switchrow input:focus-visible + .track{outline:2px solid var(--accent); outline-offset:2px}
  .switchrow .txt{font-size:12.5px; line-height:1.62}
  .switchrow .txt b{font-weight:560}
  .switchrow .txt span{display:block; color:var(--ink-2); font-size:12px}

  /* ── 其他操作 ───────────────────────────────────────── */
  .acts{padding:5px 0 6px}
  .act{
    display:flex; align-items:baseline; gap:12px; width:100%;
    padding:9px 16px; border:0; background:none; cursor:pointer;
    font:inherit; color:var(--ink); text-align:left;
    transition:background .12s ease;
  }
  .act:hover{background:var(--surface-2)}
  .act .n{font-size:13px; font-weight:560; min-width:84px}
  .act .d{flex:1; font-size:12px; color:var(--ink-3)}
  .act .go{font-size:13px; color:var(--line-2); transition:color .12s ease, transform .12s ease}
  .act:hover .go{color:var(--accent); transform:translateX(2px)}
  .act[data-kind="write"] .n{color:var(--danger)}
  .act[data-kind="write"]:hover{background:var(--danger-soft)}
  .act[disabled]{opacity:.4; cursor:not-allowed}
  .act[disabled]:hover{background:none}

  .more{border-top:1px solid var(--line)}
  .more > summary{
    cursor:pointer; list-style:none; padding:10px 16px;
    font-size:12.5px; color:var(--ink-3); display:flex; align-items:center; gap:8px;
  }
  .more > summary::-webkit-details-marker{display:none}
  .more > summary::before{
    content:""; width:5px; height:5px; flex:none; border-right:1.5px solid var(--ink-3);
    border-bottom:1.5px solid var(--ink-3); transform:rotate(-45deg); transition:transform .15s ease;
  }
  .more[open] > summary::before{transform:rotate(45deg)}
  .more > summary:hover{color:var(--ink-2)}

  /* ── 本次摘要 ───────────────────────────────────────── */
  /* 右列底部把「点下去会发生什么」提前写出来：既填掉两列的高度差，也让人在按
     大按钮之前就知道自己选了什么，而不是等确认框弹出来才看。 */
  .summary{border-top:1px solid var(--line); margin-top:auto}
  .summary dl{margin:0; padding:10px 16px 14px; display:grid; gap:7px}
  .summary dl > div{display:flex; gap:12px; align-items:baseline; font-size:12.5px}
  .summary dt{width:56px; flex:none; color:var(--ink-3)}
  .summary dd{margin:0; color:var(--ink-2); min-width:0}
  .summary dd b{font-weight:560; color:var(--ink)}
  /* 类选择器的 display 会盖掉 UA 的 [hidden]{display:none}，这里补一刀 */
  [hidden]{display:none !important}

  /* ── 输出 ───────────────────────────────────────────── */
  .console{
    margin-top:16px; border:1px solid var(--line); border-radius:var(--r);
    overflow:hidden; background:var(--console-bg);
  }
  .console .head{background:#221f19; border-bottom:1px solid #322d24}
  .console .head h2{color:#b3aa99}
  .console .head .aside{color:#7d7566}
  .console .head .link{color:#b3aa99}
  .console .head .link:hover{color:#e5ddce}
  .live{width:6px; height:6px; border-radius:50%; background:#4a4438; flex:none}
  .console.on .live{background:#8fb79a; animation:blip 1.05s ease-in-out infinite}
  pre#out{
    margin:0; padding:15px 18px 17px;
    height:clamp(180px,34vh,320px); overflow:auto;
    background:var(--console-bg); color:var(--console-ink);
    font:12.5px/1.72 ui-monospace,SFMono-Regular,"Cascadia Mono",Menlo,Consolas,monospace;
    white-space:pre-wrap; word-break:break-word; tab-size:2;
  }
  pre#out::-webkit-scrollbar{width:10px; height:10px}
  pre#out::-webkit-scrollbar-thumb{background:#332e25; border-radius:6px; border:2px solid var(--console-bg)}
  pre#out::-webkit-scrollbar-thumb:hover{background:#443d31}
  .empty{color:var(--console-dim); line-height:1.9}
  .empty b{color:#b3aa99; font-weight:560}

  footer{
    display:flex; gap:14px; align-items:baseline; flex-wrap:wrap;
    margin-top:13px; padding:0 2px; font-size:11.5px; color:var(--ink-3);
  }
  footer b{font-weight:560; color:var(--ink-2)}
  footer .sep{color:var(--line-2)}
  a.repo{color:var(--ink-2); text-decoration:none; border-bottom:1px solid var(--line-2);
         transition:color .12s ease, border-color .12s ease}
  a.repo:hover{color:var(--accent); border-color:var(--accent)}
  .help a{color:var(--accent); text-decoration:none; border-bottom:1px solid currentColor}
  .help a:hover{color:var(--accent-2)}

  /* ── 确认框 ─────────────────────────────────────────── */
  .modal{position:fixed; inset:0; display:none; place-items:center; z-index:50;
         background:rgba(28,26,22,.4); padding:20px}
  .modal.on{display:grid}
  .modal .panel{
    width:min(430px,100%); background:var(--surface);
    border:1px solid var(--line-2); border-radius:var(--r); padding:22px 22px 18px;
    box-shadow:0 24px 60px -20px rgba(28,26,22,.45);
  }
  .modal h3{margin:0 0 7px; font-size:15.5px; letter-spacing:-.01em}
  .modal p{margin:0 0 6px; font-size:13px; color:var(--ink-2); line-height:1.68}
  .modal .kv{
    margin:13px 0 18px; padding:10px 12px; border-radius:var(--r-sm);
    background:var(--surface-2); border:1px solid var(--line);
    font-size:12px; color:var(--ink-2); line-height:1.95;
  }
  .modal .kv span{color:var(--ink-3); display:inline-block; min-width:62px}
  .modal .row{display:flex; gap:8px; justify-content:flex-end}

  @media (prefers-reduced-motion: reduce){
    *{animation:none !important; transition:none !important}
  }
</style>
</head>
<body>
<div class="shell">

  <header class="topbar">
    <span class="seal" aria-hidden="true"></span>
    <div class="brand">
      <b>破甲一键通</b>
      <span class="tag">社区版</span>
      <span class="ver mono">v__VERSION__</span>
    </div>
    <span class="grow"></span>
    <span class="state" id="state"><i></i><span id="state-text">待命中</span></span>
  </header>

  <div class="updatebar" id="u-bar" hidden>
    <span class="u-dot" aria-hidden="true"></span>
    <span class="u-text" id="u-text"></span>
    <span class="grow"></span>
    <button type="button" class="btn primary" id="u-go">安装</button>
    <button type="button" class="link" id="u-no">以后再说</button>
  </div>

  <section class="hero">
    <h1>解锁 AI 编程工具被藏起来的能力</h1>
    <p class="lede">勾选你用到的软件，点一下「一键破甲」就行。没装的会自动跳过，改错了随时能还原。</p>
    <div class="cta">
      <button type="button" class="btn primary lg" id="go">一键破甲</button>
      <button type="button" class="btn" id="detect">先检测一下（只看不改）</button>
    </div>
    <p class="hint" id="hint"></p>
  </section>

  <details class="help">
    <summary>第一次用？三十秒看懂这个工具在做什么</summary>
    <div class="body">
      <div>
        <p class="q">「破甲」是什么</p>
        <p class="a">这些 AI 编程工具出厂时会把系统提示词收窄、把部分能力关掉。破甲就是把本机上这些被收窄的提示词恢复成完整版，让模型按你原本的意图干活。</p>
      </div>
      <div>
        <p class="q">它会改我电脑上的什么</p>
        <p class="a">只改这些软件安装目录里的提示词和配置文件，改之前先备份一份。不动系统设置、不动你的代码、不动账号数据。</p>
      </div>
      <div>
        <p class="q">后悔了怎么办</p>
        <p class="a">右边点「还原成原版」，会按备份逐字节恢复。软件自己升级后设置可能被覆盖，重跑一次就行。</p>
      </div>
      <div>
        <p class="q">源码和更新在哪</p>
        <p class="a">开源在 <a href="__REPO__" target="_blank" rel="noopener noreferrer">__REPO_NAME__</a>。更新日志、已知问题、反馈入口都在仓库里 —— 用着不对劲可以先翻一眼那里。</p>
      </div>
    </div>
  </details>

  <div class="grid">
    <div class="col">
      <div class="head"><h2>选软件</h2><span class="aside mono" id="count"></span></div>
      <div class="list" id="chips"></div>
      <div class="foot">
        <button type="button" class="link" id="all">全选</button>
        <button type="button" class="link" id="none">全不选</button>
        <span class="tip">没装的会跳过</span>
      </div>
    </div>

    <div class="col">
      <!-- 整块随「是否勾选 DSH」显示/隐藏：没勾就一点痕迹都不留，
           而不是压暗成一块读不懂的灰区。 -->
      <div id="dshblock">
        <div class="head">
          <h2>DSH 怎么处理</h2>
          <span class="aside">只影响 DeepSeek Harness</span>
        </div>
        <div class="opts" id="opts">
          <label class="choice on" id="c-inject">
            <input type="radio" name="mode" value="inject" checked>
            <span>
              <span class="ct">改配置文件 <span class="tag">默认</span></span>
              <span class="cd">直接把 DSH 的人格设定改掉。所有模式都生效，最彻底。</span>
            </span>
          </label>
          <label class="choice" id="c-preset">
            <input type="radio" name="mode" value="preset">
            <span>
              <span class="ct">只加一个模式 <span class="tag">更稳妥</span></span>
              <span class="cd">不动 DSH 的任何官方文件，只在模式列表里多一项「破甲模式」。你在下拉里选中它才生效，DSH 升级也不会把设置冲掉。</span>
            </span>
          </label>

          <label class="switchrow" id="gb-opt">
            <input type="checkbox" id="gitbash">
            <span class="track"></span>
            <span class="txt">
              <b>让 DSH 改用 Git Bash 执行命令</b>
              <span>Windows 自带的命令行在引号处理上容易出错，模型常在这儿翻车。打开后程序会自动准备一个便携版 Git Bash —— 不用你安装，也不改系统设置。改完要重启 DSH 才生效。</span>
            </span>
          </label>
        </div>
      </div>

      <div class="head"><h2>其他操作</h2></div>
      <div class="acts" id="acts"></div>
      <details class="more">
        <summary>更多工具（诊断、预演、快照）</summary>
        <div class="acts" id="acts2"></div>
      </details>

      <div class="summary">
        <div class="head"><h2>这次会做什么</h2></div>
        <dl>
          <div><dt>软件</dt><dd id="s-soft"></dd></div>
          <div id="s-row-mode"><dt>DSH</dt><dd id="s-mode"></dd></div>
          <div id="s-row-shell"><dt>命令行</dt><dd id="s-shell"></dd></div>
          <div><dt>反悔</dt><dd>随时点「还原成原版」逐字节恢复</dd></div>
        </dl>
      </div>
    </div>
  </div>

  <section class="console" id="console">
    <div class="head">
      <span class="live"></span><h2>运行详情</h2>
      <span class="aside mono" id="elapsed"></span>
      <span class="grow"></span>
      <button type="button" class="link" id="clear">清空</button>
    </div>
    <pre id="out"><span class="empty">这里会显示每一步在做什么。<b>一键破甲</b>会改文件，<b>先检测一下</b>只看不改 —— 拿不准就先检测。</span></pre>
  </section>

  <footer>
    <span>本地运行，只绑定 <b>127.0.0.1</b></span>
    <span class="sep">/</span>
    <span>改文件前自动备份，随时可还原</span>
    <span class="sep">/</span>
    <a class="repo" href="__REPO__" target="_blank" rel="noopener noreferrer">源码与更新日志：<b>__REPO_NAME__</b></a>
  </footer>
</div>

<div class="modal" id="modal">
  <div class="panel">
    <h3 id="m-title">确认操作</h3>
    <p id="m-desc"></p>
    <div class="kv" id="m-kv"></div>
    <div class="row">
      <button type="button" class="btn" id="m-cancel">取消</button>
      <button type="button" class="btn danger" id="m-ok">确认执行</button>
    </div>
  </div>
</div>

<script>
const TOKEN = "__TOKEN__";
const VERSION = "__VERSION__";
const TARGETS = __TARGETS__;
const ACTIONS = __ACTIONS__;
const IS_WIN = __ISWIN__;

const selected = new Set(TARGETS.map(t => t[0]));
const opts = {mode: "inject", gitBash: false};

const $ = id => document.getElementById(id);
const chipsEl = $("chips"), actsEl = $("acts"), acts2El = $("acts2"), outEl = $("out");
const stateEl = $("state"), stateText = $("state-text"), countEl = $("count");
const elapsedEl = $("elapsed"), consoleEl = $("console"), optsEl = $("opts");
const goBtn = $("go"), hintEl = $("hint");
const uBar = $("u-bar"), uText = $("u-text"), uGo = $("u-go"), uNo = $("u-no");

/* 软件清单 */
TARGETS.forEach(([key, label]) => {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "row";
  b.dataset.key = key;
  b.setAttribute("aria-pressed", "true");
  b.innerHTML = `<span class="box"></span><span class="lbl">${label}</span>`
    + (key === "dsh" ? `<span class="badge">有选项</span>` : "");
  b.onclick = () => {
    if (selected.has(key)) selected.delete(key); else selected.add(key);
    b.setAttribute("aria-pressed", selected.has(key));
    sync();
  };
  chipsEl.appendChild(b);
});

function sync(){
  countEl.textContent = `${selected.size}/${TARGETS.length}`;
  const on = selected.has("dsh");
  /* 没勾 DSH 就整块收起来 —— 留着压暗的控件只会让人问「为什么点不动」 */
  $("dshblock").hidden = !on;
  optsEl.querySelectorAll("input").forEach(el => el.disabled = !on);

  const n = selected.size;
  if (!n){
    hintEl.innerHTML = "还没勾选任何软件 —— 先在下面点一个。";
    goBtn.disabled = true;
  } else {
    hintEl.innerHTML = `已选 <b>${n}</b> 个软件 · 没装的会自动跳过 · 改错了随时能还原`;
    goBtn.disabled = busy;
  }
  paintSummary();
}

/* 右列底部的摘要：把「点下去会发生什么」提前写出来，不用等确认框。
   没勾 DSH 时那两行直接不显示，和上面整块的隐藏保持一致。 */
function paintSummary(){
  const n = selected.size, dsh = selected.has("dsh");
  $("s-soft").innerHTML = n
    ? `<b>${n}</b> 个${n === TARGETS.length ? "（全部）" : ""}`
    : `<b>未选</b> —— 先勾一个`;
  $("s-row-mode").hidden = !dsh;
  $("s-mode").textContent = opts.mode === "preset"
    ? "只加一个模式（不改官方文件）" : "改配置文件（所有模式生效）";
  $("s-row-shell").hidden = !dsh || !IS_WIN;
  $("s-shell").textContent = opts.gitBash
    ? "Git Bash（重启 DSH 后生效）" : "PowerShell（官方默认）";
}
$("all").onclick = () => {
  TARGETS.forEach(t => selected.add(t[0]));
  [...chipsEl.children].forEach(c => c.setAttribute("aria-pressed", "true"));
  sync();
};
$("none").onclick = () => {
  selected.clear();
  [...chipsEl.children].forEach(c => c.setAttribute("aria-pressed", "false"));
  sync();
};

/* DSH 选项 */
function paintMode(){
  $("c-inject").classList.toggle("on", opts.mode === "inject");
  $("c-preset").classList.toggle("on", opts.mode === "preset");
}
optsEl.querySelectorAll('input[name="mode"]').forEach(el => {
  el.onchange = () => {
    if (el.checked){ opts.mode = el.value; paintMode(); paintSummary(); }
  };
});
$("gitbash").onchange = e => { opts.gitBash = e.target.checked; paintSummary(); };
if (!IS_WIN) $("gb-opt").style.display = "none";

/* 操作：一键破甲单独做成大按钮，其余按「常用 / 更多」两组。
   status 不出现在列表里 —— 顶部「先检测一下」就是它，列两遍只会让人猜两者有什么不同。 */
const GROUP = {revert: 1, diagnose: 2, dryrun: 2, snapshot: 2, compare: 2};
let busy = false;
ACTIONS.forEach(([key, name, desc, kind]) => {
  const g = GROUP[key];
  if (!g) return;                       /* apply 由顶部大按钮承担 */
  const b = document.createElement("button");
  b.type = "button";
  b.className = "act";
  b.dataset.kind = kind;
  b.dataset.action = key;
  b.innerHTML = `<span class="n">${name}</span><span class="d">${desc}</span><span class="go">›</span>`;
  b.onclick = () => { if (!busy) run(key); };
  (g === 1 ? actsEl : acts2El).appendChild(b);
});

/* 确认框 */
const modal = $("modal");
let pending = null;
function ask(action, name){
  pending = action;
  const list = [...selected];
  $("m-title").textContent = `确认${name}？`;
  $("m-desc").textContent = list.length
    ? `将对下面 ${list.length} 个软件执行，这会修改它们的提示词或配置文件（改前自动备份）。`
    : "还没勾选任何软件，会按「全部」处理，这会修改它们的提示词或配置文件（改前自动备份）。";
  const kv = [];
  /* 显示软件的中文名，不显示 wb / wbintl 这种内部代号；超过四个就折成
     「前三个 等 N 个」—— 十七个名字堆满一屏，反而没人看。 */
  const names = list.map(k => {
    const t = TARGETS.find(x => x[0] === k);
    return t ? t[1] : k;
  });
  const shown = !names.length ? "全部"
    : names.length > 4 ? names.slice(0, 3).join(" / ") + ` 等 ${names.length} 个`
    : names.join(" / ");
  kv.push(`<div><span>软件</span>${shown}</div>`);
  if (selected.has("dsh") || !list.length){
    kv.push(`<div><span>DSH</span>${opts.mode === "preset" ? "只加一个模式（不改官方文件）" : "改配置文件（所有模式生效）"}</div>`);
    if (IS_WIN) kv.push(`<div><span>命令行</span>${opts.gitBash ? "改用 Git Bash（要重启 DSH）" : "保持 PowerShell"}</div>`);
  }
  kv.push(`<div><span>反悔</span>用「还原成原版」逐字节恢复</div>`);
  $("m-kv").innerHTML = kv.join("");
  modal.classList.add("on");
  $("m-cancel").focus();
}
$("m-cancel").onclick = () => { modal.classList.remove("on"); pending = null; };
$("m-ok").onclick = () => { modal.classList.remove("on"); if (pending) run(pending); pending = null; };
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && modal.classList.contains("on")){
    modal.classList.remove("on"); pending = null;
  }
});

$("go").onclick = () => { if (!busy) ask("apply", "一键破甲"); };
$("detect").onclick = () => { if (!busy) run("status"); };
$("clear").onclick = () => {
  outEl.innerHTML = '<span class="empty">已清空。</span>';
  elapsedEl.textContent = "";
  setState("idle");
};

/* ANSI → HTML */
const ANSI = {
  "30":"#7d7566","31":"#e08a7c","32":"#8fc0a0","33":"#d9bb7c","34":"#8fa8cf",
  "35":"#c3a0d6","36":"#86c3c6","37":"#e5ddce","90":"#7d7566","91":"#e08a7c",
  "92":"#8fc0a0","93":"#d9bb7c","94":"#8fa8cf","95":"#c3a0d6","96":"#86c3c6","97":"#fbf9f4"
};
function esc(s){ return s.replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c])); }
function ansiToHtml(line){
  let out = "", open = 0, last = 0, m;
  const re = /\x1b\[([0-9;]*)m/g;
  while ((m = re.exec(line)) !== null){
    out += esc(line.slice(last, m.index));
    last = m.index + m[0].length;
    const codes = m[1].split(";").filter(Boolean);
    if (!codes.length || codes.includes("0")){
      out += "</span>".repeat(open); open = 0; continue;
    }
    for (const c of codes){
      const color = ANSI[c];
      if (color){ out += `<span style="color:${color}">`; open++; }
      else if (c === "1"){ out += `<span style="font-weight:600">`; open++; }
    }
  }
  out += esc(line.slice(last));
  return out + "</span>".repeat(open);
}

let stateTimer = null;
function setState(kind){
  clearTimeout(stateTimer);
  stateEl.classList.remove("busy", "bad", "good");
  if (kind === "busy"){ stateEl.classList.add("busy"); stateText.textContent = "处理中…"; }
  else if (kind === "bad"){ stateEl.classList.add("bad"); stateText.textContent = "有问题，看下面"; }
  else if (kind === "good"){ stateEl.classList.add("good"); stateText.textContent = "完成"; }
  else stateText.textContent = "待命中";
}
/* 输出里出现这些字样就当成「没跑通」，胶囊转红，省得小白翻几百行找 */
const BAD = /(\[!\]|\[x\]|Traceback|失败|出错|错误：|Error:|not found|拒绝访问)/i;

let started = false;
async function run(action){
  if (busy) return;
  busy = true;
  setState("busy");
  consoleEl.classList.add("on");
  goBtn.disabled = true;
  document.querySelectorAll(".act").forEach(b => b.disabled = true);
  if (!started){ outEl.innerHTML = ""; started = true; }
  const t0 = Date.now();
  const timer = setInterval(() => {
    elapsedEl.textContent = ((Date.now() - t0) / 1000).toFixed(1) + "s";
  }, 100);
  let plain = "";
  try{
    const res = await fetch(`/api/run?t=${TOKEN}`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        action, targets: [...selected], confirm: true,
        dsh_mode: opts.mode, git_bash: opts.gitBash
      })
    });
    if (!res.ok || !res.body){
      outEl.insertAdjacentHTML("beforeend", `<span style="color:#e08a7c">请求失败：HTTP ${res.status}</span>\n`);
      plain += "失败";
    } else {
      const reader = res.body.getReader();
      const dec = new TextDecoder("utf-8");
      let buf = "";
      while (true){
        const {done, value} = await reader.read();
        if (done) break;
        buf += dec.decode(value, {stream: true});
        const parts = buf.split("\n");
        buf = parts.pop();
        for (const p of parts){
          plain += p + "\n";
          outEl.insertAdjacentHTML("beforeend", ansiToHtml(p) + "\n");
        }
        outEl.scrollTop = outEl.scrollHeight;
      }
      if (buf){
        plain += buf;
        outEl.insertAdjacentHTML("beforeend", ansiToHtml(buf) + "\n");
      }
    }
  }catch(e){
    plain += String(e);
    outEl.insertAdjacentHTML("beforeend", `<span style="color:#e08a7c">${esc(String(e))}</span>\n`);
  }finally{
    clearInterval(timer);
    busy = false;
    consoleEl.classList.remove("on");
    outEl.scrollTop = outEl.scrollHeight;
    const bad = BAD.test(plain);
    setState(bad ? "bad" : "good");
    stateTimer = setTimeout(() => { if (!busy) setState("idle"); }, bad ? 12000 : 5000);
    document.querySelectorAll(".act").forEach(b => b.disabled = false);
    sync();
  }
}

sync();

/* ── 更新提示 ────────────────────────────────────────────────
   进页面问一次「有没有新版」：只读 GitHub 的发布信息，不带任何本机内容。
   查到就亮一条，装不装、什么时候装，由按按钮的人决定 —— 从不自己动手。 */
async function probeUpdate(){
  /* 点过「以后再说」就这次版本内不再问（下次开还是同一版，没必要反复问） */
  if (localStorage.getItem("pojia.skipUpdate") === VERSION) return;
  try{
    const res = await fetch(`/api/update?t=${TOKEN}`);
    if (!res.ok) return;
    const d = await res.json();
    if (!d.ok || !d.newer) return;
    uText.innerHTML = `有新版本 <b class="mono">v${esc(d.latest)}</b> 可以装`
      + `（当前 v${esc(d.current)}）。装完关掉这个窗口就行，程序会自己换好再打开。`;
    uGo.textContent = `安装 v${d.latest}`;
    uBar.hidden = false;
  }catch(e){ /* 没网、限流、被墙都当没这回事 */ }
}

uGo.onclick = () => {
  uBar.hidden = true;
  run("update");
};
uNo.onclick = () => {
  uBar.hidden = true;
  try{ localStorage.setItem("pojia.skipUpdate", VERSION); }catch(e){}
};

probeUpdate();
</script>
</body>
</html>
"""


def render_page():
    return (PAGE
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

    def do_GET(self):
        if not self._authorized():
            self.send_error(403, "bad token")
            return
        if self.path.startswith("/api/update"):
            body = json.dumps(check_update(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
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
        try:
            while True:
                chunk = proc.stdout.readline()
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            proc.kill()
        finally:
            try:
                proc.stdout.close()
            except Exception:
                pass
            proc.wait()


def main():
    if not FROZEN and not os.path.isfile(CORE):
        print("找不到核心脚本：%s" % CORE)
        return 1
    host = "127.0.0.1"
    srv = ThreadingHTTPServer((host, 0), Handler)
    port = srv.server_address[1]
    url = "http://%s:%d/?t=%s" % (host, port, TOKEN)
    print("=" * 66, flush=True)
    print(" 破甲一键通 · 图形界面   v%s%s"
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
