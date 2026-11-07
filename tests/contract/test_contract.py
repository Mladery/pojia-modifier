# -*- coding: utf-8 -*-
"""黑盒契约测试。

每一条对应 `docs/spec/00-overview.md` 里的一条不变量，或者 `REPLACE.md` 第 3 节的
一条出口契约。全部通过子进程 + 命令行参数完成，**不 import 被测模块**——所以实现
整体重写、改名、拆文件都不影响这一层。

编号与 `REPLACE.md` 第 5 节一一对应。
"""
import os
import sys

import pytest


CLAUDE_SAMPLE = b"# my own rules\r\n\r\n- read the code before changing it\r\n"


def _claude(box, name="claude"):
    """造一个带 CLAUDE.md 的假 Claude 配置目录。"""
    d = box.target(name)
    open(os.path.join(d, "CLAUDE.md"), "wb").write(CLAUDE_SAMPLE)
    return d, os.path.join(d, "CLAUDE.md")


# ---------------------------------------------------------------- C1 版本号

def test_c1_version_exits_zero(box):
    r = box.run("--version")
    assert r.returncode == 0, box.out(r)
    text = box.out(r)
    assert "Traceback" not in text
    # 至少有一个数字版本号，且不带旧的 v8/v7 系列标记
    assert any(ch.isdigit() for ch in text), text
    for stale in ("v8.", "v7.", "v6."):
        assert stale not in text, "版本号里还残留 %s：%s" % (stale, text)


# ------------------------------------------------------------ C2 命令行出口

REQUIRED_SWITCHES = [
    "--target", "--apply", "--revert", "--status", "--check", "--dry-run",
    "--force", "--yes", "--quiet", "--menu", "--gui", "--version",
    "--persona", "--persona-name", "--persona-list", "--persona-set",
    "--persona-show", "--pick", "--clear", "--deep", "--dsh-mode",
    "--zpatch", "--mac-check", "--uninstall", "--purge",
]


def test_c2_help_lists_every_switch(box):
    r = box.run("--help")
    assert r.returncode == 0, box.out(r)
    text = box.out(r)
    missing = [s for s in REQUIRED_SWITCHES if s not in text]
    assert not missing, "--help 里缺这些开关：%s" % missing


def test_c2_help_lists_every_target_dir_flag(box):
    """17 个目标各自的手动指定开关。名字不统一是历史原因，这里逐条钉死。"""
    flags = [
        "--dsh-dir",                                        # dsh
        "--wb-install", "--wb-data",                        # wb
        "--wbintl-install", "--wbintl-data",                # wbintl
        "--zcode-dir", "--zcode-cjs",                       # zcode
        "--codex-dir", "--cursor-dir", "--claude-dir",
        "--gemini-dir",                                     # antigravity（名字是 gemini）
        "--qwen-dir", "--iflow-dir", "--trae-dir",
        "--codebuddy-dir", "--opencode-dir", "--windsurf-dir",
        "--cline-dir", "--copilot-dir", "--kiro-dir",
    ]
    r = box.run("--help")
    text = box.out(r)
    missing = [f for f in flags if f not in text]
    assert not missing, "缺这些目标的目录参数：%s" % missing


# --------------------------------------------------------- C3 只读不落盘

@pytest.mark.parametrize("argv", [
    ("--status",),
    ("--check",),
    ("--persona-show",),
    ("--persona-list",),
])
def test_c3_readonly_actions_write_nothing(box, argv):
    d, path = _claude(box)
    before = box.tree()
    r = box.run(*argv)
    after = box.tree()
    assert r.returncode in (0, 1), box.out(r)
    assert after == before, (
        "只读动作改了盘：\n新增 %s\n消失 %s\n变化 %s"
        % (sorted(set(after) - set(before)),
           sorted(set(before) - set(after)),
           sorted(k for k in set(before) & set(after) if before[k] != after[k]))
    )
    # 目标文件也没被动过
    assert open(path, "rb").read() == CLAUDE_SAMPLE


# ------------------------------------------------------------ C4 预演不落盘

def test_c4_dry_run_does_not_touch_target(box):
    d, path = _claude(box)
    before = box.tree(d)
    r = box.run("--target", "claude", "--claude-dir", d, "--apply", "--dry-run", "--yes")
    assert r.returncode == 0, box.out(r)
    assert box.tree(d) == before, "预演改了目标目录：%s" % sorted(box.tree(d))
    assert open(path, "rb").read() == CLAUDE_SAMPLE


# ---------------------------------------------------------------- C5 幂等

def test_c5_apply_twice_is_byte_identical(box):
    d, path = _claude(box)
    r1 = box.run("--target", "claude", "--claude-dir", d, "--apply", "--yes")
    assert r1.returncode == 0, box.out(r1)
    once = open(path, "rb").read()
    r2 = box.run("--target", "claude", "--claude-dir", d, "--apply", "--yes")
    assert r2.returncode == 0, box.out(r2)
    twice = open(path, "rb").read()
    assert once == twice, "二次 apply 不是幂等的（%d → %d 字节）" % (len(once), len(twice))
    assert once.count(b"<!-- POJIA-NEXT-INJECT:BEGIN -->") == 1, "主块被重复叠加"


# ---------------------------------------------------------------- C6 可逆

@pytest.mark.parametrize("blob,name", [
    (CLAUDE_SAMPLE, "CRLF"),
    (b"# lf rules\n\n- a\n", "LF"),
    (b"# no trailing newline", "无末尾换行"),
    (b"\xef\xbb\xbf# bom rules\r\n\r\n- x\r\n", "BOM+CRLF"),
    ("\ufeff# \u4e2d\u6587\u89c4\u5219\r\n\r\n- \u4fdd\u7559\r\n".encode("utf-8"), "中文+BOM"),
])
def test_c6_apply_then_revert_is_byte_exact(box, blob, name):
    d = box.target("c6")
    path = os.path.join(d, "CLAUDE.md")
    open(path, "wb").write(blob)

    r1 = box.run("--target", "claude", "--claude-dir", d, "--apply", "--yes")
    assert r1.returncode == 0, box.out(r1)
    patched = open(path, "rb").read()
    assert len(patched) > len(blob), "apply 好像没写进去"

    r2 = box.run("--target", "claude", "--claude-dir", d, "--revert", "--yes")
    assert r2.returncode == 0, box.out(r2)
    back = open(path, "rb").read()
    assert back == blob, "%s：还原没回到原文\n原文 %r\n还原 %r" % (name, blob, back)


# ---------------------------------------------------------------- C7 行尾

def test_c7_apply_does_not_mix_line_endings(box):
    d, path = _claude(box)
    r = box.run("--target", "claude", "--claude-dir", d, "--apply", "--yes")
    assert r.returncode == 0, box.out(r)
    blob = open(path, "rb").read()
    lone_lf = blob.count(b"\n") - blob.count(b"\r\n")
    assert lone_lf == 0, "CRLF 文件里混进了 %d 个孤立 LF" % lone_lf


# ---------------------------------------------------------------- C8 BOM

def test_c8_bom_survives_apply_and_revert(box):
    d = box.target("c8")
    path = os.path.join(d, "CLAUDE.md")
    open(path, "wb").write(b"\xef\xbb\xbf" + CLAUDE_SAMPLE)
    box.run("--target", "claude", "--claude-dir", d, "--apply", "--yes")
    after = open(path, "rb").read()
    assert after.count(b"\xef\xbb\xbf") == 1, "BOM 被吃掉或重复了"
    box.run("--target", "claude", "--claude-dir", d, "--revert", "--yes")
    assert open(path, "rb").read().startswith(b"\xef\xbb\xbf"), "还原后 BOM 丢了"


# --------------------------------------------------- C9 单点失败不扩散

def test_c9_bad_target_fails_loudly_without_truncating(box):
    d = box.target("c9")
    # 把落点做成目录：程序应该判定"读不了"并跳过，绝不截断
    os.makedirs(os.path.join(d, "CLAUDE.md"))
    r = box.run("--target", "claude", "--claude-dir", d, "--apply", "--yes")
    assert r.returncode == 1, "坏目标应当退出 1，实际 %d：%s" % (r.returncode, box.out(r))
    assert os.path.isdir(os.path.join(d, "CLAUDE.md")), "目录被当成文件覆盖了"
    assert "Traceback" not in box.out(r), "坏目标不该抛异常栈"


def test_c9_one_bad_target_does_not_block_the_others(box):
    bad = box.target("c9bad")
    os.makedirs(os.path.join(bad, "CLAUDE.md"))
    good = box.target("c9good")
    gpath = os.path.join(good, "CLAUDE.md")
    open(gpath, "wb").write(CLAUDE_SAMPLE)

    r = box.run("--target", "claude,codex",
                "--claude-dir", bad,
                "--codex-dir", good,
                "--apply", "--yes")
    assert r.returncode == 1, "有一个失败时退出码应为 1：%s" % box.out(r)
    # codex 的落点是 config.toml；只要它被写了，就说明没被 claude 的失败拖住
    assert os.path.exists(os.path.join(good, "config.toml")), \
        "前一个目标失败后，后一个目标被跳过了"


# ---------------------------------------------------------------- C10 不越界

def test_c10_apply_writes_only_inside_target_dir(box):
    d, _path = _claude(box)
    before = box.tree(box.home)
    r = box.run("--target", "claude", "--claude-dir", d, "--apply", "--yes")
    assert r.returncode == 0, box.out(r)
    after = box.tree(box.home)
    added = sorted(set(after) - set(before))
    assert not added, "注入跑到用户主目录去了：%s" % added


# ---------------------------------------------- 出口契约：磁盘固定字符串

def test_disk_markers_are_stable(box):
    d, path = _claude(box)
    box.run("--target", "claude", "--claude-dir", d, "--apply", "--yes")
    blob = open(path, "rb").read()
    for mark in (b"<!-- POJIA-NEXT-INJECT:BEGIN -->",
                 b"<!-- POJIA-NEXT-INJECT:END -->"):
        assert mark in blob, "磁盘标记变了：%r 不在文件里" % mark


# ------------------------------------------------- 已知偏差（新实现应修）

@pytest.mark.xfail(strict=True, reason=(
    "已知残留：--revert 之后会留下 *.pojia.bak（备份，设计如此）、"
    "settings.json（Claude 的空壳 {}）与 output-styles/（空目录）。"
    "备份是有意的，后两条是残留。新实现应当清掉后两条——清了之后本测试会 xpass，"
    "把 xfail 标记删掉即可。"))
def test_revert_leaves_no_residue(box):
    d = box.target("resid")
    open(os.path.join(d, "CLAUDE.md"), "wb").write(CLAUDE_SAMPLE)
    box.run("--target", "claude", "--claude-dir", d, "--apply", "--yes")
    box.run("--target", "claude", "--claude-dir", d, "--revert", "--yes")
    left = sorted(n for n in os.listdir(d) if not n.endswith(".pojia.bak"))
    assert left == ["CLAUDE.md"], "还原后还剩：%s" % left
