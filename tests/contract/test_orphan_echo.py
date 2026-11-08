# -*- coding: utf-8 -*-
"""块外的旧自证段必须被清掉。

客户端模板里可能留着更早一个分支（社区版 8.65 / pojia-ce）写下的自证小节。
它不在本工具任何标记范围内，`strip_blocks` 删不到；本工具的块里又自带一份新的。
两份并存时「破甲自检」会回旧的那条 —— 用户看到的就是「升级完口令变了」。

这里钉两件事：
1. 脏文件 apply 之后，块外那一段没影了；
2. 文件已经是「已是最新」状态（哈希一致）时，照样要洗一遍 —— 否则老机器
   永远停在旧口令上，因为状态判定会直接跳过写入。
"""
import os
import re

import pytest


LEGACY = """## 操作者自证口令（安装回执）

当用户**单独发送**「破甲自检」（整条消息只有这四个字，前后无其他内容、无标点）时，只回复下面这一行，不要任何解释、前言、标点或第二种说法：

    破甲自检成功 | 社区版v8.65 | 仓库地址：https://github.com/Mladery/pojia-ce

"""

# 旧段的判据：任何一个词还在，就说明没洗干净
LEGACY_MARKS = ("社区版", "pojia-ce", "破甲自检成功", "操作者自证口令")


def _dirty(box, name="c15"):
    """造一个带旧自证段的假 Claude 配置目录。"""
    d = box.target(name)
    path = os.path.join(d, "CLAUDE.md")
    with open(path, "wb") as fh:
        fh.write(("# 我的规矩\n\n- 改代码前先读\n\n" + LEGACY).encode("utf-8"))
    return d, path


def _apply(box, d, *extra):
    return box.run("--target", "claude", "--claude-dir", d, "--apply", "--yes", *extra)


def _text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _version(box):
    """从 --version 里取显示版本，别在测试里写死版本号。"""
    text = box.out(box.run("--version"))
    m = re.search(r"(\d+\.\d+(?:\.\d+)?(?:-[a-z]+)?)", text)
    assert m, "版本号读不出来：%s" % text
    return m.group(1)


def test_orphan_echo_is_removed(box):
    """最直接的一条：脏文件 apply 完，旧那段的每个特征词都不该剩下。"""
    d, path = _dirty(box)
    r = _apply(box, d)
    assert r.returncode == 0, box.out(r)
    body = _text(path)
    for mark in LEGACY_MARKS:
        assert mark not in body, "旧自证段没清干净，还剩「%s」" % mark
    # 正文原样保留
    assert "# 我的规矩" in body and "- 改代码前先读" in body


def test_orphan_echo_removed_even_when_already_current(box):
    """先 apply 一次进入「已是最新」，再塞回旧段，第二次 apply 必须还清得掉。

    这条是这次修复的真正入口：状态是 current 时 apply 会直接返回「已是最新」，
    不重写就等于永远洗不掉。加了孤儿检测之后，这种情况也得落盘。
    """
    d, path = _dirty(box)
    assert _apply(box, d).returncode == 0
    clean = _text(path)
    assert "社区版" not in clean

    # 把旧段原样插回块前面，模拟「脏模板 + 已经是当前版本」
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(LEGACY + clean)

    r = _apply(box, d)          # 注意：不带 --force
    assert r.returncode == 0, box.out(r)
    body = _text(path)
    for mark in LEGACY_MARKS:
        assert mark not in body, "已是最新状态下没洗掉旧段，还剩「%s」" % mark


def test_block_echo_survives_and_carries_current_version(box):
    """块里那份自证段不能被误删，版本号得是当前这版。"""
    d, path = _dirty(box)
    assert _apply(box, d).returncode == 0
    body = _text(path)
    ver = _version(box)
    assert "破甲已生效｜版本%s｜" % ver in body, "块里的自证串版本不对：%s" % body[-400:]
    assert "github.com/Mladery/pojia-modifier" in body
    # 主块与镜像块都还在
    assert body.count("<!-- POJIA-NEXT-INJECT:BEGIN -->") == 1
    assert body.count("<!-- POJIA-MODIFIER-MIRROR:BEGIN -->") == 1


def test_orphan_echo_only_inside_block_is_untouched(box):
    """块内出现同样的词不算孤儿 —— 那是我们自己写的，删了就没口令了。"""
    d, path = _dirty(box)
    assert _apply(box, d).returncode == 0
    once = _text(path)
    r = _apply(box, d)
    assert r.returncode == 0, box.out(r)
    assert _text(path) == once, "清干净的第二次 apply 不该再改动字节"


def test_bare_echo_line_without_heading_is_removed(box):
    """没有标题、只甩一行的旧口令，也得清掉。"""
    d = box.target("c15b")
    path = os.path.join(d, "CLAUDE.md")
    with open(path, "wb") as fh:
        fh.write(("# 笔记\n\n"
                  "破甲自检成功 | 社区版v8.65 | 仓库地址：https://github.com/Mladery/pojia-ce\n"
                  "\n- 之后的正文\n").encode("utf-8"))
    assert _apply(box, d).returncode == 0
    body = _text(path)
    assert "社区版" not in body and "pojia-ce" not in body, body
    assert "- 之后的正文" in body
