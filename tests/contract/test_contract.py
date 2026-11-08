# -*- coding: utf-8 -*-
"""黑盒契约测试。

每一条对应 `docs/spec/00-overview.md` 里的一条不变量，或者 `docs/spec/50-cli.md` 里的
一条出口契约。全部通过子进程 + 命令行参数完成，**不 import 被测模块**——所以实现
整体重写、改名、拆文件都不影响这一层。

编号 C1… 与 `docs/spec/` 里的不变量编号对应。
"""
import json
import os
import re
import subprocess
import sys
import threading
import time

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
    "--zpatch", "--mac-check", "--uninstall", "--purge", "--settings",
]


def test_c2_help_lists_every_switch(box):
    r = box.run("--help")
    assert r.returncode == 0, box.out(r)
    text = box.out(r)
    missing = [s for s in REQUIRED_SWITCHES if s not in text]
    assert not missing, "--help 里缺这些开关：%s" % missing


URL_RE = re.compile(r"(http://127\.0\.0\.1:\d+/\?t=[A-Za-z0-9_\-]+)")


def test_c2_no_args_opens_the_gui(box):
    """零参数 = 双击，必须起图形界面并把地址打出来。

    这条钉的是「双击之后有界面」这一件事本身：进菜单、直接退出、或者根本没把界面
    文件带上，都算红。界面是独立文件，所以它同时钉住了「两个文件得待在一起」。
    """
    env = box.env()
    env["POJIA_GUI_NO_OPEN"] = "1"          # 别在测试机上弹浏览器
    proc = subprocess.Popen([sys.executable, box.prog], cwd=box.root, env=env,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines = []

    def _drain():
        for raw in proc.stdout:
            lines.append(raw.decode("utf-8", "replace"))

    threading.Thread(target=_drain, daemon=True).start()
    try:
        deadline = time.time() + 120
        url = ""
        while time.time() < deadline:
            for text in lines:
                m = URL_RE.search(text)
                if m:
                    url = m.group(1)
                    break
            if url or proc.poll() is not None:
                break
            time.sleep(0.1)
        assert url, "零参数启动没起界面（退出码 %r）：%s" % (proc.poll(), "".join(lines))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()


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


# ------------------------------------------------------------ C13 哈希标记

def test_c13_hash_marker_uses_legacy_prefix(box):
    """前缀 `pjm:h=` 是磁盘兼容契约，换一个就读不出老机器上的哈希。"""
    d, path = _claude(box)
    box.run("--target", "claude", "--claude-dir", d, "--apply", "--yes")
    blob = open(path, encoding="utf-8").read()
    assert "pjm:h=" in blob, "哈希标记前缀不是 pjm:h=，老机器上的状态会判错"


# ------------------------------------------------------------ C14 镜像层

def test_c14_apply_writes_and_revert_removes_mirror(box):
    """主块被客户端过滤掉时，镜像层是唯一的第二重保险。"""
    d, path = _claude(box)
    r = box.run("--target", "claude", "--claude-dir", d, "--apply", "--yes")
    assert r.returncode == 0, box.out(r)
    blob = open(path, encoding="utf-8").read()
    assert "<!-- POJIA-MODIFIER-MIRROR:BEGIN -->" in blob, "没写镜像层"
    assert "<!-- POJIA-MODIFIER-MIRROR:END -->" in blob, "镜像层没有结束标记"

    box.run("--target", "claude", "--claude-dir", d, "--revert", "--yes")
    back = open(path, encoding="utf-8").read()
    assert "POJIA-MODIFIER-MIRROR" not in back, "撤回没删掉镜像层"


# --------------------------------------------------- C12 旧版本标记的兼容

LEGACY_HEADERS = ("pjm:h=", "unlock-v6:h=", "unlock-v4:h=")


@pytest.mark.parametrize("header", LEGACY_HEADERS)
def test_c12_recognizes_legacy_hash_headers(box, header):
    """老版本注入过的文件，必须认得出、撤得掉。

    认不出来会走成"没有我们的块，无需还原"——用户以为还原了，实际一个字没动。
    """
    d = box.target("legacy")
    path = os.path.join(d, "CLAUDE.md")
    body = (
        "# 用户自己的规则\n"
        "\n"
        "<!-- POJIA-NEXT-INJECT:BEGIN -->\n"
        "<!-- " + header + "0123456789ab -->\n"
        "这是旧版本写进来的政策正文，用户不该看到它。\n"
        "<!-- POJIA-NEXT-INJECT:END -->\n"
    )
    open(path, "w", encoding="utf-8", newline="").write(body)

    r = box.run("--target", "claude", "--claude-dir", d, "--revert", "--yes")
    assert r.returncode == 0, box.out(r)
    back = open(path, encoding="utf-8").read()
    assert "旧版本写进来的政策正文" not in back, \
        "旧标记 %s 没被认出来，块还留在文件里" % header
    assert "用户自己的规则" in back, "用户原文被一起删掉了"


# ------------------------------------------------- 已知偏差（新实现应修）

def test_revert_leaves_no_residue(box):
    d = box.target("resid")
    open(os.path.join(d, "CLAUDE.md"), "wb").write(CLAUDE_SAMPLE)
    box.run("--target", "claude", "--claude-dir", d, "--apply", "--yes")
    box.run("--target", "claude", "--claude-dir", d, "--revert", "--yes")
    left = sorted(n for n in os.listdir(d) if not n.endswith(".pojia.bak"))
    assert left == ["CLAUDE.md"], "还原后还剩：%s" % left


# --------------------------------------------------- C7 更新通道（梯度 + 持久化）
#
# 一次拉一页发布，在本地按渠道筛：alpha 收 alpha/beta/mod，beta 收 beta/mod，
# mod 只收 mod。以前看 /releases/latest，预发布被整段跳过 —— 装 beta 的人
# 永远等不到下一个 beta，界面自然「提示更新不生效」。

_FAKE_RELEASES = [
    {"tag_name": "v3.0.0-alpha", "draft": False,
     "assets": [{"name": "alpha.zip", "browser_download_url": "http://127.0.0.1/a"}]},
    {"tag_name": "v1.9.0-beta", "draft": False, "assets": []},
    {"tag_name": "v1.5.0-mod", "draft": False, "assets": []},
    {"tag_name": "v9.9.9-mod", "draft": True, "assets": []},      # 草稿不算数
]


def _serve_releases(payload):
    """起一个只喂 JSON 的本地服务，返回 (server, url)。用完 shutdown。"""
    import http.server

    body = json.dumps(payload).encode("utf-8")

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d/releases" % srv.server_address[1]


def _update_json(text):
    m = re.search(r"#update (\{.*\})", text)
    assert m, "没打出机器可读的更新行：\n%s" % text
    return json.loads(m.group(1))


@pytest.mark.parametrize("channel,want", [
    ("alpha", "3.0.0-alpha"),     # 三条都收，版本最高的那条
    ("beta", "1.9.0-beta"),       # 不收 alpha
    ("mod", "1.5.0-mod"),         # 只收正式版
])
def test_c7_update_channel_ladder(box, channel, want):
    srv, url = _serve_releases(_FAKE_RELEASES)
    try:
        r = box.run("--settings", "channel=" + channel)
        assert r.returncode == 0, box.out(r)
        r = box.run("--check-update", env_extra={"POJIA_UPDATE_API": url})
        assert r.returncode == 0, box.out(r)
        data = _update_json(box.out(r))
        assert data["latest"] == want, box.out(r)
        assert data["channel"] == channel
    finally:
        srv.shutdown()


def test_c7_update_skips_draft(box):
    """草稿版本号再高也不能算「最新发布」。"""
    srv, url = _serve_releases(_FAKE_RELEASES)
    try:
        box.run("--settings", "channel=mod")
        r = box.run("--check-update", env_extra={"POJIA_UPDATE_API": url})
        assert _update_json(box.out(r))["latest"] != "9.9.9-mod"
    finally:
        srv.shutdown()


def test_c7_settings_round_trip(box):
    r = box.run("--settings", "channel=mod auto=off")
    assert r.returncode == 0, box.out(r)
    r = box.run("--settings")
    m = re.search(r"#settings (\{.*\})", box.out(r))
    assert m, box.out(r)
    data = json.loads(m.group(1))
    assert data["channel"] == "mod"
    assert data["auto_check"] is False


def test_c7_settings_rejects_junk(box):
    r = box.run("--settings", "channel=nightly")
    assert r.returncode != 0, "乱填的通道被接受了：%s" % box.out(r)
    assert "alpha / beta / mod" in box.out(r)
