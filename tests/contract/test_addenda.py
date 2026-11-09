# -*- coding: utf-8 -*-
"""特化注入：工具型目标要拿到「执行纪律 + 本模型专用的坏法」，不是一句话。

分层在 policy_src/addenda.json 的 _layers 里：层文本共享，多个目标叠同一份，
改一处三个目标同时生效。这里守住四件事：
  · 20 个目标谁都不能没有特化段（空字符串也算漏）；
  · _layers 只能指向存在的目标与存在的层；
  · kiro 必须是「执行纪律 → Claude → Kiro」这个顺序（第三段开头就说「上面那六条」）；
  · 层文本要真的进 <content_policy>，不能只留在 ADDENDA 里。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pojia  # noqa: E402


def test_every_target_has_addendum():
    for t in pojia.TARGETS:
        assert pojia.target_addendum(t.key).strip(), "%s 没有特化段" % t.key


def test_layers_reference_known_targets_and_layers():
    layers = pojia.ADDENDA.get("_layers") or {}
    keys = set(t.key for t in pojia.TARGETS)
    assert set(layers) <= keys, "层表里有不存在的目标"
    for names in layers.values():
        for name in names:
            text = pojia.ADDENDA.get(name)
            assert isinstance(text, str) and text.strip(), "层 %s 是空的" % name


def test_kiro_stacks_three_sections_in_order():
    text = pojia.target_addendum("kiro")
    marks = ("执行纪律", "Claude 专用", "Kiro 专用")
    pos = [text.index(m) for m in marks]
    assert pos == sorted(pos), "kiro 的三段顺序不对，Kiro 段开头引用的「上面那六条」会指空"


def test_plain_target_gets_no_layer():
    text = pojia.target_addendum("wb")
    assert "执行纪律" not in text
    assert text.startswith("## 本客户端补充")


def test_policy_core_carries_addendum():
    core = pojia.policy_core(pojia.Ctx().persona, "claude")
    assert "Claude 专用" in core
    assert "<content_policy>" not in core      # 段落本身由模板提供，正文不许自带


def test_antigravity_split_keeps_both_files_under_limit():
    """Antigravity 单文件 24,000 字节封顶、从尾部截断 —— 自证恰在最后。

    所以正文必须拆两个文件：主文件放政策本体，特化段放 rules/ 那个。
    """
    ctx = pojia.Ctx()
    t = [x for x in pojia.TARGETS if x.key == "antigravity"][0]
    plan = t.plan(ctx, "C:/fake")
    assert len(plan) == 2
    sizes = {}
    for path, kind, payload in plan:
        assert payload, "%s 没有正文" % path
        sizes[kind] = len(payload.encode("utf-8"))
        assert sizes[kind] < t.RULE_MAX_BYTES, "%s 有 %d 字节，会被截断" % (path, sizes[kind])
    block = [p for p in plan if p[1] == "block"][0][2]
    rules = [p for p in plan if p[1] == "whole"][0][2]
    assert pojia.echo_section("antigravity").splitlines()[0] in block
    assert "Gemini 专用" not in block          # 特化段不许留在主文件里
    assert "Gemini 专用" in rules
    assert rules.startswith("---\ntrigger: always_on")
