#!/bin/sh
# __APP__ 安装器（Linux / macOS）
#
# 一个文件干三件事：装、升级、卸载。头部是这段脚本，尾部贴着一份 tar.gz 载荷
# —— 所以下载页上只有一个文件，不用先猜哪个能用。
#
#   ./__APP__-linux-x64-installer.run 交互安装（双击 / 直接跑）
#   ./__APP__-linux-x64-installer.run --yes 不问，直接装（升级走的就是这条）
#   ./__APP__-linux-x64-installer.run --uninstall 卸载
#   ./__APP__-linux-x64-installer.run --prefix DIR 换安装目录
#
# 装到用户目录而不是 /usr/local：装到系统目录的话，--update 每次都得提权，
# 自动更新就废了。Windows 那边装 %LOCALAPPDATA% 也是这个道理。

APP="__APP__"
APP_NAME=破甲修改器
VERSION="__VERSION__"
ASSET="__ASSET__"

PREFIX="${POJIA_PREFIX:-$HOME/.local/share/$APP}"
BIN_DIR="$HOME/.local/bin"
ASSUME_YES=0
QUIET=0
MODE=install
REVERT=-1          # -1 没问过，0 不还原，1 还原
WANT_PATH=-1       # -1 没问过，0 不加，1 加
PURGE=0

# 变量后面紧跟中文时必须写 ${VAR}：macOS 的 /bin/sh 是 bash 3.2，它在 UTF-8 里
# 扫变量名会多吃掉后面那个字的首字节，`$PREFIX」` 被当成变量 `PREFIX<0xE3>`，
# 未定义 → 整个值变空，剩下的字节还会解码失败，装到一半就报一堆乱码。
say() { [ "$QUIET" = 1 ] || printf '%s\n' "$*"; }
die() { printf '%s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
__APP__ 安装器

  --yes, -y          不问，全用默认值
  --quiet, -q        少说话
  --prefix DIR       安装目录（默认 ~/.local/share/__APP__）
  --uninstall        卸载
  --revert           卸载前先把已改的提示词还原
  --purge            卸载时连 状态/ 和 历史备份/ 一起删
  --add-path         把 ~/.local/bin 写进 shell 配置
  --no-path          不碰 shell 配置
  --help, -h         这一屏

装好之后：直接敲 __APP__ 进图形界面
          加 --menu 进命令行菜单
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y)     ASSUME_YES=1 ;;
    --quiet|-q)   QUIET=1 ;;
    --prefix)     shift; [ $# -gt 0 ] || die "--prefix 后面要跟一个目录"; PREFIX="$1" ;;
    --prefix=*)   PREFIX="${1#--prefix=}" ;;
    --uninstall|--remove) MODE=uninstall ;;
    --revert)     REVERT=1 ;;
    --purge)      PURGE=1 ;;
    --add-path)   WANT_PATH=1 ;;
    --no-path)    WANT_PATH=0 ;;
    --help|-h)    usage; exit 0 ;;
    *)            die "看不懂的参数：${1}（--help 看用法）" ;;
  esac
  shift
done

# 绝对路径 + 不能是 / 或 $HOME。下面要 rm -rf 这个值，手滑一次就是灾难。
case "$PREFIX" in
  ""|"/"|"$HOME"|"$HOME/") die "拒绝把「${PREFIX}」当安装目录" ;;
  /*) ;;
  *)  die "安装目录要给绝对路径：$PREFIX" ;;
esac

# ---------------------------------------------------------------- 卸载
# 安装目录里那份程序自己知道怎么卸（它要跑还原、要摘 PATH）。这里只负责
# 找到它并转发；找不到才做兜底清理。
if [ "$MODE" = uninstall ]; then
  if [ -x "$PREFIX/$APP" ] && [ -f "$PREFIX/install.json" ]; then
    set -- --uninstall
    [ "$ASSUME_YES" = 1 ] && set -- "$@" --yes
    [ "$QUIET" = 1 ] && set -- "$@" --quiet
    [ "$REVERT" = 1 ] && set -- "$@" --revert
    [ "$PURGE" = 1 ] && set -- "$@" --purge
    exec "$PREFIX/$APP" "$@"
  fi
  # 兜底：程序已经没了，但软链 / 桌面项可能还在。
  rm -f "$BIN_DIR/$APP"
  rm -f "$HOME/.local/share/applications/$APP.desktop"
  if [ -d "$PREFIX" ]; then
    say "程序文件不在了，这是残留目录：$PREFIX"
    say "确认没用就手动删：rm -rf '$PREFIX'"
  else
    say "没装过（$PREFIX 不存在）。"
  fi
  exit 0
fi

# ---------------------------------------------------------------- 拆载荷
SELF_PATH=$0
case "$SELF_PATH" in
  /*) ;;
  *) SELF_PATH="$(pwd)/$SELF_PATH" ;;
esac

TMP=$(mktemp -d "${TMPDIR:-/tmp}/pojia-install.XXXXXX") || die "建不了临时目录"
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

LINE=$(awk '/^__POJIA_PAYLOAD_BELOW__$/ {print NR + 1; exit}' "$SELF_PATH" 2>/dev/null)
[ -n "$LINE" ] || die "这文件不完整（找不到载荷），重新下一次"
# tail -n +N 是 POSIX，GNU / BSD / busybox 都认；不要用需要 seek 的工具，
# 那样在管道里跑就废了。
tail -n +"$LINE" "$SELF_PATH" > "$TMP/payload.tgz" || die "拆不开载荷"
tar -xzf "$TMP/payload.tgz" -C "$TMP" || die "解包失败"
SRC="$TMP/$APP"
[ -f "$SRC/$APP" ] || die "载荷里没有 ${APP}，包坏了"
chmod +x "$SRC/$APP" 2>/dev/null
[ -d "$SRC/_internal" ] || say "  注意：载荷里没有 _internal/，只有单文件程序"

# ---------------------------------------------------------------- 环境
OLD_VER=""
if [ -f "$PREFIX/install.json" ]; then
  OLD_VER=$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
            "$PREFIX/install.json" | head -1)
fi

OS=$(uname -s 2>/dev/null || echo unknown)

# 目录不是空的、又没有 install.json：只允许落在「本程序的残留数据」上
# —— 卸载会留下 状态/、历史备份/、persona.md 这些，重装得能接着用。
# 白名单之外的东西一律拒绝：下面要 rm -rf 这个目录，宁可让人换个 --prefix。
# 以后新增数据文件，记得往这个 case 里补一行。
if [ -d "$PREFIX" ] && [ ! -f "$PREFIX/install.json" ]; then
  for p in "$PREFIX"/* "$PREFIX"/.[!.]*; do
    [ -e "$p" ] || continue
    case "$(basename "$p")" in
      状态|历史备份|人格库|skills|备份|persona.md|my-prompt.txt|破甲日志.txt) ;;
      extra-targets.txt|__APP__|提示词快照-*) ;;
      *) die "$PREFIX 里有本程序不认识的东西（$(basename "$p")），不覆盖。换一个 --prefix。" ;;
    esac
  done
fi

if [ -n "$OLD_VER" ] && [ "$OLD_VER" != "$VERSION" ]; then
  say "$APP_NAME $OLD_VER → $VERSION"
  say "  目录 ${PREFIX}（状态/、历史备份/ 会保留）"
elif [ -n "$OLD_VER" ]; then
  say "重新安装 $APP_NAME $VERSION"
  say "  目录 ${PREFIX}（数据保留，程序文件重写一遍）"
else
  say "安装 $APP_NAME $VERSION"
  say "  目录 $PREFIX"
  say "  命令 $BIN_DIR/$APP"
fi

# 要不要加 PATH：默认问一句。PATH 里多一条自己不知道的路径，是个长期的困扰；
# 但不加又敲不到命令。让用户自己决定，别替他决定。
case ":$PATH:" in
  *":$BIN_DIR:"*) PATH_OK=1 ;;
  *)              PATH_OK=0 ;;
esac
if [ "$PATH_OK" = 0 ] && [ "$WANT_PATH" = -1 ]; then
  if [ "$ASSUME_YES" = 1 ]; then
    WANT_PATH=0            # 非交互不乱改别人的 shell 配置
  else
    printf '把 %s 加进 PATH？（写进 shell 配置）[y/N] ' "$BIN_DIR"
    read ans || ans=""
    case "$ans" in y|Y|yes|YES) WANT_PATH=1 ;; *) WANT_PATH=0 ;; esac
  fi
fi

if [ "$ASSUME_YES" != 1 ]; then
  printf '继续？[Y/n] '
  read ans || ans=""
  case "$ans" in n|N|no|NO) say "已取消。"; exit 0 ;; esac
fi

# ---------------------------------------------------------------- 落盘
NEW="$PREFIX.new.$$"
mkdir -p "$(dirname "$PREFIX")" || die "建不了 $PREFIX 的父目录"
rm -rf "$NEW"
mv "$SRC" "$NEW" || die "搬运失败"

# 旧目录里「新目录没有」的东西全部搬过去 —— 状态/、历史备份/、persona.md、
# 日志，以及以后可能加的任何数据文件。列举写死的话，加个新目录就丢数据。
if [ -d "$PREFIX" ]; then
  for p in "$PREFIX"/* "$PREFIX"/.[!.]*; do
    [ -e "$p" ] || continue
    base=$(basename "$p")
    [ -e "$NEW/$base" ] && continue
    mv "$p" "$NEW/$base" || die "搬运 $base 失败"
  done
  rm -rf "$PREFIX" || die "清不掉旧目录：$PREFIX"
fi
mv "$NEW" "$PREFIX" || die "落位失败"
chmod +x "$PREFIX/$APP"

cat > "$PREFIX/install.json" <<EOF
{"prefix": "$PREFIX", "version": "$VERSION", "asset": "$ASSET", "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"}
EOF

mkdir -p "$BIN_DIR" || die "建不了 $BIN_DIR"
ln -sf "$PREFIX/$APP" "$BIN_DIR/$APP" || die "软链失败"

# 桌面菜单项。macOS 上没有 applications 目录这回事，跳过。
if [ "$OS" = Linux ]; then
  DESK="$HOME/.local/share/applications"
  if mkdir -p "$DESK" 2>/dev/null; then
    cat > "$DESK/$APP.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=修改本机 AI 客户端的提示词模板
Exec=$PREFIX/$APP
Terminal=false
Categories=Development;Utility;
EOF
    command -v update-desktop-database >/dev/null 2>&1 && \
      update-desktop-database "$DESK" >/dev/null 2>&1 || true
  fi
fi

if [ "$WANT_PATH" = 1 ]; then
  case "${SHELL##*/}" in
    zsh)  RC="$HOME/.zshrc" ;;
    bash) RC="$HOME/.bashrc" ;;
    *)    RC="$HOME/.profile" ;;
  esac
  if ! grep -q "__APP__ PATH" "$RC" 2>/dev/null; then
    {
      printf '\n# __APP__ PATH\n'
      printf 'case ":$PATH:" in *":%s:"*) ;; *) export PATH="%s:$PATH" ;; esac\n' \
             "$BIN_DIR" "$BIN_DIR"
    } >> "$RC" 2>/dev/null && say "  已写进 ${RC}（重开终端生效）"
  fi
fi

say ""
say "装好了。"
if [ "$PATH_OK" = 0 ] && [ "$WANT_PATH" != 1 ]; then
  say "  $BIN_DIR 不在 PATH 里，现在这么用："
  say "      $PREFIX/$APP"
  say "  想直接敲 ${APP}："
  say "      echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.profile"
fi
say "  卸载：$PREFIX/$APP --uninstall"
say "  升级：跑新版的安装包，或者程序里 --update"
exit 0

__POJIA_PAYLOAD_BELOW__
