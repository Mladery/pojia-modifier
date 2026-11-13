# -*- coding: utf-8 -*-
"""WorkBuddy 运行时缓存的清理范围。

客户端把每轮用的 product 配置缓存到 ~/.workbuddy/cache/ 下。老版本只留一个
acc-product-config-v3.json；新版改成每个进程一份：

    acc-product-config-v3-<pid>-<guid>.json

退出后并不清。清理逻辑如果只删老名字，等于一份都删不到 —— 实测残留 11 份、
最老的一天前。缓存一直被复用，新政策写进 product.json 也读不到，表现就是
「注入成功但拦截到的提示词里没有政策」。

这里只测收口函数的选人范围：认版本前缀 + .json 结尾，跳过 .unlockbak。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pojia  # noqa: E402


def _touch(path):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{}")


def test_finds_every_generation(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    _touch(cache / "acc-product-config-v3.json")
    _touch(cache / "acc-product-config-v3-11304-e8e49495.json")
    _touch(cache / "acc-product-config-v3-6452-f549855f.json")
    _touch(cache / "acc-product-config-v3.json.unlockbak")
    _touch(cache / "update-endpoint.json")

    got = sorted(os.path.basename(p) for p in pojia.wb_cache_files(str(tmp_path)))

    assert got == [
        "acc-product-config-v3-11304-e8e49495.json",
        "acc-product-config-v3-6452-f549855f.json",
        "acc-product-config-v3.json",
    ]


def test_missing_cache_dir_is_empty(tmp_path):
    assert pojia.wb_cache_files(str(tmp_path)) == []
    assert pojia.wb_cache_files("") == []
