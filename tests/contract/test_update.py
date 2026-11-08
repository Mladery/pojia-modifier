# -*- coding: utf-8 -*-
"""升级落盘的单点回归。

这是 tests/contract 里唯一 import 被测模块的地方，理由说清楚：下载那一步没有
能在断网环境跑的 CLI 入口（`--update` 的地址写死 GitHub），而 1.01.6 的毛病
恰好只在这一步 —— state/ 不存在时 `open(....part)` 直接 Errno 2，界面上只看到
一行「落盘失败」，没人知道是缺个目录。

所以退一步：在沙箱副本里把 http_get / update_asset 换成夹具，调真实的
update_download，然后看磁盘上的字节。被测的仍然是那几十行里的目录处理。
"""
import os
import re
import subprocess
import sys
import time

import pytest

SNIPPET = r'''
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[1])))
import pojia
pojia.http_get = lambda url, timeout=8, progress=None: b"MZ-fake-setup-bytes"
pojia.update_asset = lambda: "pojia-modifier-windows-x64-setup.exe"
ok, msg = pojia.update_download(
    {"pojia-modifier-windows-x64-setup.exe": "http://example.invalid/x"},
    sys.argv[2])
print("RESULT", ok, msg)
'''


def _download(box, dst):
    return subprocess.run(
        [sys.executable, "-c", SNIPPET, box.prog, dst],
        cwd=box.root, env=box.env(),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120,
    )


def test_update_download_creates_missing_state_dir(box):
    """刚装好、还没跑过 apply 的目录里没有 state/ —— 升级不能死在这儿。"""
    dst = os.path.join(box.prog_dir, "state",
                       "_update_pojia-modifier-windows-x64-setup.exe")
    assert not os.path.isdir(os.path.dirname(dst)), "前置条件：state/ 本来不存在"

    p = _download(box, dst)
    text = box.out(p)
    assert "RESULT True" in text, text
    assert os.path.isfile(dst), text
    with open(dst, "rb") as fh:
        assert fh.read() == b"MZ-fake-setup-bytes"
    # 半成品不许留下：校验失败要删，成功要改名
    assert not os.path.exists(dst + ".part")


def test_update_download_keeps_existing_files(box):
    """state/ 里已经有别的东西时，建目录不能把原来的文件抹掉。"""
    state = os.path.join(box.prog_dir, "state")
    os.makedirs(state)
    keep = os.path.join(state, "user-note.txt")
    with open(keep, "w", encoding="utf-8") as fh:
        fh.write("别动我")

    dst = os.path.join(state, "_update_pojia-modifier-windows-x64-setup.exe")
    p = _download(box, dst)
    assert "RESULT True" in box.out(p), box.out(p)
    assert os.path.isfile(keep)


# ---------------------------------------------------------------------------
# 换装批处理的进程检测
#
# 1.01.8 的第二个坑：批处理里写的是 `tasklist | find /i "x"`。启动器要是
# Git Bash 那一套（usr\bin 排在 System32 前面），`find` 命中的是 GNU 的，
# `find /i "pojia-modifier.exe"` 在它眼里是「从路径 /i 开始遍历」，MSYS 再把
# /i 翻成 I:\ —— 整个盘扫一遍。人看到的就是「升级卡在 find 上」。
# ---------------------------------------------------------------------------

BATCH_SNIPPET = r'''
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[1])))
import pojia
pojia.FROZEN = True
pojia.SELF_EXE = r"C:\Users\t\AppData\Local\Programs\pojia-modifier\pojia-modifier.exe"
pojia.install_meta = lambda: {"dir": r"C:\Users\t\AppData\Local\Programs\pojia-modifier"}
pojia.setup_install_dir = lambda: ""
lines = []
pojia._swap_script = lambda ls, name: (lines.extend(ls), r"C:\temp\_x.bat")[1]
pojia._run_detached = lambda argv: True
pojia.update_install(r"C:\Users\t\state\_update_pojia-modifier-windows-x64-setup.exe")
print("BATCH-BEGIN")
for line in lines:
    print(line)
print("BATCH-END")
'''


def _batch_lines(box):
    p = subprocess.run(
        [sys.executable, "-c", BATCH_SNIPPET, box.prog],
        cwd=box.root, env=box.env(),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120,
    )
    text = box.out(p)
    assert "BATCH-BEGIN" in text, text
    body = text.split("BATCH-BEGIN", 1)[1].split("BATCH-END", 1)[0]
    return [ln for ln in body.strip().splitlines() if ln.strip()]


@pytest.mark.skipif(sys.platform != "win32", reason="换装批处理只有 Windows 上有")
def test_swap_batch_calls_system_tools_by_full_path(box):
    """PATH 里只要有个同名程序，裸写 find/tasklist 就不是系统那个了。"""
    lines = _batch_lines(box)
    joined = "\n".join(lines)
    assert not re.search(r"(^|[|&]\s*)find(\.exe)?\s", joined), joined
    for tool in ("tasklist", "findstr", "taskkill", "ping"):
        uses = [ln for ln in lines if tool in ln]
        assert uses, "批处理里没用到 %s？" % tool
        for ln in uses:
            # 注意 %SystemRoot% 里的 % 要写成 %%：这一行本身用 % 拼字符串
            want = "%%SystemRoot%%\\System32\\%s.exe" % tool
            assert want in ln, ln
    assert 'set "PATH=%SystemRoot%\\System32;' in joined


@pytest.mark.skipif(sys.platform != "win32", reason="换装批处理只有 Windows 上有")
def test_swap_batch_wait_loop_terminates(box, tmp_path):
    """把 :swap 换成 echo 跑真循环：进程不在时几秒内必须走到 swap。"""
    lines = _batch_lines(box)
    head = lines[:lines.index(":swap")]
    bat = tmp_path / "_wait.bat"
    bat.write_text("\r\n".join(head + [":swap", "echo SWAP-REACHED"]) + "\r\n",
                   encoding="mbcs")
    t0 = time.time()
    r = subprocess.run(["cmd", "/c", str(bat)],
                       capture_output=True, text=True, timeout=90)
    used = time.time() - t0
    assert "SWAP-REACHED" in (r.stdout or ""), (r.stdout, r.stderr)
    assert used < 20, "过了 %.1fs 才走到 swap，说明又在扫盘" % used


# ---------------------------------------------------------------------------
# 「谁算新版」
#
# 1.01-mod 是从 1.01.9-beta 切出来的：内容一样，序号反而小。纯数字比会让
# 稳定版用户被劝「升级」回自己那份测试版 —— 界面顶上就冒出
# 「有新版本 v1.01.9-beta 可以装（当前 v1.01-mod）」。
# ---------------------------------------------------------------------------

NEWER_SNIPPET = r'''
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[1])))
import pojia
for item in sys.argv[2:]:
    cand, cur = item.split("|")
    print("%s|%s|%d" % (cand, cur, 1 if pojia.update_newer(cand, cur) else 0))
'''


def _newer(cand, cur):
    core = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src", "pojia.py"))
    p = subprocess.run([sys.executable, "-c", NEWER_SNIPPET, core, cand + "|" + cur],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    text = (p.stdout or b"").decode("utf-8", "replace").strip()
    assert text.endswith("|0") or text.endswith("|1"), (text, p.stderr)
    return text.endswith("|1")


@pytest.mark.parametrize("cand,cur,want", [
    # 稳定版不被自己的上游打动
    ("1.01.9-beta", "1.01-mod", False),
    ("1.01.10-beta", "1.01-mod", False),   # 同系列一律不推：稳定版已经是这条线的终点
    ("1.01-mod", "1.01-mod", False),
    # 跨系列照常推
    ("1.02.1-beta", "1.01-mod", True),
    ("1.02-mod", "1.01-mod", True),
    # 测试版之间按数字比
    ("1.01.9-beta", "1.01.8-beta", True),
    ("1.01.8-beta", "1.01.9-beta", False),
    # 稳定版盖过同系列测试版：双向都算新。
    # 这一条的数字是往下走的（1.01 < 1.01.9，1.02 < 1.02.1），纯数字比会判成
    # 「更旧」—— 装测试版的人就被钉在测试通道上，永远升不到自己的稳定版。
    ("1.01-mod", "1.01.9-beta", True),
    ("1.02-mod", "1.02.1-beta", True),
    # 反方向不降级：已经装了稳定版，不会被自己的上游测试版拉回去
    ("1.01.9-beta", "1.01-mod", False),
    ("1.02.1-beta", "1.02-mod", False),
    # 跨系列照常：新线的测试版该推还是推
    ("1.03.1-beta", "1.02-mod", True),
])
def test_update_newer(cand, cur, want):
    assert _newer(cand, cur) is want


# ---------------------------------------------------------------------------
# 候选发布怎么挑
#
# 光有 update_newer 还不够：它拿到的 cand 是 update_check 挑出来的那一个。
# 同一系列里稳定版与测试版并存时，1.02.1-beta 的数字比 1.02-mod 大，「取绝对
# 最大」会永远挑中测试版本身 —— 装了测试版的人收到的 cand 就是自己，
# newer 恒为 false，稳定版发了也看不到提示。
# ---------------------------------------------------------------------------

CHECK_SNIPPET = r'''
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[1])))
import pojia
pojia.DISPLAY_VERSION = sys.argv[3]
pojia.update_channel = lambda: sys.argv[4]
pojia.http_get = lambda url, timeout=8: sys.argv[2].encode("utf-8")
ver, assets, err = pojia.update_check()
print("GOT", ver, 1 if ver and pojia.update_newer(ver) else 0, err)
'''


def _pick(tags, cur, channel):
    """-> (挑中的 tag, 它算不算该装的新版)。"""
    import json
    data = [{"tag_name": "v" + t, "draft": False,
             "assets": [{"name": "a", "browser_download_url": "u"}]} for t in tags]
    core = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src", "pojia.py"))
    p = subprocess.run([sys.executable, "-c", CHECK_SNIPPET, core,
                        json.dumps(data), cur, channel],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    text = (p.stdout or b"").decode("utf-8", "replace").strip()
    assert text.startswith("GOT "), (text, (p.stderr or b"").decode("utf-8", "replace"))
    parts = text.split()
    return parts[1], parts[2] == "1"


@pytest.mark.parametrize("tags,cur,channel,want_tag,want_newer", [
    # 测试版机器：同系列的稳定版虽然序号更小，也得被挑出来
    (["1.02.1-beta", "1.02-mod"], "1.02.1-beta", "beta", "1.02-mod", True),
    # 稳定版机器：同系列的上游测试版不当候选
    (["1.02.1-beta", "1.02-mod"], "1.02-mod", "beta", "1.02.1-beta", False),
    # 跨系列照旧推新线
    (["1.02-mod", "1.03.1-beta"], "1.02-mod", "beta", "1.03.1-beta", True),
    # 稳定通道里测试版压根不参与
    (["1.02.1-beta", "1.01-mod"], "1.01-mod", "mod", "1.01-mod", False),
])
def test_update_check_picks_the_one_worth_installing(tags, cur, channel,
                                                     want_tag, want_newer):
    tag, newer = _pick(tags, cur, channel)
    assert tag == want_tag, "挑中的是 %s，期望 %s（候选 %s）" % (tag, want_tag, tags)
    assert newer is want_newer
