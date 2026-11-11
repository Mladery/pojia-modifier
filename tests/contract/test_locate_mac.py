# -*- coding: utf-8 -*-
"""macOS 上的定位：默认配置目录只看「存在且非空」，.app 包按 Contents/Resources 认。

issue #2（mac 用户报的）：除 zcode / codex 外全显示未安装。这不是 mac 独有的
毛病，是默认位置的判据被收紧成了 is_valid（markers 强判据）：

  · ~/.claude 里常年只有 projects/、settings.json 之类，既没有 CLAUDE.md 也没有
    skills → 一个 marker 都不命中 → 判成没装；
  · ~/.gemini 里只有 settings.json，没有 GEMINI.md / antigravity → 同样全灭；
  · 反过来，markers 为空的 zcode、恰好有 config.toml 的 codex 是唯二能认出来的
    —— 和 issue 描述一字不差。

第二类是路径形态：Reasonix 的默认根写成了 Windows 的 AppData 拼接，DSH 只认
resources/app.asar、只扫盘符，WorkBuddy 只找 AppData\\Programs —— 这些在 mac 上
一条都不成立。

测试全部用假 HOME，跑在哪个平台上都一样（不依赖 IS_MAC 为真）。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pojia  # noqa: E402


ENV_KEYS = ("CLAUDE_CONFIG_DIR", "GEMINI_CLI_HOME", "CODEX_HOME", "DSH_HOME",
            "REASONIX_HOME", "REASONIX_STATE_HOME", "ZCODE_HOME", "ZCODE_CONFIG_DIR",
            "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME")


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """一个空 HOME，并把状态文件读空 —— 否则本机的手动指定会顶掉默认位置。"""
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setattr(pojia, "home", lambda: str(h))
    monkeypatch.setattr(pojia, "manual_get", lambda key: "")
    monkeypatch.setattr(pojia, "discovered_get", lambda key: "")
    for k in ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    return h


def _blind(t):
    """把兜底源全部打空：这几条只在真有本机安装 / 真在跑进程时才有结果。"""
    t.from_process = lambda: ""
    t.from_switch = lambda: ""
    t.from_shortcut = lambda: ""
    t.from_everything = lambda: ""
    return t


# ------------------------------------------------------------ 默认位置的判据

def test_default_ok_accepts_dir_with_any_content(fake_home):
    """~/.claude 里只有一个 projects/ 也算装了 —— 这是 issue 的正例。"""
    claude = fake_home / ".claude"
    (claude / "projects").mkdir(parents=True)
    t = pojia.ClaudeTarget()
    assert t.is_valid(str(claude)) is False, "markers 里没有 projects/，前提就不成立"
    assert t.default_ok(str(claude)) is True


def test_default_ok_rejects_empty_dir(fake_home):
    """mkdir 出来的空壳不算装了 —— 放宽不等于全放。"""
    empty = fake_home / ".claude"
    empty.mkdir()
    assert pojia.ClaudeTarget().default_ok(str(empty)) is False


def test_default_ok_accepts_marker_hit(fake_home):
    d = fake_home / ".claude"
    d.mkdir()
    (d / "CLAUDE.md").write_text("x", encoding="utf-8")
    assert pojia.ClaudeTarget().default_ok(str(d)) is True


def test_default_ok_rejects_missing_dir(tmp_path):
    assert pojia.ClaudeTarget().default_ok(str(tmp_path / "nope")) is False


# ------------------------------------------------------------ 默认位置能解析出来

def test_claude_resolves_from_projects_only(fake_home):
    claude = fake_home / ".claude"
    (claude / "projects").mkdir(parents=True)
    root, src, _tried = _blind(pojia.ClaudeTarget()).resolve()
    assert root == str(claude)
    assert src == "默认位置"


def test_antigravity_resolves_with_only_settings(fake_home):
    gem = fake_home / ".gemini"
    gem.mkdir()
    (gem / "settings.json").write_text("{}", encoding="utf-8")
    root, src, _tried = _blind(pojia.AntigravityTarget()).resolve()
    assert root == str(gem)
    assert src == "默认位置"


def test_empty_config_dir_still_reports_missing(fake_home):
    (fake_home / ".claude").mkdir()
    root, _src, tried = _blind(pojia.ClaudeTarget()).resolve()
    assert root == ""
    assert str(fake_home / ".claude") in tried, "试过哪些路径要留痕，否则报错没法自查"


# ------------------------------------------------------------ Reasonix 的 mac 根

def test_reasonix_default_root_on_mac(fake_home, monkeypatch):
    monkeypatch.setattr(pojia, "IS_WIN", False)
    assert pojia.ReasonixTarget().default_root() == str(fake_home / ".reasonix")


def test_reasonix_default_root_on_windows(fake_home, monkeypatch):
    monkeypatch.setattr(pojia, "IS_WIN", True)
    monkeypatch.setenv("APPDATA", str(fake_home / "AppData" / "Roaming"))
    assert pojia.ReasonixTarget().default_root() == str(
        fake_home / "AppData" / "Roaming" / "reasonix")


def test_reasonix_resolves_from_dot_dir(fake_home, monkeypatch):
    monkeypatch.setattr(pojia, "IS_WIN", False)
    d = fake_home / ".reasonix"
    d.mkdir()
    (d / "config.toml").write_text("", encoding="utf-8")
    root, src, _tried = _blind(pojia.ReasonixTarget()).resolve()
    assert root == str(d)
    assert src == "默认位置"


# ------------------------------------------------------------ DSH 的 .app 包

def _mac_bundle(base):
    app = base / "DSH Desktop.app"
    res = app / "Contents" / "Resources"
    res.mkdir(parents=True)
    (res / "app.asar").write_text("", encoding="utf-8")
    return app


def test_dsh_is_install_accepts_mac_bundle(tmp_path):
    app = _mac_bundle(tmp_path)
    t = pojia.DshTarget()
    assert t.is_install(str(app)) is True
    assert t.resource_base(str(app)) == str(app / "Contents" / "Resources" / "app") or \
        t.resource_base(str(app)) == ""


def test_dsh_resource_base_finds_app_dir_in_bundle(tmp_path):
    app = _mac_bundle(tmp_path)
    (app / "Contents" / "Resources" / "app").mkdir()
    assert pojia.DshTarget().resource_base(str(app)) == \
        str(app / "Contents" / "Resources" / "app")


def test_dsh_plan_without_install_root_keeps_profile_entry(fake_home, tmp_path):
    """安装根找不到时 plan 不许崩：base 为空，profile 那一条照出。"""
    cfg = fake_home / ".dsh"
    prof = cfg / "profiles" / "desktop"
    prof.mkdir(parents=True)
    (prof / "cordis.patch.yml").write_text("name: base\n", encoding="utf-8")
    t = pojia.DshTarget()
    ctx = type("Ctx", (), {"persona": "P", "hash": "h"})()
    out = t.plan(ctx, str(cfg))
    paths = [p for p, _k, _v in out]
    assert os.path.join(str(prof), "cordis.patch.yml") in paths
    assert len(paths) == 1, paths


def test_dsh_resolves_to_config_root_when_install_missing(fake_home, monkeypatch):
    # 装成非 Windows：否则本机盘符扫描会先把测试抢走（J 盘上真有一份 DSH）
    monkeypatch.setattr(pojia, "IS_WIN", False)
    cfg = fake_home / ".dsh"
    prof = cfg / "profiles" / "desktop"
    prof.mkdir(parents=True)
    (prof / "cordis.patch.yml").write_text("name: base\n", encoding="utf-8")
    monkeypatch.setattr(pojia, "process_table", lambda: [])
    monkeypatch.setattr(pojia, "all_cmdlines", lambda: {})
    monkeypatch.setattr(pojia, "everything_walk", lambda *a, **k: "")
    t = pojia.DshTarget()
    root, src, _tried = t.resolve()
    assert root == str(cfg)
    assert "配置目录" in src


def test_dsh_no_config_root_no_profiles_is_missing(fake_home, monkeypatch):
    monkeypatch.setattr(pojia, "IS_WIN", False)
    monkeypatch.setattr(pojia, "process_table", lambda: [])
    monkeypatch.setattr(pojia, "all_cmdlines", lambda: {})
    monkeypatch.setattr(pojia, "everything_walk", lambda *a, **k: "")
    (fake_home / ".dsh").mkdir()
    root, _src, _tried = pojia.DshTarget().resolve()
    assert root == "", "~/.dsh 空壳没有 profiles，不许当成可注入的配置根"


# ------------------------------------------------------------ WorkBuddy 的 .app

def test_workbuddy_candidates_include_applications(fake_home, monkeypatch):
    monkeypatch.setattr(pojia, "IS_MAC", True)
    cands = pojia.WorkBuddyTarget().install_candidates()
    assert os.path.join("/Applications", "WorkBuddy.app") in cands
    assert str(fake_home / "Applications" / "WorkBuddyAI.app") in cands


def test_workbuddy_resource_root_prefers_contents(tmp_path):
    app = tmp_path / "WorkBuddy.app"
    (app / "Contents" / "Resources").mkdir(parents=True)
    assert pojia.WorkBuddyTarget().resource_root(str(app)) == \
        str(app / "Contents" / "Resources")


def test_workbuddy_is_intl_reads_bundle_name(tmp_path):
    assert pojia.WorkBuddyTarget().is_intl(str(tmp_path / "WorkBuddyAI.app")) is True
    assert pojia.WorkBuddyTarget().is_intl(str(tmp_path / "WorkBuddy.app")) is False


def test_workbuddy_install_on_mac_bundle(tmp_path):
    app = tmp_path / "WorkBuddy.app"
    tpl = (app / "Contents" / "Resources" / "app.asar.unpacked" / "resources"
           / "templates" / "workbuddy-prompt.tpl")
    tpl.parent.mkdir(parents=True)
    tpl.write_text("x", encoding="utf-8")
    assert pojia.WorkBuddyTarget().is_install(str(app)) is True
