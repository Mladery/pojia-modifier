# -*- coding: utf-8 -*-
"""逐目标往返自检（不属于交付物，只用来证明行为等价）。

对 20 个目标各造一个假安装，跑：
    注入 -> 再注入（必须字节不变）-> 撤回（必须字节回到原样）

只比字节，不看内部结构。
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROG = os.path.join(ROOT, "src", "pojia.py")
PY = sys.executable

PASS = []
FAIL = []


def tree(top, skip_suffix=(".pojia.bak", ".dshpurge.bak", ".unlockbak", ".unlockbak-ai")):
    out = {}
    for base, dirs, files in os.walk(top):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".pojia")]
        for f in files:
            if f.endswith(skip_suffix):
                continue
            p = os.path.join(base, f)
            rel = os.path.relpath(p, top)
            with open(p, "rb") as fh:
                blob = fh.read()
            out[rel] = hashlib.sha256(blob).hexdigest()
    return out


def run(home, *argv):
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SystemRoot": os.environ.get("SystemRoot", ""),
        "COMSPEC": os.environ.get("COMSPEC", ""),
        "PATHEXT": os.environ.get("PATHEXT", ""),
        "WINDIR": os.environ.get("WINDIR", ""),
        "HOME": home,
        "USERPROFILE": home,
        "APPDATA": os.path.join(home, "AppData", "Roaming"),
        "LOCALAPPDATA": os.path.join(home, "AppData", "Local"),
        "TEMP": os.path.join(home, "tmp"),
        "TMP": os.path.join(home, "tmp"),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "POJIA_NO_UPDATE_CHECK": "1",
    }
    for d in ("AppData/Roaming", "AppData/Local", "tmp"):
        os.makedirs(os.path.join(home, d), exist_ok=True)
    return subprocess.run([PY, PROG] + list(argv), env=env, cwd=home,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)


def out(p):
    return ((p.stdout or b"") + (p.stderr or b"")).decode("utf-8", "replace")


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if isinstance(data, bytes) else "w"
    kw = {} if isinstance(data, bytes) else {"encoding": "utf-8"}
    with open(path, mode, **kw) as fh:
        fh.write(data)


CLAUDE_MD = b"# my rules\r\n\r\n- keep it short\r\n"


def seed(root):
    """-> (key, argv_extra, 需要比对的目录)"""
    cases = []

    # 1 dsh
    d = os.path.join(root, "dsh")
    write(os.path.join(d, "resources", "app", "node_modules", "@deepseek-ai",
                       "dsh-agent-instructions", "lib", "agent.js"),
          "const SYSTEM = \"You are DSH, a coding assistant. " + "x" * 400 + "\";\n"
          "module.exports = { SYSTEM };\n")
    write(os.path.join(d, "resources", "app", "node_modules", "@deepseek-ai",
                       "dsh-web-app", "presets", "base.patch.yml"), "name: base\n")
    cases.append(("dsh", ["--dsh-dir", d], d))

    # 2 wb
    w = os.path.join(root, "wb")
    write(os.path.join(w, "resources", "app.asar.unpacked", "resources", "templates",
                       "workbuddy-prompt.tpl"), "你是 WorkBuddy。\r\n{{persona}}\r\n")
    write(os.path.join(w, "resources", "app.asar.unpacked", "resources", "templates",
                       "product-a.tpl"), "产品模板 A\r\n")
    data = os.path.join(root, "wb-data")
    os.makedirs(data, exist_ok=True)
    cases.append(("wb", ["--wb-install", w, "--wb-data", data], w))

    # 3 wbintl
    wi = os.path.join(root, "wbintl")
    write(os.path.join(wi, "WorkBuddyAI.exe"), b"MZ")
    write(os.path.join(wi, "resources", "app.asar.unpacked", "resources", "templates",
                       "workbuddy-prompt.tpl"), "You are WorkBuddy.\r\n")
    di = os.path.join(root, "wbintl-data")
    os.makedirs(di, exist_ok=True)
    cases.append(("wbintl", ["--wbintl-install", wi, "--wbintl-data", di], wi))

    # 4 zcode
    z = os.path.join(root, "zcode")
    os.makedirs(z, exist_ok=True)
    cases.append(("zcode", ["--zcode-dir", z], z))

    # 5 codex
    c = os.path.join(root, "codex")
    write(os.path.join(c, "config.toml"), 'model = "gpt-5"\r\n\r\n[mcp]\r\nx = 1\r\n')
    cases.append(("codex", ["--codex-dir", c], c))

    # 6 cursor
    cu = os.path.join(root, "cursor")
    write(os.path.join(cu, "rules", "keep.mdc"), "---\r\nalwaysApply: true\r\n---\r\n")
    cases.append(("cursor", ["--cursor-dir", cu], cu))

    # 7 claude
    cl = os.path.join(root, "claude")
    write(os.path.join(cl, "CLAUDE.md"), CLAUDE_MD)
    cases.append(("claude", ["--claude-dir", cl], cl))

    # 8 antigravity
    ag = os.path.join(root, "antigravity")
    write(os.path.join(ag, "GEMINI.md"), "# gemini rules\n")
    cases.append(("antigravity", ["--gemini-dir", ag], ag))

    # 9..17 通用标记块型
    simple = [
        ("qwen", "QWEN.md"), ("iflow", "IFLOW.md"),
        ("trae", os.path.join("rules", "project_rules.md")),
        ("codebuddy", "CODEBUDDY.md"), ("opencode", "AGENTS.md"),
        ("windsurf", os.path.join("memories", "global_rules.md")),
        ("cline", "pojia-inject.md"), ("copilot", "copilot-instructions.md"),
        ("kiro", os.path.join("steering", "pojia-inject.md")),
        ("reasonix", "AGENTS.md"),
        ("traecn", os.path.join("rules", "project_rules.md")),
        ("qodercn", os.path.join("agents", "purge", "qodercn.md")),
    ]
    for key, rel in simple:
        d = os.path.join(root, key)
        write(os.path.join(d, rel), "user content for %s\r\n" % key)
        cases.append((key, ["--%s-dir" % key if key != "antigravity" else "--gemini-dir", d], d))
    return cases


def one(root, key, extra, top):
    home = os.path.join(root, "home-" + key)
    os.makedirs(home, exist_ok=True)
    before = tree(top)

    r1 = run(home, "--target", key, *(extra + ["--apply", "--yes"]))
    if r1.returncode != 0:
        FAIL.append("%s: apply 退出码 %d\n%s" % (key, r1.returncode, out(r1)))
        return
    once = tree(top)
    if once == before:
        FAIL.append("%s: apply 之后文件没变" % key)
        return

    r2 = run(home, "--target", key, *(extra + ["--apply", "--yes"]))
    twice = tree(top)
    if r2.returncode != 0:
        FAIL.append("%s: 二次 apply 退出码 %d\n%s" % (key, r2.returncode, out(r2)))
        return
    if twice != once:
        diff = sorted(set(once) ^ set(twice)) or [k for k in once if once[k] != twice.get(k)]
        FAIL.append("%s: 二次 apply 不是幂等的，差异 %s" % (key, diff[:4]))
        return

    r3 = run(home, "--target", key, *(extra + ["--revert", "--yes"]))
    if r3.returncode != 0:
        FAIL.append("%s: revert 退出码 %d\n%s" % (key, r3.returncode, out(r3)))
        return
    back = tree(top)
    if back != before:
        diff = sorted(set(before) ^ set(back)) or [k for k in before if before[k] != back.get(k)]
        FAIL.append("%s: 撤回没回到原样，差异 %s" % (key, diff[:6]))
        return
    PASS.append(key)


def main():
    root = tempfile.mkdtemp(prefix="pojia-selftest-")
    try:
        for key, extra, top in seed(root):
            one(root, key, extra, top)
        print("通过 %d / 失败 %d" % (len(PASS), len(FAIL)))
        print("通过：" + ", ".join(PASS))
        for f in FAIL:
            print("\n[FAIL] " + f)
        return 1 if FAIL else 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
