#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打包产物的图形界面冒烟：零参数启动 → 取地址 → 拉首页 → 点一次「检测状态」。

为什么要单独一个脚本：GUI 在打包版里是 **runpy 从数据文件里跑起来的**，构建时漏了
`--add-data`、或者 runpy 那条路走不通，`--version` 和 `--status` 全都照样绿 —— 只有
真的把界面拉起来才会暴露。CI 的冒烟步骤调它。

**故意不带参数**：零参数（= 双击）就是用户默认走的那条路。界面起不来的话程序会
退回命令行菜单，菜单读 stdin 拿到 EOF 就退出，于是这里拿不到地址、直接失败 ——
比只测 `--gui` 更贴近真实。

用法：
    python tools/gui_smoke.py build/dist/pojia-modifier.exe
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.request

URL_RE = re.compile(r"(http://127\.0\.0\.1:\d+/\?t=[A-Za-z0-9_\-]+)")


def fail(msg):
    print("GUI smoke FAIL: " + msg)
    return 1


def main():
    if len(sys.argv) < 2:
        return fail("用法：python tools/gui_smoke.py <可执行文件>")
    exe = sys.argv[1]
    if not os.path.isfile(exe):
        return fail("找不到产物：%s" % exe)

    env = dict(os.environ)
    env["POJIA_GUI_NO_OPEN"] = "1"          # 别在 CI 上弹浏览器
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen([exe], env=env,
                            stdin=subprocess.DEVNULL,      # 万一退回菜单，别卡在 input()
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    url = None
    try:
        deadline = time.time() + 180        # 单文件包要先解包，给足时间
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", "replace").rstrip()
            m = URL_RE.search(text)
            if m:
                url = m.group(1)
                break
        if not url:
            return fail("没等到界面地址（零参数启动没进界面，或者包里没带 pojia_gui.py）")

        html = urllib.request.urlopen(url, timeout=60).read().decode("utf-8", "replace")
        if "破甲修改器" not in html:
            return fail("首页内容不对：%r" % html[:200])
        print("  首页 OK，%d 字节" % len(html))

        base, token = url.split("?t=", 1)
        body = json.dumps({"action": "status", "targets": ["claude"]}).encode("utf-8")
        req = urllib.request.Request(base + "?t=" + token, data=body,
                                     headers={"Content-Type": "application/json"})
        # 这一步会真的把「自己」当子进程拉起来跑 --status，等于顺带验了
        # build_cmd 的冻结态分支和输出流回页面。
        out = urllib.request.urlopen(req, timeout=300).read().decode("utf-8", "replace")
        if "claude" not in out.lower():
            return fail("动作输出不对：%r" % out[:400])
        print("  动作 OK，%d 字节输出" % len(out))
        print("GUI smoke OK")
        return 0
    except Exception as e:
        return fail("%s: %s" % (type(e).__name__, e))
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=30)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
