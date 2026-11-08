#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打单文件可执行文件（可选先把核心编译成 C 扩展）。

为什么单独一个脚本，而不是在 workflow 里堆一条 pyinstaller 命令：

  · `--add-data` 的分隔符 Windows 是 `;`、POSIX 是 `:`。写在 YAML 里要么分平台
    写两遍，要么被 Git Bash 的路径转换吃掉。这里用 `os.pathsep`，一份代码通吃。
  · 图形界面是当**数据文件**塞进包的（`pojia_gui.py`），核心用 runpy 在进程内跑它 ——
    打包时漏了这条 `--add-data`，产物就没有 GUI，而且只有在用户敲 `--gui` 时才发现。
  · Cython 那一步要先 cythonize、再 build_ext、再生成一个 ASCII 名字的入口模块
    （源文件名是中文，扩展模块名不能用中文）。编译失败不该让发布变红 —— 自动退回
    纯源码打包，产物照样能用，只是慢一点。

关于 Cython：**这不是加壳。** 仓库里的源码一行没少，任何人 clone 下来就是可读的
Python；编译只是为了跑得快一截（省掉每次启动把 9929 行编译成字节码，热点循环也走
C 层）。真要藏代码应该上混淆器，本项目不干那事。

用法：
    python tools/build_exe.py --name pojia-modifier
    python tools/build_exe.py --name pojia-modifier --no-cython      # 强制纯 Python 打包
    python tools/build_exe.py --name pojia-modifier --keep-cython-src # 留着中间 .py/.c 排查
"""

import argparse
import ast
import glob
import importlib.util
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
CORE = os.path.join(SRC, "pojia.py")
GUI = os.path.join(SRC, "pojia_gui.py")

SETUP_TMPL = '''\
from setuptools import Extension, setup
from Cython.Build import cythonize

ext = Extension(
    "%(mod)s", ["%(mod)s.py"],
    extra_compile_args=%(cflags)s,
    extra_link_args=%(ldflags)s,
)

setup(
    name="%(mod)s",
    ext_modules=cythonize(
        [ext],
        language_level=3,
        # binding=True：编译出来的 cyfunction 保留 __name__ / __doc__ / 关键字参数，
        # 核心里有 fn.__name__ 这种用法（按函数名报「打了哪几处」），不保留就 AttributeError。
        compiler_directives={"binding": True, "language_level": 3},
        quiet=True,
    ),
    script_args=["build_ext", "--inplace"],
)
'''

ENTRY_TMPL = '''\
# 由 tools/build_exe.py 生成：把编译好的核心模块当程序入口。
# 不能直接把 pojia_core.py 当入口 —— 那样 PyInstaller 会把源码打进包，编译白做。
import sys

from %(mod)s import main

if __name__ == "__main__":
    sys.exit(main())
'''


def log(msg):
    print("[build] " + msg, flush=True)


def scan_imports(path):
    """把源码里 import 到的模块名全揪出来（含函数内的延迟导入）。

    **编译版必须这么做**：PyInstaller 是靠读字节码找依赖的，而 `.pyd` 里只剩 C，
    它一个 import 都看不见 —— 于是打出来的包跑两步就 `No module named 'shlex'`。
    图形界面更隐蔽：它是 runpy 从数据文件里跑起来的，静态分析同样看不见
    `http.server` / `secrets` 这些，只有敲 `--gui` 那一刻才会炸。
    """
    try:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError) as e:
        log("扫 import 失败（%s）：%s" % (os.path.basename(path), e))
        return []
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
    out = []
    for m in names:
        for cand in (m, m.split(".")[0]):
            if cand not in out:
                out.append(cand)
    return out


def importable(mod):
    """当前平台上真的能 import 才算 —— winreg / msvcrt 在 Linux 上不存在，
    塞给 --hidden-import 只会换来一堆 WARNING。"""
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, AttributeError, ValueError, ModuleNotFoundError):
        return False


def hidden_imports(*sources):
    seen = []
    for src in sources:
        for m in scan_imports(src):
            if m in seen or m in ("__future__",):
                continue
            if importable(m):
                seen.append(m)
    return seen


def build_version(src):
    """从核心脚本里读对外版本号。

    优先 DISPLAY_VERSION（带 `-mod` 这类后缀，界面横幅与 `--version` 用它），
    没有再退回 VERSION。护照里存的仍是纯数字那一份，两者用途不同。
    """
    try:
        with open(src, "r", encoding="utf-8", errors="ignore") as f:
            txt = f.read()
    except OSError:
        return ""
    m = (re.search(r'^DISPLAY_VERSION\s*=\s*"([^"]+)"', txt, re.M)
         or re.search(r'^VERSION\s*=\s*"([^"]+)"', txt, re.M))
    return m.group(1) if m else ""


def write_version_file(src, dest):
    """把版本号摊成 `_version.txt` 一起打进包，返回路径；写不出来返回空串。

    图形界面冻结态读不到 .py 源码，早先靠起一个 `exe --version` 子进程问自己。
    那条路会卡死：子进程继承了终端 stdin，退出前的留屏逻辑在等一个没人按的
    回车，父进程干等，界面停在横幅第一行。版本号打包时就确定了，没必要问。
    """
    ver = build_version(src)
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="\n") as f:
            f.write((ver or "?") + "\n")
    except OSError as e:
        log("写版本号文件失败（界面版本会显示 ?）：%s" % e)
        return ""
    return dest


def runtime_tmpdir_for(args, nt=None):
    """单文件版的解包目录。空字符串表示不加这个参数。

    默认落点由 bootloader 自己挑，通常是 %TEMP%。有些机器上那个位置建不出
    目录 —— TEMP 被指到不可写卷、或安全软件不放行在 Temp 下创建可执行目录 ——
    进程会在 Python 起来之前直接退出，只留一行
    "Could not create temporary directory"，重下重启都没用。换到用户自己的
    LocalAppData 下，bootloader 会把整条多级路径自己补出来（实测父目录不存在
    也能建）。目录形态不解包，这项对它没有意义。
    """
    if args.onedir:
        return ""
    if args.runtime_tmpdir:
        return args.runtime_tmpdir
    if (os.name == "nt") if nt is None else nt:
        return os.path.join("%LOCALAPPDATA%", "pojia-modifier", "rt")
    return ""


def cython_available():
    try:
        import Cython  # noqa: F401
        return True
    except Exception:
        return False


def compile_core(workdir, mod="pojia_core"):
    """把核心编译成扩展模块，返回模块名；失败抛异常由上层兜。"""
    os.makedirs(workdir, exist_ok=True)
    py = os.path.join(workdir, mod + ".py")
    shutil.copyfile(CORE, py)

    setup_py = os.path.join(workdir, "setup_%s.py" % mod)
    # 编译选项按平台给：gcc / clang 默认带 -g，编出来的 .so 里塞满调试信息 ——
    # Linux 产物因此从 21 MB 涨到 33 MB（同一份代码，Windows 只涨 1 MB）。
    # -g0 不生成调试信息，-s 链接时顺手 strip。MSVC 不认这两个开关，Windows 不给。
    if os.name == "nt":
        cflags, ldflags = "[]", "[]"
    else:
        cflags, ldflags = '["-g0", "-O2"]', '["-s"]'
    with open(setup_py, "w", encoding="utf-8") as f:
        f.write(SETUP_TMPL % {"mod": mod, "cflags": cflags, "ldflags": ldflags})

    log("cythonize + build_ext（%s）" % mod)
    r = subprocess.run([sys.executable, setup_py, "build_ext", "--inplace"],
                       cwd=workdir, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("编译失败：\n%s\n%s"
                           % ((r.stdout or "")[-3000:], (r.stderr or "")[-3000:]))

    built = glob.glob(os.path.join(workdir, mod + "*.pyd")) + \
            glob.glob(os.path.join(workdir, mod + "*.so"))
    if not built:
        raise RuntimeError("编译命令成功，但没找到 %s.pyd / %s.so" % (mod, mod))

    entry = os.path.join(workdir, "_pojia_entry.py")
    with open(entry, "w", encoding="utf-8") as f:
        f.write(ENTRY_TMPL % {"mod": mod})
    return mod, entry


def main():
    ap = argparse.ArgumentParser(description="打单文件可执行文件")
    ap.add_argument("--name", default="pojia-modifier", help="产物名（不含扩展名）")
    ap.add_argument("--dist", default=os.path.join("build", "dist"))
    ap.add_argument("--work", default=os.path.join("build", "work"))
    ap.add_argument("--spec", default="build")
    ap.add_argument("--no-cython", action="store_true", help="跳过 Cython，纯源码打包")
    ap.add_argument("--keep-cython-src", action="store_true",
                    help="保留中间产物（.py / .c），排查编译问题时用")
    ap.add_argument("--onedir", action="store_true",
                    help="打成目录而不是单文件：启动时不解包，不碰临时目录")
    ap.add_argument("--runtime-tmpdir", default=None, metavar="PATH",
                    help="单文件版的解包目录。留空时 Windows 用 "
                         "%%LOCALAPPDATA%%\\pojia-modifier\\rt；onedir 形态忽略此项")
    args = ap.parse_args()

    for p in (CORE, GUI):
        if not os.path.isfile(p):
            log("找不到源文件：%s" % p)
            return 2

    dist = os.path.join(ROOT, args.dist)
    work = os.path.join(ROOT, args.work)
    spec = os.path.join(ROOT, args.spec)
    cywork = os.path.join(work, "cython")

    use_cython = not args.no_cython
    entry = CORE
    paths = []
    mod = ""

    if use_cython and not cython_available():
        log("没装 Cython，退回纯源码打包（产物一样能用，只是启动慢一点）")
        use_cython = False

    if use_cython:
        try:
            mod, entry = compile_core(cywork)
            paths = [cywork]
            if not args.keep_cython_src:
                # 只留 .pyd/.so：留着 .py，PyInstaller 有可能把源码也打进包，
                # 那这次编译就白做了（而且包还变大）。
                for junk in glob.glob(os.path.join(cywork, "pojia_core.py")) + \
                            glob.glob(os.path.join(cywork, "pojia_core.c")):
                    try:
                        os.remove(junk)
                    except OSError:
                        pass
            log("核心已编译成扩展模块（%s）" % mod)
        except Exception as e:                      # 编译环境千奇百怪，别让发布变红
            log("Cython 编译失败，退回纯源码打包：")
            log(str(e).strip().splitlines()[-1] if str(e).strip() else "未知错误")
            use_cython = False
            entry = CORE
            paths = []

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean", "--noconfirm",
        "--onedir" if args.onedir else "--onefile",
        "--name", args.name,
        "--distpath", dist,
        "--workpath", work,
        "--specpath", spec,
        # GUI 是数据文件：核心用 runpy 在进程内跑它。漏了这条，产物就没有 --gui。
        "--add-data", GUI + os.pathsep + ".",
    ]
    # 版本号也是一份数据文件，和 GUI 放同一层（解包后是 _MEIPASS/_version.txt）。
    vfile = write_version_file(CORE, os.path.join(spec, "_version.txt"))
    if vfile:
        cmd += ["--add-data", vfile + os.pathsep + "."]
    # Everything 的 SDK 库。只有 Windows 用得上，别的平台打进去也是一堆死文件。
    vendor = os.path.join(ROOT, "vendor", "everything")
    if sys.platform == "win32" and os.path.isdir(vendor):
        cmd += ["--add-data", vendor + os.pathsep + os.path.join("vendor", "everything")]
        log("附带 Everything SDK：%s" % vendor)
    for p in paths:
        cmd += ["--paths", p]
    if mod:
        cmd += ["--hidden-import", mod]
    # 图形界面是 runpy 从数据文件里跑的，它的 import 静态分析看不见；核心编译成
    # 扩展模块之后，核心自己的 import 也看不见。两边都得手动声明。
    hid = hidden_imports(CORE, GUI)
    log("补 %d 个 hidden-import：%s" % (len(hid), " ".join(hid)))
    for m in hid:
        cmd += ["--hidden-import", m]
    # 单文件版的解包目录见 runtime_tmpdir_for：默认不再用 %TEMP%。
    rt = runtime_tmpdir_for(args)
    if rt and args.onedir:
        log("--onedir 不需要解包目录，--runtime-tmpdir 已忽略")
    elif rt:
        log("解包目录：%s" % rt)
        cmd += ["--runtime-tmpdir", rt]
    cmd.append(entry)

    log("PyInstaller（%s）" % ("Cython 编译版" if use_cython else "纯源码"))
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        log("PyInstaller 失败，退出码 %d" % r.returncode)
        return r.returncode

    if args.onedir:
        # 目录形态：exe 旁边就是 _internal/，启动时直接加载，不解包也不写临时目录。
        out_dir = os.path.join(dist, args.name)
        exe = os.path.join(out_dir, args.name + (".exe" if os.name == "nt" else ""))
        if not os.path.isfile(exe):
            log("没找到产物：%s" % exe)
            return 1
        total = sum(os.path.getsize(os.path.join(d, f))
                    for d, _, fs in os.walk(out_dir) for f in fs)
        log("OK  %s/  %.1f MB（目录）cython=%s" % (out_dir, total / 1048576.0,
                                                   "yes" if use_cython else "no"))
        return 0

    out = os.path.join(dist, args.name + (".exe" if os.name == "nt" else ""))
    if not os.path.isfile(out):
        log("没找到产物：%s" % out)
        return 1
    log("OK  %s  %.1f MB  cython=%s" % (out, os.path.getsize(out) / 1048576.0,
                                        "yes" if use_cython else "no"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
