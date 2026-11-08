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
import subprocess
import sys

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
