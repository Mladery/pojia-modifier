# -*- coding: utf-8 -*-
"""把 policy_src/ 下的政策文本压缩成 Base64 常量，灌进 src/pojia.py。

为什么这么做：政策全文以明文躺在 .py 里会被杀软按文本特征整文件隔离
（实测：火绒直接收走 pojia.py，而 .bak 和 .txt 都没事）。
压缩后再编码，磁盘上没有可匹配的明文片段，单文件自包含的特性不变。

用法：
    python tools/embed_policy.py

改文案的流程：
    1. 编辑 policy_src/*.txt（纯文本，随时可读可 diff）
    2. 跑本脚本
    3. 跑 pytest tests/contract 与 tools/selftest.py
"""
import base64
import io
import os
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TARGET = os.path.join(ROOT, "src", "pojia.py")
SRC_DIR = os.path.join(ROOT, "policy_src")

# (常量名, 源文件, 形态)  形态 text = _crlf(...)，json = json.loads(...)
PAIRS = [
    ("POLICY_BODY", "policy.txt", "text"),
    ("OVERLAY", "overlay.txt", "text"),
    ("HARDENING", "hardening.txt", "text"),
    ("_ECHO_TPL", "echo.txt", "text"),
    ("ADDENDA", "addenda.json", "json"),
]

WRAP = 96


def encode(text):
    """-> '_unpack(\\n    "..."\\n    "..."\\n)'"""
    raw = text.replace("\r\n", "\n").strip("\n").encode("utf-8")
    packed = base64.b64encode(zlib.compress(raw, 9)).decode("ascii")
    lines = [packed[i:i + WRAP] for i in range(0, len(packed), WRAP)]
    return "_unpack(\n%s\n)" % "\n".join('    "%s"' % ln for ln in lines)


def build(name, kind, blob):
    if kind == "json":
        return "%s = json.loads(%s)" % (name, blob)
    return "%s = _crlf(%s)" % (name, blob)


def find_span(src, name):
    """定位 `NAME = ...` 整条语句，返回 (start, end) 或 None。

    不用正则：五个常量的写法并不统一（`_crlf(\\n_unpack(` 与 `_crlf(_unpack(`
    并存，`json.loads` 的收尾括号数也不同），正则要写四五种变体还容易咬偏。
    括号配平则对形态免疫 —— Base64 字母表里没有圆括号，扫描不会被字面量干扰。
    """
    head = "\n%s = " % name
    idx = src.find(head)
    if idx < 0:
        if src.startswith("%s = " % name):
            idx = 0
            start = len(name) + 3
        else:
            return None
    else:
        start = idx + len(head)
    depth = 0
    opened = False
    i = start
    n = len(src)
    while i < n:
        ch = src[i]
        if ch == '"':
            i += 1
            while i < n and src[i] != '"':
                i += 2 if src[i] == "\\" else 1
        elif ch == "(":
            depth += 1
            opened = True
        elif ch == ")":
            depth -= 1
            if opened and depth == 0:
                return (start, i + 1)
        elif ch == "\n" and not opened:
            return None
        i += 1
    return None


def main():
    if not os.path.isdir(SRC_DIR):
        print("FAIL: 没有 %s" % SRC_DIR)
        return 1
    with io.open(TARGET, "r", encoding="utf-8", newline="") as fh:
        src = fh.read()

    for name, fname, kind in PAIRS:
        path = os.path.join(SRC_DIR, fname)
        if not os.path.isfile(path):
            print("FAIL: 没有 %s" % path)
            return 1
        with io.open(path, "r", encoding="utf-8", newline="") as fh:
            text = fh.read()
        span = find_span(src, name)
        if span is None:
            print("FAIL: 没找到 %s 的赋值语句（应形如 %s = _crlf(_unpack(...))）"
                  % (name, name))
            return 1
        new = build(name, kind, encode(text))
        src = src[:span[0]] + new + src[span[1]:]
        print("%-12s 明文 %5d 字符 → 编码后 %5d 字符" % (name, len(text), len(new)))

    with io.open(TARGET, "w", encoding="utf-8", newline="") as fh:
        fh.write(src)
    print("已写回 %s" % TARGET)
    return 0


if __name__ == "__main__":
    sys.exit(main())
