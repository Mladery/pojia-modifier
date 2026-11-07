#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把一个 onedir 产物打成 Linux / macOS 的自解压安装包。

产物结构：`tools/installer.sh` 的正文 + 一行载荷标记 + 一份 tar.gz。
装、升级、卸载的逻辑全在 installer.sh 里，这个脚本只负责把 `__APP__` / `__VERSION__`
/ `__ASSET__` 三个占位符填掉、再把载荷接上去。

为什么不做 .deb / .pkg：两者都是系统级安装，装到 /usr 或 /Applications，
`--update` 每次都得提权，自动更新就废了。Windows 那边装 %LOCALAPPDATA%
也是同一个理由。自解压脚本装到 ~/.local，无 sudo、可自更新。

用法：
    python tools/build_unix_installer.py --src build/dist-onedir/pojia-modifier --asset linux-x64
    python tools/build_unix_installer.py --src ... --asset macos-arm64 --out out/x.command
"""

import argparse
import gzip
import io
import os
import re
import shutil
import sys
import tarfile
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADER = os.path.join(ROOT, "tools", "installer.sh")
SRC_PY = os.path.join(ROOT, "src", "pojia.py")
APP = "pojia-modifier"

# 载荷标记。installer.sh 里用 awk 找这一行，下一行起就是 gzip 数据。
MARK = "__POJIA_PAYLOAD_BELOW__"


def core_version():
    """从源码读 VERSION。版本号只写一处，别处都是读出来的。"""
    with open(SRC_PY, encoding="utf-8", errors="replace") as f:
        s = f.read()
    ver = re.search(r'^VERSION\s*=\s*"([^"]+)"', s, re.M)
    return ver.group(1) if ver else "0.0"


def default_out(asset):
    ext = ".command" if asset.startswith("macos-") else ".run"
    return os.path.join(ROOT, "out", "%s-%s-installer%s" % (APP, asset, ext))


def make_payload(src):
    """把 onedir 目录压成 tar.gz 字节。

    手动构造 TarInfo 而不是 tar.add()：add() 会把构建机的 uid / gid / 用户名
    写进去，解包时看着像别人的文件。这里统一成 0:0 + 固定的 0755 / 0644。
    """
    buf = io.BytesIO()
    # mtime=0 让同一份产物两次构建出同一个字节流，方便比对。
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w") as tar:
            for root, dirs, files in os.walk(src):
                dirs.sort()
                rel = os.path.relpath(root, src)
                # tar 里永远用正斜杠。os.path.join 在 Windows 上给的是反斜杠，
                # 打出来的包在 Linux 上会解出一串名字里带 \ 的文件。
                arc_root = APP if rel == "." else APP + "/" + rel.replace(os.sep, "/")
                ti = tarfile.TarInfo(arc_root)
                ti.type = tarfile.DIRTYPE
                ti.mode = 0o755
                ti.mtime = 0
                ti.uid = ti.gid = 0
                ti.uname = ti.gname = "root"
                tar.addfile(ti)
                for name in sorted(files):
                    p = os.path.join(root, name)
                    st = os.stat(p)
                    ti = tarfile.TarInfo(arc_root + "/" + name)
                    ti.size = st.st_size
                    # 可执行位只给真正需要的那几个：主程序，以及 .so / .dylib
                    # 之外的东西一律 0644。
                    exe = name == APP or name.endswith((".so", ".dylib")) or (
                        st.st_mode & 0o111 and not name.endswith(".py"))
                    ti.mode = 0o755 if exe else 0o644
                    ti.mtime = 0
                    ti.uid = ti.gid = 0
                    ti.uname = ti.gname = "root"
                    with open(p, "rb") as f:
                        tar.addfile(ti, f)
    return buf.getvalue()


def build(src, asset, out, version=""):
    if not os.path.isdir(src):
        print("没有这个目录：%s" % src, file=sys.stderr)
        return 1
    exe = os.path.join(src, APP)
    if not os.path.isfile(exe):
        print("%s 里没有 %s —— 要 onedir 产物，不是单文件" % (src, APP), file=sys.stderr)
        return 1
    if not os.path.isdir(os.path.join(src, "_internal")):
        print("%s 里没有 _internal/ —— 单文件产物装出来会缺依赖，不打包" % src,
              file=sys.stderr)
        return 1

    ver = version or core_version()
    with open(HEADER, encoding="utf-8", newline="\n") as f:
        head = f.read()
    if MARK not in head:
        print("%s 里没有载荷标记 %s" % (HEADER, MARK), file=sys.stderr)
        return 1

    # 必须从**最后**一次出现处切：模板里的 awk 也写着这个标记（`/^__...__$/`），
    # 用 split() 会从那一行切开，剩下的头部连引号都不闭合。
    head = head[:head.rfind(MARK)].rstrip("\n") + "\n"
    # 程序名也灌进去，别让 installer.sh 自己写死一份：写死就会和这里的 APP 走岔，
    # 装的时候去找一个载荷里不存在的目录，报「载荷里没有 xxx，包坏了」。
    head = (head.replace("__APP__", APP)
                .replace("__VERSION__", ver)
                .replace("__ASSET__", asset))
    left = [m for m in ("__APP__", "__VERSION__", "__ASSET__") if m in head]
    if left:
        print("模板占位符没替换干净：%s" % ", ".join(left), file=sys.stderr)
        return 1

    payload = make_payload(src)
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".part"
    with open(tmp, "wb") as f:
        f.write(head.encode("utf-8"))
        f.write((MARK + "\n").encode("ascii"))
        f.write(payload)
    os.chmod(tmp, 0o755)
    os.replace(tmp, out)
    print("%s  %s  %.1f MB（版本 %s）" % (
        out, asset, os.path.getsize(out) / 1048576.0, ver))
    return 0


def main():
    ap = argparse.ArgumentParser(description="打 Linux / macOS 自解压安装包")
    ap.add_argument("--src", required=True, help="onedir 产物目录（里面有 pojia-modifier）")
    ap.add_argument("--asset", required=True,
                    help="linux-x64 / macos-x64 / macos-arm64")
    ap.add_argument("--out", default="", help="输出路径，默认 out/<name>-<asset>-installer.<ext>")
    ap.add_argument("--version", default="", help="不填就从源码读 VERSION")
    a = ap.parse_args()
    return build(a.src, a.asset, a.out or default_out(a.asset), a.version)


if __name__ == "__main__":
    sys.exit(main())
