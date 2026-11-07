# -*- coding: utf-8 -*-
"""黑盒契约测试装置。

这里**不 import 被测模块**。所有断言都通过子进程 + 命令行参数完成，只看三样
东西：退出码、stdout/stderr、磁盘上文件的字节。

这样做的唯一理由：让实现可以整体重写。函数名、类结构、模块划分随便变，只要
命令行行为一致，这一层就还是绿的。
"""
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORE = os.path.join(ROOT, "src", "pojia.py")
GUI = os.path.join(ROOT, "src", "pojia_gui.py")

# 子进程只拿到这几项，其余一概不给。目的是切断任何"读到本机真实配置"的可能。
_PASS_ENV = ("PATH", "SystemRoot", "SystemDrive", "COMSPEC", "PATHEXT",
             "WINDIR", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE")


class Box(object):
    """一个完全隔离的沙箱：程序副本、假 HOME、假 AppData 全在里面。"""

    # 系统组件自己往沙箱里写的东西，不算「本工具改了盘」。
    # 实测：Windows 上 powershell.exe 一启动就建模块分析缓存（约 290 KB）。--status
    # 为了判断客户端是否在跑会读一次进程命令行，于是拉起 powershell —— 缓存是它的
    # 行为，不是本工具写的。它落在哪个前缀下取决于环境（沙箱里实测是直接落在根下的
    # Microsoft\Windows\PowerShell\），所以按路径片段匹配，不按前缀。
    # 断言仍然覆盖本工具写的每一个字节。
    _NOISE_MARKS = ("microsoft/windows/powershell/",)

    def __init__(self, root):
        self.root = str(root)
        self.prog_dir = os.path.join(self.root, "prog")
        os.makedirs(self.prog_dir)
        self.prog = os.path.join(self.prog_dir, "pojia.py")
        shutil.copy2(CORE, self.prog)
        # 界面是单独一个文件（打包时当数据文件塞进包里）。两个文件必须待在一起，
        # 否则零参数启动找不到界面 —— 沙箱要跟真实安装形态一致，所以一并拷。
        if os.path.isfile(GUI):
            shutil.copy2(GUI, os.path.join(self.prog_dir, "pojia_gui.py"))
        self.home = self._dir("home")
        self.appdata = self._dir("appdata")
        self.local = self._dir("local")
        self.temp = self._dir("temp")

    def _dir(self, name):
        p = os.path.join(self.root, name)
        os.makedirs(p, exist_ok=True)
        return p

    def env(self):
        e = {}
        for k in _PASS_ENV:
            if k in os.environ:
                e[k] = os.environ[k]
        e.update({
            "HOME": self.home,
            "USERPROFILE": self.home,
            "APPDATA": self.appdata,
            "LOCALAPPDATA": self.local,
            "TEMP": self.temp,
            "TMP": self.temp,
            "POJIA_NO_EVERYTHING": "1",
            "POJIA_NO_UPDATE_CHECK": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        return e

    def run(self, *argv, **kw):
        timeout = kw.pop("timeout", 300)
        return subprocess.run(
            [sys.executable, self.prog] + list(argv),
            cwd=self.root, env=self.env(),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout,
        )

    def out(self, proc):
        """stdout+stderr 合起来，按 UTF-8 尽力解码。控制台颜色码已由程序自己关掉。"""
        raw = (proc.stdout or b"") + (proc.stderr or b"")
        return raw.decode("utf-8", "replace")

    def target(self, name):
        p = os.path.join(self.root, name)
        os.makedirs(p, exist_ok=True)
        return p

    def _is_noise(self, rel):
        low = "/" + rel.replace("\\", "/").lower()
        return any(mark in low for mark in self._NOISE_MARKS)

    def tree(self, top=None):
        """文件指纹表：相对路径 -> (字节数, sha256)。目录不记，空目录是噪音。"""
        import hashlib
        top = top or self.root
        seen = {}
        for base, dirs, files in os.walk(top):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in files:
                p = os.path.join(base, f)
                rel = os.path.relpath(p, top)
                if self._is_noise(rel):
                    continue
                try:
                    with open(p, "rb") as fh:
                        blob = fh.read()
                except OSError:
                    seen[rel] = (-1, "")
                    continue
                seen[rel] = (len(blob), hashlib.sha256(blob).hexdigest())
        return seen


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def write_bytes(path, blob):
    with open(path, "wb") as f:
        f.write(blob)


def rw(path):
    """按 UTF-8 读，保留原始换行（不做换行翻译）。"""
    with open(path, "rb") as f:
        return f.read().decode("utf-8")
