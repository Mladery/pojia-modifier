#!/usr/bin/env bash
# 把 out/ 里的产物挂到当前 tag 的 Release 上。
#
# 为什么要单独一个脚本：六个 job 并行跑，每个都执行同一段「建 Release → 传产物
# → 标预发布」。1.01.7 的 linux-x64 就死在这里 —— 它 `gh release view` 的那一刻
# 另一个 job 刚把 Release 建出来但还没对上账，于是它走 create 分支，撞上
# `already_exists` 直接退出，Linux 的裸二进制就这么从 Release 里漏掉了
# （其余六个产物都在，checksums 因为 needs 失败被跳过）。
#
# 所以这里的每一步都当「可能会被别人抢先」来写：
#   · 建 Release：view 拿不到就建，建失败但原因是 already_exists 也算成功；
#   · 传产物：--clobber 覆盖，失败重试几次（并发上传偶尔会撞到临时错误）；
#   · 标预发布：同样重试。
#
# 用法：publish_release.sh <tag> <文件...>
#   publish_release.sh v1.01.7-beta out/*

set -uo pipefail

TAG="${1:?用法：publish_release.sh <tag> <文件...>}"
shift

if [ -z "${GH_TOKEN:-}" ]; then
  echo "没有 GH_TOKEN，传不了产物" >&2
  exit 1
fi

NOTES="docs/release-notes/$TAG.md"

# 建（或确认已经有人建好）这个 tag 的 Release。
ensure_release() {
  local i out
  for i in 1 2 3 4 5; do
    if gh release view "$TAG" >/dev/null 2>&1; then
      return 0
    fi
    if [ -f "$NOTES" ]; then
      if out=$(gh release create "$TAG" --title "破甲修改器 ${TAG#v}" \
                 --notes-file "$NOTES" 2>&1); then
        return 0
      fi
    else
      # 没有手写说明才退回自动生成 —— 它会把从第一个提交起的全部标题堆上来。
      if out=$(gh release create "$TAG" --title "破甲修改器 ${TAG#v}" \
                 --generate-notes 2>&1); then
        return 0
      fi
    fi
    case "$out" in
      # 并发 job 抢先建好了。这不是错误，接着传产物就行。
      *already_exists*|*already\ exists*|*Already\ Exists*)
        return 0 ;;
    esac
    echo "建 Release 没成（第 $i 次）：$out" >&2
    sleep $((i * 3))
  done
  return 1
}

ensure_release || { echo "建 Release 失败：$TAG" >&2; exit 1; }

# 传产物。--clobber：重跑同一个 tag 能覆盖旧文件。
upload() {
  local i
  for i in 1 2 3 4 5; do
    if gh release upload "$TAG" "$@" --clobber; then
      return 0
    fi
    echo "传产物没成（第 $i 次），$((i * 3)) 秒后重试" >&2
    sleep $((i * 3))
  done
  return 1
}

if [ "$#" -gt 0 ]; then
  upload "$@" || { echo "产物传不上去" >&2; exit 1; }
fi

# 强制「已发布」。删过 tag 再重推、或者 release 建得比 tag 早的时候，gh 会把它
# 留在草稿态 —— 草稿在 Releases 页面上看不到，用户只看到一个空页面。
# 版本后缀定渠道：-alpha / -beta 是预发布，-mod 才是稳定版。预发布必须标出来，
# 否则 /releases/latest 会把它当正式版，稳定版用户会被提示升级到 beta。
publish() {
  local i
  for i in 1 2 3 4 5; do
    case "$TAG" in
      *-alpha*|*-beta*)
        gh release edit "$TAG" --draft=false --prerelease && return 0 ;;
      *)
        gh release edit "$TAG" --draft=false --prerelease=false && return 0 ;;
    esac
    echo "改发布状态没成（第 $i 次）" >&2
    sleep $((i * 3))
  done
  return 1
}

publish || { echo "没能把 Release 标成已发布" >&2; exit 1; }

# 发布说明跟着仓库走：Release 早于说明改动的（比如先发后补），重跑一次就同步。
if [ -f "$NOTES" ]; then
  gh release edit "$TAG" --notes-file "$NOTES" >/dev/null || \
    echo "发布说明没同步上，Release 已发，说明可以手动补" >&2
fi

echo "已发布 $TAG"
