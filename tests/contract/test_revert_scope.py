# -*- coding: utf-8 -*-
"""--revert 的撤回范围：只撤我们写的，不回滚别人后来写进去的东西。

背景：`revert_one` 原来的顺序是"干净备份 → 保险库 → 按标记裁剪"。对**纯插入**
型注入（`cblock` 注释块、`jslit` 的注释块分支）这套顺序是错的：快照会把拍快照
那一刻的整份文件搬回来，于是快照之后第三方写进同一文件的内容一起没。

真实案例：DSH 的 `profiles/desktop/cordis.patch.yml` 被用户自己的 preset 安装器
（麦麦模式）往里插了一段；一次 `--revert` 会拿几天前的 827 字节快照整个覆盖，
那段跟着消失。而这个文件本来就不是"我们独占"的，它是一层公开的 patch 层。

判据：块在就按标记裁剪（只回滚自己的行），块不在就当没撤的、直接返回。
"我们换掉了内容"的形态（整文件、字段注入、JS 字面量替换）仍然只能靠快照。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pojia  # noqa: E402


class _Fake(pojia.Target):
    key = "fake"
    name = "Fake"
    bak_suffix = ".pojia.bak"

    def vault_root(self):
        return ""


def _block(payload="policy", style="yaml"):
    return pojia.cblock_put("", payload, style)


def _ours(tmp_path, extra=""):
    """一份"我们注入过、之后又有别人往里写"的文件。"""
    before = "- id: mine\n  name: x\n"
    after = _block("body", "yaml") + "\n" + extra
    path = tmp_path / "cordis.patch.yml"
    path.write_text(before + after, encoding="utf-8")
    # 拍快照那一刻的内容（注入之前）
    (tmp_path / "cordis.patch.yml.pojia.bak").write_text(before, encoding="utf-8")
    return str(path), before, extra


@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setitem(pojia.OPT, "dry", False)
    return pojia.OPT


def test_revert_keeps_foreign_block(tmp_path, fresh):
    """有干净备份也不能拿它覆盖：别人后写的块必须留下。"""
    path, before, _ = _ours(
        tmp_path, "- insert:\n    - id: preset-maimai\n      name: '@deepseek-ai/dsh-agent-preset'\n")
    ok = pojia.revert_one(_Fake(), path, "cblock:yaml", False)
    assert ok
    text = open(path, encoding="utf-8").read()
    assert "POJIA-NEXT-INJECT" not in text, "我们那块要剪干净"
    assert "preset-maimai" in text, "别人写的那段不能跟着没"
    assert "- id: mine" in text


def test_revert_without_block_is_noop(tmp_path, fresh):
    """块已经不在了（宿主换过文件 / 上次撤过）：不许拿快照把文件搬回去。"""
    path = tmp_path / "cordis.patch.yml"
    current = "- id: host-new\n  name: y\n- insert:\n    - id: preset-maimai\n"
    path.write_text(current, encoding="utf-8")
    (tmp_path / "cordis.patch.yml.pojia.bak").write_text("- id: ancient\n", encoding="utf-8")
    assert pojia.revert_one(_Fake(), str(path), "cblock:yaml", False)
    assert open(path, encoding="utf-8").read() == current


def test_revert_block_only_file_removes_it(tmp_path, fresh):
    """我们自己建的文件：剪完为空就删掉，不留一个空壳。"""
    path = tmp_path / "pojia-inject.md"
    path.write_text(_block("body", "yaml"), encoding="utf-8")
    assert pojia.revert_one(_Fake(), str(path), "cblock:yaml", True)
    assert not os.path.exists(path)


def test_jslit_literal_still_flies_back_to_backup(tmp_path, fresh):
    """JS 字面量替换没有块可剪，必须照旧走备份还原。"""
    path = tmp_path / "lib.js"
    path.write_text("const A = 1;\nconst INSTR = \"pojia 注入过的人设\";\nconst B = 2;\n",
                    encoding="utf-8")
    orig = "const A = 1;\nconst INSTR = \"原始人设\";\nconst B = 2;\n"
    (tmp_path / "lib.js.pojia.bak").write_text(orig, encoding="utf-8")
    assert pojia.revert_one(_Fake(), str(path), "jslit", False)
    assert open(path, encoding="utf-8").read() == orig


def test_jslit_comment_block_strips_only_block(tmp_path, fresh):
    """jslit 的另一种形态（没有字面量可换，改成插注释块）走裁剪。"""
    path = tmp_path / "lib.js"
    path.write_text("const A = 1;\n" + _block("body", "js") + "const B = 2;\n", encoding="utf-8")
    (tmp_path / "lib.js.pojia.bak").write_text("OLD-AND-STALE\n", encoding="utf-8")
    assert pojia.revert_one(_Fake(), str(path), "jslit", False)
    text = open(path, encoding="utf-8").read()
    assert "POJIA-NEXT-INJECT" not in text
    assert "const A = 1;" in text and "const B = 2;" in text
    assert "OLD-AND-STALE" not in text


@pytest.mark.parametrize("original,label", [
    ("name: base\n", "结尾带换行"),
    ("name: base", "结尾不带换行"),
    ("", "原本是空文件"),
])
def test_revert_is_byte_exact(tmp_path, fresh, original, label):
    """注入前的行尾形状（有没有收尾换行）必须原样还回去，不能被分隔空行带偏。"""
    path = tmp_path / "cordis.patch.yml"
    path.write_text(original, encoding="utf-8")
    (tmp_path / "cordis.patch.yml.pojia.bak").write_text(original, encoding="utf-8")
    injected = pojia.cblock_put(original, "body", "yaml")
    path.write_text(injected, encoding="utf-8")
    assert pojia.revert_one(_Fake(), str(path), "cblock:yaml", False), label
    assert open(path, encoding="utf-8").read() == original, label
