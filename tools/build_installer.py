#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 onedir 产物打成一个 Windows 安装程序（setup.exe）。

为什么单独一个脚本：makensis 的 `/D` 宏必须出现在脚本路径**之前**，而且值里带
空格时要自己加引号；顺带把「makensis 到底装在哪」这件事收在一处 —— CI 上是
choco/scoop 装的，用户本机可能压根没装。

产物默认落在 `out/<name>-windows-x64-setup.exe`，和裸 exe 用同一个名字规则，
`--update` 起来之后只认这一个。

用法：
    python tools/build_installer.py --src build/dist-onedir/pojia-modifier
    python tools/build_installer.py --src build/dist-onedir/pojia-modifier --version 1.0
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NSI = os.path.join(ROOT, "tools", "installer.nsi")

# makensis 不在 PATH 上是常态：choco 装到 Program Files，scoop 装到用户目录。
CANDIDATES = [
    r"C:\Program Files (x86)\NSIS\makensis.exe",
    r"C:\Program Files\NSIS\makensis.exe",
    os.path.expanduser(r"~\scoop\apps\nsis\current\makensis.exe"),
    os.path.expanduser(r"~\scoop\shims\makensis.exe"),
    "/usr/bin/makensis",
    "/usr/local/bin/makensis",
]


def find_makensis():
    p = shutil.which("makensis")
    if p:
        return p
    for c in CANDIDATES:
        if os.path.isfile(c):
            return c
    return ""


def core_version():
    """从源码读 VERSION，省得版本号在三个地方各写一遍。"""
    path = os.path.join(ROOT, "src", "pojia.py")
    with open(path, encoding="utf-8", errors="replace") as f:
        m = re.search(r'^VERSION\s*=\s*"([^"]+)"', f.read(), re.M)
    return m.group(1) if m else "0.0"


LICENSE_MD = os.path.join(ROOT, "docs", "disclaimer.md")


def md_to_text(md):
    """把disclaimer.md 压成安装向导能显示的纯文本。

    NSIS 的协议页只吃纯文本（要用 RTF 得自己转，不值得）。Markdown 的记号
    直接显示出来会很怪 —— `**`、`>`、`|---|` 混在条款里像乱码。这里只做
    「去掉记号、保留文字」，不重排：段落靠空行分，长行交给编辑框自己折。

    表格压成一条一行、用空格隔开，比留一竖排 `|` 好读。
    """
    out = []
    for raw in md.splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            continue
        if re.match(r"^\s*\|[\s:|-]+\|\s*$", line):
            continue                                  # |---|---| 分隔行
        if line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            out.append("   ".join(c for c in cells if c))
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)        # 标题记号
        line = re.sub(r"^>\s?", "", line)             # 引用记号
        line = re.sub(r"^\s*[-*+]\s+", "  · ", line)  # 无序列表
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)  # 粗体
        line = re.sub(r"`([^`]+)`", r"\1", line)      # 行内代码
        line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", line)   # 链接只留文字
        if re.match(r"^\s*-{3,}\s*$", line):
            line = "—" * 24
        out.append(line)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out))
    return text.strip() + "\n"


def write_license():
    """生成 build/LICENSE.txt，返回路径；源文件不在就返回空串。

    编码必须是带 BOM 的 UTF-8：NSIS 靠 BOM 判断编码，不带 BOM 的中文在协议页
    里会变成一堆问号。
    """
    if not os.path.isfile(LICENSE_MD):
        return ""
    with open(LICENSE_MD, encoding="utf-8") as f:
        text = md_to_text(f.read())
    path = os.path.join(ROOT, "build", "LICENSE.txt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(text)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join("build", "dist-onedir", "pojia-modifier"),
                    help="onedir 产物目录（含 pojia-modifier.exe 与 _internal/）")
    ap.add_argument("--out", default=os.path.join("out", "pojia-modifier-windows-x64-setup.exe"))
    ap.add_argument("--version", default="", help="默认取源码里的 VERSION")
    ap.add_argument("--makensis", default="", help="指定 makensis 路径")
    a = ap.parse_args()

    src = os.path.abspath(a.src)
    exe = os.path.join(src, "pojia-modifier.exe")
    if not os.path.isfile(exe):
        print("没有找到 onedir 产物：%s" % exe, file=sys.stderr)
        return 1
    if not os.path.isdir(os.path.join(src, "_internal")):
        print("警告：%s 下没有 _internal/，装出来可能起不来" % src, file=sys.stderr)

    mk = a.makensis or find_makensis()
    if not mk:
        print("找不到 makensis。装一个：choco install nsis / scoop install nsis", file=sys.stderr)
        return 1

    ver = a.version or core_version()
    out = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)

    # 安装包没有协议页就不该出包：条款是发布物的一部分，不是可选项。
    lic = write_license()
    if not lic:
        print("没有 docs/disclaimer.md，装出来就没有协议页 —— 先把它补回来。", file=sys.stderr)
        return 1

    # /D 的值不能加引号（makensis 会连引号一起当值），所以路径里有空格就过不去。
    for label, val in (("SRCDIR", src), ("OUTFILE", out), ("LICENSE", lic)):
        if " " in val:
            print("%s 里有空格，makensis 的 /D 吃不下：%s" % (label, val), file=sys.stderr)
            return 1

    cmd = [mk, "/V2",
           "/DVERSION=%s" % ver,
           "/DSRCDIR=%s" % src,
           "/DOUTFILE=%s" % out,
           "/DLICENSE=%s" % lic,
           NSI]
    print("+ %s" % " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print("makensis 失败，退出码 %d" % r.returncode, file=sys.stderr)
        return r.returncode

    if not os.path.isfile(out) or os.path.getsize(out) < 1024 * 1024:
        print("产物不对劲：%s" % out, file=sys.stderr)
        return 1
    print("setup: %s（%.1f MB，版本 %s）" % (out, os.path.getsize(out) / 1048576.0, ver))
    return 0


if __name__ == "__main__":
    sys.exit(main())
