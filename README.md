# 破甲修改器

> 产物名 `pojia-modifier`，对外版本号 **`v1.03.5-beta`**，MIT 正文 + Commons Clause。
> 后缀即渠道：`-alpha` 开发版、`-beta` 测试版、`-mod` 稳定版。
> 仅限在**自己有权管理的本机设备**上使用，下载前请读 [完整免责声明](docs/disclaimer.md)。

[![CI](https://github.com/Mladery/pojia-modifier/actions/workflows/ci.yml/badge.svg)](https://github.com/Mladery/pojia-modifier/actions/workflows/ci.yml)
[![Build](https://github.com/Mladery/pojia-modifier/actions/workflows/build.yml/badge.svg)](https://github.com/Mladery/pojia-modifier/actions/workflows/build.yml)
[![License](https://img.shields.io/badge/license-MIT%20%2B%20Commons%20Clause-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)

**一句话：把你电脑上 20 个 AI 客户端「自己改不到的内置提示词」，换成你自己写的那份。**

| 换完之后 | 说明 |
|---|---|
| 用**你的**身份设定 | 而不是软件自带的默认人格 |
| **20 个客户端一份口径** | 共用一份人格文本，不用各改各的 |
| **当场能自证** | 发一句固定口令验证真载入，不靠「感觉好像生效了」 |
| **随时能还原** | `--revert` 回官方原版，改前备份一直都在 |

> 它**不修改软件本体**：只做文本文件层面的替换。破甲流程不删包、不写注册表、不装服务（为了定位安装目录，会读一次卸载表与 `App Paths`，只读不写）；全程不发任何网络请求（联网只发生在你主动用 `--fetch-tools` / `--git-bash` / `--update` 拉东西，或启动时那一次可以关掉的版本检查）。

## 使用边界（必读）

> 以下是摘要。**初次下载的用户请务必读一遍 [完整免责声明](docs/disclaimer.md)** —— 含 Commons Clause 的边界、授权范围与权利人通知渠道。

- **只动你自己的机器。** 读写限于本机安装目录与用户目录，不碰他人网站 / 服务器 / 账号，不修改任何服务端，不伪造请求。
- **不是破解工具。** 不生成注册码、不伪造许可证、不绕过付费墙。它改的是你自己机器上的提示词文本。
- **可逆、可审计。** 改前写旁路备份，`--revert` 一键还原；源码全公开，发布的 exe 由本仓库 Actions 从同一份源码构建。
- **无后门、无遥测。** 无账号、无登录、无统计、无云控、**无静默更新** —— 从不自动下载、自动替换、自动重启。升级只有一条路：你按下「安装」（界面上的按钮 / 菜单 / `--update`）。核心流程（定位 → 备份 → 替换 → 校验 → 还原）全程离线。
- **联网只做三件事，都只下载、都可关。** ① `--fetch-tools` 拉 busybox 与 Everything 的官方二进制；② `--git-bash` 拉 Git for Windows 安装包；③ 启动 / 打开界面时查一次「有没有新版」——只读 GitHub 公开的发布列表（`releases`，最近 30 条），不带任何本机信息、不发 query，结果缓存一天，查到了也只是一个提示加一个安装按钮。不想让它查：界面上点「以后再说」，或设置里关掉「启动时检查更新」，命令行加 `--no-update-check`。
- **后果自负。** 按现状（AS IS）提供，无任何担保。目标客户端可能异常、更新失效、配置损坏或账号受限 —— 这些风险由使用者承担。

## 界面

![首屏：选软件、DSH 处理方式、这次会做什么](docs/images/screenshot-home.png)

就是本机网页 UI：脚本起一个只绑 `127.0.0.1` 的页面，带随机 token，关掉窗口即退出。

## 支持的目标

| 目标 | 说明 |
|---|---|
| `dsh` | DeepSeek Harness（Desktop / npm 全局 / npx 缓存 / 便携版） |
| `wb` | WorkBuddy 国内版（模板 + 账号级云记忆） |
| `wbintl` | WorkBuddy 国际版（`WorkBuddyAI.exe`） |
| `zcode` | ZCode（`AGENTS.md` / Memory / 技能 / 可选 cjs 系统提示词） |
| `codex` | OpenAI Codex CLI（`config.toml` 的 `model_instructions_file`） |
| `cursor` | Cursor（`.cursor/rules/*.mdc`） |
| `claude` | Claude Code（`CLAUDE.md`） |
| `antigravity` | Antigravity（CLI `agy` / IDE / 桌面端，共用 `~/.gemini`） |
| `qwen` | Qwen Code（`~/.qwen/QWEN.md`） |
| `iflow` | iFlow CLI 心流（`~/.iflow/IFLOW.md`） |
| `trae` | Trae（`~/.trae` / `~/.trae-cn`，均读 `rules/project_rules.md`） |
| `codebuddy` | CodeBuddy 腾讯（`~/.codebuddy/CODEBUDDY.md`） |
| `opencode` | OpenCode（`~/.config/opencode/AGENTS.md`） |
| `windsurf` | Windsurf（`~/.codeium/windsurf/memories/global_rules.md`） |
| `cline` | Cline（`~/Documents/Cline/Rules/pojia-inject.md`） |
| `copilot` | GitHub Copilot CLI（`~/.copilot/copilot-instructions.md`） |
| `kiro` | Kiro（`~/.kiro/steering/pojia-inject.md`） |
| `reasonix` | Reasonix Studio（`%APPDATA%\reasonix/AGENTS.md`，非 `~/.reasonix`） |
| `traecn` | Trae CN（`~/.trae-cn/rules/project_rules.md`，与 `trae` 分开认） |
| `qodercn` | Qoder CN（`~/.qoder-cn/agents/purge/qodercn.md` 带 frontmatter，附 `skills/purge/SKILL.md`） |

## 快速开始

### 三步

1. **写人格** —— `--persona FILE` 指定一份文本；不给就用内置片段（`--persona-list` 看有哪些）。
2. **先预演** —— `--dry-run --apply`，只报要改哪些文件，一个字节都不写。
3. **再执行** —— `--apply`，改前自动旁路备份；之后 `--status` 看状态，`--revert` 还原。

### 常用命令

```bash
python src/pojia.py                      # 交互菜单
python src/pojia.py --status             # 只读：所有目标查一遍
python src/pojia.py --check              # 只读体检：含会话快照的密钥体检（脱敏）
python src/pojia.py --diagnose           # 只读：详细取证，逐文件列出
python src/pojia.py --dry-run --apply    # 预演，不改盘
python src/pojia.py --apply --target wb  # 真打，只处理 WorkBuddy
python src/pojia.py --revert --target wb # 还原
python src/pojia.py --apply --target dsh --dsh-mode preset   # DSH：不改官方文件
python src/pojia.py --apply --target wb --full               # WorkBuddy：五层开关一次做完
python src/pojia.py --clean-spill        # 清过期的会话快照（含明文 Key）
python src/pojia.py --guard install      # 装运行时守卫（Windows 计划任务）
python src/pojia.py --session-guard on   # 装 DSH 会话守卫（拒答续命 / 异常续跑，Cordis 插件）
python src/pojia.py --check-update       # 只查有没有新版（只读，不下不装）
python src/pojia.py --update             # 有新版就下、校验、替换
python src/pojia.py --settings           # 看设置（更新通道 / 启动检查）
python src/pojia.py --settings "channel=mod"   # 换通道：alpha / beta / mod
python src/pojia.py --no-update-check    # 这次启动别查更新
python src/pojia.py --fetch-tools        # 下 busybox / Everything 到用户目录
python src/pojia.py                      # 不带参数 = 直接进图形界面（同 --gui）
python src/pojia_gui.py                  # 只起图形界面（本机网页）
```

**先 `--dry-run`，再动手。** 所有路径都可以用 `--<目标>-dir` 手动指定，记不住就跑 `--pick <目标>` 弹窗选。

### 自证

在客户端**新会话**里单独发一句 `破甲自检`（整条消息只有这四个字），只回一行就说明人格真载入了：

```
破甲已生效｜版本1.03.5-beta｜仓库地址：https://github.com/Mladery/pojia-modifier
```

回复带解释、加戏或拒答 → 人格没生效，先确认目标已**重启**（改的是磁盘文件，运行中的进程不会重读）。

### macOS

`.app` 是整体签名的，往里写文件会让签名失效 —— 带隔离标记的包再启动会报「已损坏」。已经卡住的：

```bash
pojia-modifier --mac-check            # 看哪些包的签名坏了（只读）
pojia-modifier --mac-check --resign   # 顺手签回去
```

手动救援：`codesign --force --deep --sign - /Applications/Xxx.app` 或 `xattr -cr /Applications/Xxx.app`。另外：客户端要**连托盘一起退干净**再重开，`/Applications` 里的包要求属主是你自己。

### 安装版（推荐）

下对应平台的安装包，双击装。装完有菜单入口、能卸载、命令行直接敲 `pojia-modifier`。

| 平台 | 安装包 |
|---|---|
| Windows x64 | `pojia-modifier-windows-x64-setup.exe` |
| Linux x64 | `pojia-modifier-linux-x64-installer.run` |
| macOS Intel | `pojia-modifier-macos-x64-installer.command` |
| macOS Apple Silicon | `pojia-modifier-macos-arm64-installer.command` |

**Windows**：装在 `%LOCALAPPDATA%\pojia-modifier`，**不需要管理员**，也不弹 UAC。再装一次就是升级，`state/` 和备份都留着。静默装 `/S`；指定目录 `/D=D:\tools\pojia`（必须放最后，不加引号）；静默卸载 `uninstall.exe /S`。

**Linux / macOS**：装到 `~/.local/share/pojia-modifier`，命令行入口软链到 `~/.local/bin/pojia-modifier`，**不需要 sudo** —— 装到系统目录的话 `--update` 每次都得提权，自动更新就废了。同一个包再跑一次就是升级，`state/` 与备份原样保留。

```sh
sh pojia-modifier-linux-x64-installer.run              # 交互：问一遍装哪、加不加 PATH
pojia-modifier --uninstall                             # 删程序，留状态与备份
pojia-modifier --uninstall --purge                     # 连用户数据一起删
```

Linux 上自动往应用菜单里放一项；装的时候问要不要把 `~/.local/bin` 写进 shell 配置（`--yes` 模式下不问，也不碰你的 dotfile）。macOS 的包是 `.command`，双击在终端里跑，第一次可能被 Gatekeeper 拦，右键 → 打开。

### 免安装

| 平台 | 安装版（推荐） | 免安装 |
|---|---|---|
| Windows x64 | `pojia-modifier-windows-x64-setup.exe` | `pojia-modifier-windows-x64.exe` |
| Linux x64 | `pojia-modifier-linux-x64-installer.run` | `pojia-modifier-linux-x64` |
| macOS Intel | `pojia-modifier-macos-x64-installer.command` | `pojia-modifier-macos-x64` |
| macOS Apple Silicon | `pojia-modifier-macos-arm64-installer.command` | `pojia-modifier-macos-arm64` |

在 [Actions](https://github.com/Mladery/pojia-modifier/actions/workflows/build.yml) 最新一次运行的 Artifacts 里下；tag 版本在 [Releases](https://github.com/Mladery/pojia-modifier/releases)。用法和脚本一致，把 `python pojia.py` 换成可执行文件即可；人格文件、`state/`、日志都跟着可执行文件走（安装版则在装目录里）。

三点先说：macOS 首次要 `xattr -d com.apple.quarantine`；Windows Defender 可能对单文件 exe 误报（要绝对干净就用源码跑，或用安装版——它不在临时目录里解包，误报少得多）；不带参数双击就进图形界面，想看命令行菜单加 `--menu`。

单文件 exe 每次启动会把自己解包到 `%TEMP%\_MEIxxxxxx`，个别机器的安全软件不放行在临时目录里创建可执行文件，会报 `Could not create temporary directory!`。遇到这个就换安装版。

## 校验

```
3ae0d6c07376bc641dba42d16855a019bf31fc47acf4c76d0e310c153f9c2284  src/pojia.py       (275,470 B / LF)
64c1b4b54bea14d5dba726384f7ed2ed2fa61231120822e7eb3c3099d0dc76ee  src/pojia_gui.py   (48,034 B / LF)
```

`src/` 两份随本仓库每次改动而变，上面的值对应本版。

<details>
<summary><b>下载的可执行文件怎么验</b></summary>

哈希和文件在同一处发布 —— 能改仓库的人可以同时改掉两者，那不叫交叉验证。所以 exe 走另外两条通道：

**通道一：签名 + 仓库钉定的公钥证书（Windows）。** 锚点证书在 `tools/codesign/pojia-signing.cer`（`CN=Mladery, O=Mladery CE, C=CN`，有效期至 2036-11-01）。指纹是整张证书的 SHA-256，比对这一个值就够：

```
ee95267b61a4965829338d80a792d3b3810d6b0c2d8045d6842ce1fb22c8e413
```

```text
.\tools\verify-windows.ps1 -Exe pojia-modifier-windows-x64.exe
# [ OK ] 签名者与锚点证书一致 → 退出码 0
# [FAIL] 签名者不是仓库里钉的那张证书 → 退出码 1
```

脚本比对**整张证书的 SHA-256**，不是主题名 —— 主题名谁都能写，指纹不能。链状态显示 `UnknownError` 是正常的：自签根没进你的信任存储，不影响「签名有效且来自这张证书」这个结论。

**通道二：SHA256SUMS.txt（全平台）。** 每次构建由 `checksums` job 汇总四个产物生成，打 tag 时随 Release 发出：

```bash
sha256sum -c SHA256SUMS.txt        # Linux
shasum -a 256 -c SHA256SUMS.txt    # macOS
```

</details>

## 仓库内容

```
LICENSE                        MIT 正文 + Commons Clause
NOTICE                         目录职责、程序结构、运行时标记
src/pojia.py                   命令行主程序（零第三方依赖）
src/pojia_gui.py               图形界面：本机网页 UI，零依赖
policy_src/                    策略明文：policy / overlay / hardening / echo / addenda
tools/embed_policy.py          明文 → 嵌入常量（重跑必须字节一致）
tools/selftest.py              20 个目标的自检
tools/                         打包与发布：PyInstaller、NSIS、POSIX 安装器、签名与验签
vendor/everything/             Everything SDK 动态库（MIT），用于直查文件索引
tests/contract/                26 条黑盒契约
docs/                          行为规格、免责声明、研发缘由、界面截图
```

跑测试只需要 pytest（脚本本身零依赖），全部在临时目录里操作，**不碰真实的 `~`**：

```bash
python -m pip install pytest && python -m pytest tests/contract -q
```

`src/pojia.py` 里的策略常量由 `policy_src/*.txt` 压出来。改了明文就重跑一次嵌入，否则两者不同步：

```bash
python tools/embed_policy.py && git status --porcelain   # 必须为空
```

## 参与

**欢迎 PR。**

提之前顺手过一遍：

- `python -m pytest tests/contract -q` 全绿。改行为的 PR 请带上能复现问题的契约测试，光改代码没有测试的一律先挂着
- 只改一个目标就只动那个类。别顺手重排整个文件 —— 格式化噪音会把真正的改动淹掉
- 新目标适配请附客户端版本号和 `--diagnose` 输出（本机路径自己打个码）
- 改了 `policy_src/` 记得重跑 `tools/embed_policy.py` 并把结果一起提交

不写代码也帮得上忙：报一个能复现的 bug、补一段某客户端的安装路径、把 README 里过时的说明指出来，都算。

## 致谢

[![贡献者](https://contrib.rocks/image?repo=Mladery/pojia-modifier)](https://github.com/Mladery/pojia-modifier/graphs/contributors)

按并入主线的时间排序，只列代码与文档改动。头像墙按提交记录自动更新，新名字出现即上榜。

- **[zixuan203344](https://github.com/zixuan203344)** —— Reasonix、Trae CN、Qoder CN 三个目标的适配（`v1.03.3-beta`），目标数 17 → 20；一并修掉第二落点撤回后残留、技能文件 YAML 头被覆盖、旧版本块叠加三处问题。

想加自己正在用的客户端，照着 `docs/spec/40-targets.md` 的落点表补一个类，跑一遍 `tools/selftest.py` 再提。

## 许可

**MIT 正文 + Commons Clause，Copyright (c) 2026 Mladery。** 许可正文见 [LICENSE](LICENSE)，目录职责与运行时标记见 [NOTICE](NOTICE)。

**免费，且不许拿它卖钱。** 自己用、公司内部用、教学研究、非营利项目集成、改了再送人 —— 都可以。卖安装包、卖「解锁版」、做付费下载站、包进付费产品或付费托管服务、收钱代部署代运维 —— 不在授权范围内。这是 [Commons Clause 1.0](https://commonsclause.com/) 的原文条件：它只从授权里排除「Sell」，其余 MIT 权利（使用、修改、再分发）原样保留。

遇到有人收费：那不是官方行为，也超出了本许可；可追究的情形是未经授权收费（版权侵权）、删除或隐瞒版权与许可声明、以官方名义收费或暗示背书、使用本项目名称图标造成来源混淆。

**第三方独立性。** 与 WorkBuddy / 腾讯、DeepSeek、Anthropic、OpenAI、Google、Cursor、字节跳动、Moonshot、GitHub 等均无隶属、合作、授权或背书关系。

## 研发缘由

这个项目为什么存在、三类现成做法差在哪、本项目的取舍：[docs/why.md](docs/why.md)。
