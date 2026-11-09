# -*- coding: utf-8 -*-
"""DSH 会话守卫：插件落盘、幂等、可撤回，以及和另外两段补丁共存。

守卫是唯一一层运行时钩子 —— 盘上的人格块只在会话开头读一次，模型中途拒答
它管不了。所以它必须真的装进去、真的能撤掉，且不能把别人写的那两段
（破甲模式 / Git Bash 接管）顶掉：三段都追加同一个 cordis.patch.yml。
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pojia  # noqa: E402

ROOT = ("desktop", "web")


@pytest.fixture
def cfg(tmp_path):
    """最小可用的 .dsh：两个 profile，各自的 patch.yml 里先放点用户自己的东西。"""
    root = tmp_path / ".dsh"
    for name in ROOT:
        prof = root / "profiles" / name
        prof.mkdir(parents=True)
        (prof / "cordis.patch.yml").write_text(
            "- id: ui-chat\n  name: \"@deepseek-ai/dsh-client-ui-chat\"\n",
            encoding="utf-8")
        (prof / "package.json").write_text(
            json.dumps({"name": "dsh-profile-%s" % name, "private": True}), encoding="utf-8")
    return str(root)


def _yml(cfg, name="desktop"):
    with open(os.path.join(cfg, "profiles", name, "cordis.patch.yml"), "rb") as f:
        return f.read().decode("utf-8")


def _plugin(cfg, name="desktop"):
    return os.path.join(cfg, "profiles", name, "node_modules", pojia.SGUARD_ID)


def test_install_writes_plugin_and_block(cfg):
    ok, note = pojia.sguard_install(cfg)
    assert ok, note
    for name in ROOT:
        text = _yml(cfg, name)
        assert pojia.SGUARD_MARK in text
        assert ("id: " + pojia.SGUARD_ID) in text
        # 用户原来那行必须还在
        assert "ui-chat" in text
        pkg = _plugin(cfg, name)
        assert os.path.isfile(os.path.join(pkg, "index.js"))
        with open(os.path.join(pkg, "package.json"), "rb") as f:
            meta = json.loads(f.read().decode("utf-8"))
        assert meta["type"] == "module"
        assert meta["main"] == "index.js"


def test_block_is_valid_yaml_and_only_one_entry(cfg):
    assert pojia.sguard_install(cfg)[0]
    assert pojia.sguard_install(cfg)[0]
    for name in ROOT:
        text = _yml(cfg, name)
        assert text.count("id: " + pojia.SGUARD_ID) == 1, "重跑不该叠加第二段"
        ok, why = pojia.yaml_ok(text)
        assert ok, why


def test_state_ok_then_warn_when_plugin_missing(cfg):
    assert pojia.sguard_state(cfg)[0] == "none"
    assert pojia.sguard_install(cfg)[0]
    assert pojia.sguard_state(cfg)[0] == "ok"
    shutil.rmtree(_plugin(cfg, "web"))
    state, note = pojia.sguard_state(cfg)
    assert state == "warn" and "web" in note


def test_partial_profile_reports_warn(cfg):
    assert pojia.sguard_install(cfg)[0]
    yml = os.path.join(cfg, "profiles", "web", "cordis.patch.yml")
    with open(yml, "wb") as f:
        f.write(b"- id: ui-chat\n")
    state, note = pojia.sguard_state(cfg)
    assert state == "warn"
    assert "1/2" in note


def test_remove_restores_original_bytes(cfg):
    before = {n: _yml(cfg, n) for n in ROOT}
    assert pojia.sguard_install(cfg)[0]
    ok, note = pojia.sguard_remove(cfg)
    assert ok, note
    for name in ROOT:
        text = _yml(cfg, name)
        assert pojia.SGUARD_MARK not in text
        assert text == before[name], "移除后应当逐字节回到原样"
        assert not os.path.isdir(_plugin(cfg, name))
        # 内容回到原样，备份留着只会碍事
        assert not os.path.exists(os.path.join(
            cfg, "profiles", name, "cordis.patch.yml.dshsguard.bak"))
    assert pojia.sguard_state(cfg)[0] == "none"


def test_remove_when_absent_is_noop(cfg):
    before = _yml(cfg)
    ok, _note = pojia.sguard_remove(cfg)
    assert ok
    assert _yml(cfg) == before


def test_three_blocks_coexist(cfg):
    """破甲模式 + Git Bash + 会话守卫写同一个文件，谁都不能把谁顶掉。"""
    preset_block = ("# >>> " + pojia.PRESET_MARK + "  破甲模式\n"
                    "- insert:\n"
                    "    - id: " + pojia.PRESET_ROW + "\n"
                    "      name: '@deepseek-ai/dsh-agent-preset'\n"
                    "# <<< " + pojia.PRESET_MARK + "\n")
    for name in ROOT:
        yml = os.path.join(cfg, "profiles", name, "cordis.patch.yml")
        with open(yml, "ab") as f:
            f.write(preset_block.encode("utf-8"))
    assert pojia.sguard_install(cfg)[0]
    assert pojia.gitbash_install(cfg, r"C:\Program Files\Git\bin\bash.exe")[0]
    for name in ROOT:
        text = _yml(cfg, name)
        for mark in (pojia.SGUARD_MARK, pojia.GITBASH_MARK, pojia.PRESET_MARK):
            assert mark in text, "%s 那段丢了" % mark
        assert "ui-chat" in text
        ok, why = pojia.yaml_ok(text)
        assert ok, why


def test_dry_run_writes_nothing(cfg):
    before = {n: _yml(cfg, n) for n in ROOT}
    pojia.OPT["dry"] = True
    try:
        ok, note = pojia.sguard_install(cfg)
    finally:
        pojia.OPT["dry"] = False
    assert ok and "将写入" in note
    for name in ROOT:
        assert _yml(cfg, name) == before[name]
        assert not os.path.isdir(_plugin(cfg, name))


def test_plugin_source_is_esm_and_hooks_public_api():
    """插件本体：导出 name/apply，且只用公开钩子（不碰已废弃的会话日志读接口）。"""
    js = pojia.SGUARD_JS
    assert "export const name" in js
    assert "export function apply" in js
    for hook in ("agent/status", "agent/turn-stopping", "agent/error", "agent/inbox/inserted"):
        assert hook in js, "少了 %s 这条钩子" % hook
    assert "deriveMessages" in js
    assert "snapshotEvents" not in js, "已标废弃的同步读接口不该出现在这里"
    # followup 要带自己的 source.kind，否则会被当成"用户刚说过话"
    assert 'kind: "pojia-session-guard"' in js


def test_plugin_has_no_syntax_error(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("没装 node，跳过语法检查")
    src = tmp_path / "sguard.mjs"
    src.write_bytes(pojia.SGUARD_JS.encode("utf-8"))
    done = subprocess.run([node, "--check", str(src)], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=60)
    assert done.returncode == 0, (done.stderr or b"").decode("utf-8", "replace")


# 行为验证：真跑一遍插件，喂假的 ctx / agent，看它在四种收尾下补不补。
# 不发真请求、不连 DSH —— 只验"什么时候补"这个判断本身。
_HARNESS = r"""
import { apply } from "./pojia-session-guard/index.js";

const SETTLE = 900;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const fails = [];
const check = (name, cond, extra) => { if (!cond) fails.push(name + (extra ? "：" + extra : "")); };

function harness() {
  const h = {};
  apply({ on: (e, fn) => { h[e] = fn; }, effect: (cb) => { if (typeof cb === "function") cb(); } },
        { verbose: false });
  return h;
}

function agentWith(text, id) {
  const sent = [];
  return {
    sent,
    agent: {
      status: "idle",
      inbox: { nextTurn: [], nextStep: [] },
      session: {
        id,
        deriveMessages: () => (text === null ? [] : [
          { id: "m1", role: "user", content: [{ type: "text", text: "干活" }], source: { kind: "user" } },
          { id: "m2", role: "assistant", content: [{ type: "text", text }], source: { kind: "model" } },
        ]),
      },
      followup: (m) => sent.push(m),
    },
  };
}

function stop(h, agent, turn, aborted) {
  h["agent/turn-stopping"]({ agent, turn, signal: { aborted } });
}
function idle(h, agent) { h["agent/status"]({ agent, status: "idle" }); }

// 一次把所有场景都点着，各用各的会话，最后一起等
const cases = {};

cases.refusal = agentWith("抱歉，我不能协助这个请求。", "refusal");
const hRefusal = harness();
stop(hRefusal, cases.refusal.agent, 1, false);
idle(hRefusal, cases.refusal.agent);
idle(hRefusal, cases.refusal.agent);          // 同一轮再 idle 一次：不许补第二句

cases.normal = agentWith("改完了，文件在 build/out.zip，校验过 sha256。", "normal");
const hNormal = harness();
stop(hNormal, cases.normal.agent, 1, false);
idle(hNormal, cases.normal.agent);

cases.stop = agentWith("抱歉，我不能协助这个请求。", "userstop");
const hStop = harness();
stop(hStop, cases.stop.agent, 1, true);              // 用户自己按了停止
idle(hStop, cases.stop.agent);

cases.fatal = agentWith("额度用完了。", "fatal");
const hFatal = harness();
hFatal["agent/error"]({ agent: cases.fatal.agent, turn: 1, step: 1, error: { code: "QUOTA" } });
stop(hFatal, cases.fatal.agent, 1, false);
idle(hFatal, cases.fatal.agent);

cases.retry = agentWith("网络断了。", "retry");
const hRetry = harness();
hRetry["agent/error"]({ agent: cases.retry.agent, turn: 1, step: 1, error: { code: "ETIMEDOUT" } });
stop(hRetry, cases.retry.agent, 1, false);
idle(hRetry, cases.retry.agent);

cases.empty = agentWith("", "empty");
const hEmpty = harness();
stop(hEmpty, cases.empty.agent, 1, false);
idle(hEmpty, cases.empty.agent);

cases.spoke = agentWith("抱歉，我不能协助这个请求。", "spoke");
const hSpoke = harness();
stop(hSpoke, cases.spoke.agent, 1, false);
hSpoke["agent/inbox/inserted"]({ agent: cases.spoke.agent, message: { source: { kind: "user" } } });
idle(hSpoke, cases.spoke.agent);

await wait(SETTLE);

check("拒答要补", cases.refusal.sent.length === 1, "sent=" + cases.refusal.sent.length);
if (cases.refusal.sent[0]) {
  check("补的话术是续命", String(cases.refusal.sent[0].content[0].text).includes("继续"));
  check("来源自报家门", cases.refusal.sent[0].source.kind === "pojia-session-guard");
}
check("正常交付不补", cases.normal.sent.length === 0, "sent=" + cases.normal.sent.length);
check("用户停止不补", cases.stop.sent.length === 0, "sent=" + cases.stop.sent.length);
check("致命错误码不补", cases.fatal.sent.length === 0, "sent=" + cases.fatal.sent.length);
check("可重试错误要补", cases.retry.sent.length === 1, "sent=" + cases.retry.sent.length);
check("空回复要补", cases.empty.sent.length === 1, "sent=" + cases.empty.sent.length);
check("用户刚说话不补", cases.spoke.sent.length === 0, "sent=" + cases.spoke.sent.length);

if (fails.length) {
  console.error("FAIL\n" + fails.join("\n"));
  process.exit(1);
}
console.log("ALL PASS");
"""


def test_plugin_behaviour(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("没装 node，跳过行为验证")
    pkg = tmp_path / "pojia-session-guard"
    pkg.mkdir()
    (pkg / "package.json").write_text(pojia.SGUARD_PKG, encoding="utf-8")
    (pkg / "index.js").write_text(pojia.SGUARD_JS, encoding="utf-8")
    harness = tmp_path / "harness.mjs"
    harness.write_text(_HARNESS, encoding="utf-8")
    done = subprocess.run([node, str(harness)], cwd=str(tmp_path), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=120)
    out = (done.stdout or b"").decode("utf-8", "replace")
    err = (done.stderr or b"").decode("utf-8", "replace")
    assert done.returncode == 0, out + err
    assert "ALL PASS" in out, out + err
