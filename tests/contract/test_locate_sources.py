# -*- coding: utf-8 -*-
"""定位链的四个来源：进程镜像路径、切换工具配置、卸载登记表字段、重定向的桌面。

背景：这条链原来有三个洞。
  1. 进程只解析命令行，还要求命令行里含 _npx / node_modules / program files ——
     双击启动、或套壳启动器把 exe 名当参数传的机器直接空手。
  2. 多版本切换器（wb-switch / cc-switch）里存着每个版本的绝对路径，整套没读。
  3. 卸载登记表只读 InstallLocation / DisplayIcon，Electron 应用常常只写
     UninstallString，于是注册表这层也是空的。
另外桌面与开始菜单可以被 OneDrive、组策略、搬家工具重定向，拼
%USERPROFILE%\\Desktop 一律指错地方，必须问 shell。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pojia  # noqa: E402

WIN_ONLY = pytest.mark.skipif(not sys.platform.startswith("win"),
                              reason="盘符路径 / 注册表 / 快捷方式只在 Windows 上存在")


class _FakeTarget(pojia.Target):
    """标志物严格的假目标：只看 fake.marker 在不在。"""

    key = "fake"
    name = "Fake"
    exe = "Fake.exe"
    procs = ("Fake",)
    markers = ("fake.marker",)


def _install(tmp_path, sub=""):
    root = tmp_path / ("Fake" + sub)
    (root / "bin").mkdir(parents=True, exist_ok=True)
    (root / "fake.marker").write_text("x", encoding="utf-8")
    (root / "bin" / "Fake.exe").write_text("", encoding="utf-8")
    return str(root)


# --------------------------------------------------------------- 进程镜像路径

def test_proc_image_path_self():
    got = pojia._proc_image_path(os.getpid())
    assert got and os.path.isabs(got) and os.path.isfile(got)


def test_proc_image_path_rejects_bad_pid():
    assert pojia._proc_image_path(-1) == ""
    assert pojia._proc_image_path(0) == ""
    assert pojia._proc_image_path("not-a-pid") == ""


def test_from_process_uses_image_path_when_cmdline_empty(tmp_path, monkeypatch):
    """命令行是空的也必须命中：镜像路径由内核给，不靠应用自己拼的字符串。"""
    root = _install(tmp_path)
    monkeypatch.setattr(pojia, "process_table", lambda force=False: [(4242, "Fake", "")])
    monkeypatch.setattr(pojia, "all_cmdlines", lambda: {})
    monkeypatch.setattr(pojia, "_proc_image_path",
                        lambda pid: os.path.join(root, "bin", "Fake.exe")
                        if pid == 4242 else "")
    assert _FakeTarget().from_process() == root


def test_from_process_cmdline_fallback_without_npx_gate(tmp_path, monkeypatch):
    """命令行回退路不能再要求含 _npx / node_modules / program files。"""
    root = _install(tmp_path)
    exe = os.path.join(root, "bin", "Fake.exe")
    monkeypatch.setattr(pojia, "process_table", lambda force=False: [(7, "Fake", "")])
    monkeypatch.setattr(pojia, "_proc_image_path", lambda pid: "")
    monkeypatch.setattr(pojia, "all_cmdlines",
                        lambda: {7: '"%s" --started-by-launcher' % exe})
    assert _FakeTarget().from_process() == root


# ------------------------------------------------------------------ 向上找根

def test_walk_up_skips_generic_dirs(tmp_path):
    root = _install(tmp_path)
    assert pojia._walk_up_to_root(os.path.join(root, "bin"),
                                  _FakeTarget().is_valid) == root


def test_walk_up_stops_at_drive_root():
    drive = os.path.splitdrive(os.path.abspath(os.sep))[0] + os.sep
    assert pojia._walk_up_to_root(drive, lambda d: True) == ""


def test_walk_up_missing_start(tmp_path):
    assert pojia._walk_up_to_root(str(tmp_path / "nope"), lambda d: True) == ""


def test_locator_ok_prefers_is_install(tmp_path):
    """markers 为空时 is_valid 对任何目录都成真，定位链不能拿它当判据。"""

    class _Lenient(pojia.Target):
        markers = ()

        def is_install(self, root):
            return os.path.isfile(os.path.join(root, "only-here"))

    t = _Lenient()
    assert t.is_valid(str(tmp_path)) is True
    assert t.locator_ok(str(tmp_path)) is False


# ------------------------------------------------------------ 卸载登记表字段

def test_dir_of_install_value_forms(tmp_path):
    root = _install(tmp_path)
    exe = os.path.join(root, "bin", "Fake.exe")
    bin_dir = os.path.join(root, "bin")
    assert pojia.norm(pojia._dir_of_install_value(root)) == pojia.norm(root)
    assert pojia.norm(pojia._dir_of_install_value('"%s",0' % exe)) == pojia.norm(bin_dir)
    assert pojia.norm(pojia._dir_of_install_value('"%s" /S' % exe)) == pojia.norm(bin_dir)
    assert pojia.norm(pojia._dir_of_install_value("%s /S" % exe)) == pojia.norm(bin_dir)


def test_dir_of_install_value_rejects_junk():
    for bad in ("", "   ", "{1234-ABCD-0000}", "MsiExec.exe /I{1234}",
                os.path.join(os.sep, "definitely", "not", "here", "app.exe")):
        assert pojia._dir_of_install_value(bad) == ""


# ------------------------------------------------------------------ 重定向目录

def _reset_shortcut_cache(monkeypatch):
    """shortcut_files 有 120 秒进程内缓存，用例之间必须清掉。"""
    monkeypatch.setattr(pojia, "_SHORTCUT_CACHE",
                        {"t": 0.0, "files": [], "limit": 0})


def test_shortcut_files_follow_redirected_desktop(tmp_path, monkeypatch):
    """桌面被重定向后，必须按 known_folder 给的位置找，不能按 home 拼。"""
    desk = tmp_path / "redirected-desktop"
    desk.mkdir()
    (desk / "Fake.lnk").write_bytes(b"")
    _reset_shortcut_cache(monkeypatch)
    monkeypatch.setattr(pojia, "IS_WIN", True)
    monkeypatch.setattr(pojia, "known_folder",
                        lambda name, default="": str(desk) if name == "Desktop" else default)
    monkeypatch.setattr(pojia, "home", lambda: str(tmp_path / "no-home"))
    for env in ("APPDATA", "LOCALAPPDATA", "ProgramData", "PUBLIC"):
        monkeypatch.delenv(env, raising=False)
    got = pojia.shortcut_files()
    assert str(desk / "Fake.lnk") in got


def test_shortcut_files_include_taskbar_pins(tmp_path, monkeypatch):
    pins = tmp_path / "appdata" / "Microsoft" / "Internet Explorer" / "Quick Launch" \
        / "User Pinned" / "TaskBar"
    pins.mkdir(parents=True)
    (pins / "Pinned.lnk").write_bytes(b"")
    _reset_shortcut_cache(monkeypatch)
    monkeypatch.setattr(pojia, "IS_WIN", True)
    monkeypatch.setattr(pojia, "known_folder", lambda name, default="": default)
    monkeypatch.setattr(pojia, "home", lambda: str(tmp_path / "no-home"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    for env in ("LOCALAPPDATA", "ProgramData", "PUBLIC"):
        monkeypatch.delenv(env, raising=False)
    got = pojia.shortcut_files()
    assert str(pins / "Pinned.lnk") in got


# -------------------------------------------------------------- 切换工具配置

def test_exe_paths_unescape_json_backslashes():
    text = '{"p": "C:\\\\Apps\\\\Fake\\\\Fake.exe"}'
    assert pojia._exe_paths_in_text(text, ["Fake.exe"]) == ["C:\\Apps\\Fake"]


def test_switch_config_files_picks_text_only(tmp_path, monkeypatch):
    home = tmp_path / "home"
    conf = home / ".wb-switch"
    conf.mkdir(parents=True)
    (conf / "versions.json").write_text("{}", encoding="utf-8")
    (conf / "blob.bin").write_bytes(b"\x00\x01")
    monkeypatch.setattr(pojia, "home", lambda: str(home))
    for env in ("APPDATA", "LOCALAPPDATA"):
        monkeypatch.delenv(env, raising=False)
    names = [os.path.basename(p) for p in pojia.switch_config_files(force=True)]
    assert "versions.json" in names
    assert "blob.bin" not in names


@WIN_ONLY
def test_from_switch_finds_install_root(tmp_path, monkeypatch):
    root = _install(tmp_path)
    exe = os.path.join(root, "bin", "Fake.exe")
    home = tmp_path / "home"
    conf = home / ".wb-switch"
    conf.mkdir(parents=True)
    payload = '{"install": "%s"}' % exe.replace("\\", "\\\\")
    (conf / "versions.json").write_text(payload, encoding="utf-8")
    monkeypatch.setattr(pojia, "home", lambda: str(home))
    for env in ("APPDATA", "LOCALAPPDATA"):
        monkeypatch.delenv(env, raising=False)
    pojia.switch_config_files(force=True)
    assert _FakeTarget().from_switch() == root
