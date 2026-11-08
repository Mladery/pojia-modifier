# -*- coding: utf-8 -*-
"""云记忆档案里的两份正文必须一起改。

档案长这样：

    # User Memory Profile
    > Version: 999999

    ## Memory Block
    <!-- POJIA-NEXT-INJECT:MEM -->
    ……政策全文……

    ---

    <!-- RAW_JSON_START
    {"uid": "...", "memoryBlock": "……同一份正文……", "version": 999999}
    RAW_JSON_END -->

段里那份是给人看的副本，客户端每轮拼系统提示词读的是 JSON 里那份。只改副本
的话，磁盘上看着是新的，客户端照样拿旧的 —— 「破甲自检」回的仍是上一代口令，
2026-11-08 的 v1.02-mod 就是为这个发的。
"""
import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORE = os.path.join(ROOT, "src", "pojia.py")

OLD = "<!-- pojia-yijiantong cloudmem v8.65 -->\n旧政策：破甲自检成功 | 社区版v8.65 | pojia-ce"
NEW = "# 新政策\n\n破甲已生效｜版本1.02-mod｜仓库地址：https://github.com/Mladery/pojia-modifier"

ARCHIVE = """# User Memory Profile
> Last updated: 2026-11-07T18:35:03
> Version: 999999

## Memory Block

%s

---

<!-- RAW_JSON_START
{
  "uid": "u-1",
  "memoryBlock": %s,
  "updatedAt": "2026-11-07T18:35:03",
  "version": 999999
}
RAW_JSON_END -->
""" % (OLD, json.dumps(OLD, ensure_ascii=False))

SNIPPET = r'''
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[1])))
import pojia
text = open(sys.argv[2], encoding="utf-8", newline="").read()
out = pojia.mem_write(text, sys.argv[3], pojia.MEM_VERSION)
open(sys.argv[2], "w", encoding="utf-8", newline="").write(out)
print("OK", len(text), len(out))
'''


def _write(tmp_path, text):
    p = tmp_path / "_memory.md"
    p.write_text(text, encoding="utf-8", newline="")
    return str(p)


def _mem_write(tmp_path, text, content):
    p = _write(tmp_path, text)
    r = subprocess.run([sys.executable, "-c", SNIPPET, CORE, p, content],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    assert "OK" in (r.stdout or b"").decode("utf-8", "replace"), \
        (r.stdout, r.stderr)
    with open(p, encoding="utf-8", newline="") as fh:
        return fh.read()


def _raw(out):
    m = re.search(r"<!-- RAW_JSON_START\n(.*?)\nRAW_JSON_END -->", out, re.S)
    assert m, "写完之后 JSON 段没了：%s" % out[-300:]
    return json.loads(m.group(1))


def test_raw_json_memory_block_follows_the_written_text(tmp_path):
    """核心断言：JSON 里那份也要换成新正文，否则客户端读到的还是旧的。"""
    out = _mem_write(tmp_path, ARCHIVE, NEW)
    data = _raw(out)
    assert "pojia-ce" not in out, "旧口令还留在档案里"
    assert "pojia-ce" not in data["memoryBlock"]
    assert "1.02-mod" in data["memoryBlock"]


def test_both_copies_are_identical(tmp_path):
    """段里那份与 JSON 里那份逐字相同 —— 不一致时客户端以 JSON 为准。"""
    out = _mem_write(tmp_path, ARCHIVE, NEW)
    data = _raw(out)
    seg = re.search(r"## Memory Block\n(.*?)\n---", out, re.S)
    assert seg, out[:400]
    assert seg.group(1).strip() == data["memoryBlock"].strip()


def test_other_fields_survive(tmp_path):
    """uid / updatedAt / version 不许被顺手改掉。"""
    out = _mem_write(tmp_path, ARCHIVE, NEW)
    data = _raw(out)
    assert data["uid"] == "u-1"
    assert data["updatedAt"] == "2026-11-07T18:35:03"
    assert data["version"] == 999999


def test_archive_without_raw_json_still_writes(tmp_path):
    """早期档案没有 JSON 段，写入不能因此坏掉。"""
    plain = "# User Memory Profile\n> Version: 999999\n\n## Memory Block\n\n旧内容\n"
    out = _mem_write(tmp_path, plain, NEW)
    assert "1.02-mod" in out
    assert "## Memory Block" in out


def test_broken_raw_json_is_left_alone(tmp_path):
    """JSON 坏了就别动它 —— 宁可留着，也不能写出一份解析不了的档案。"""
    broken = ARCHIVE.replace('"uid": "u-1"', '"uid": u-1')
    out = _mem_write(tmp_path, broken, NEW)
    assert out.count("RAW_JSON_START") == 1
    assert '"uid": u-1' in out, "坏 JSON 被改写了"
