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
# 默认测 src/pojia.py。补功能期间被测实现还在 rewrite/src/ 下，用 POJIA_CORE 指过去：
#   POJIA_CORE=rewrite/src/pojia.py py -3 -m pytest tests/contract -q --basetemp=/tmp/pt
CORE = os.path.abspath(os.environ.get("POJIA_CORE") or os.path.join(ROOT, "src", "pojia.py"))
if not os.path.isfile(CORE):
    raise SystemExit("POJIA_CORE 指向的文件不存在：%s" % CORE)

# 子进程只拿到这几项，其余一概不给。目的是切断任何"读到本机真实配置"的可能。
_PASS_ENV = ("PATH", "SystemRoot", "SystemDrive", "COMSPEC", "PATHEXT",
             "WINDIR", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE")


class Box(object):
    """一个完全隔离的沙箱：程序副本、假 HOME、假 AppData 全在里面。"""

    def __init__(self, root):
        self.root = str(root)
        self.prog_dir = os.path.join(self.root, "prog")
        os.makedirs(self.prog_dir)
        self.prog = os.path.join(self.prog_dir, "pojia.py")
        shutil.copy2(CORE, self.prog)
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
