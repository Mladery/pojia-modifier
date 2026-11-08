# 行为规格 · 目标定位

> 靶向目标是**固定集合**，每个客户端的自然安装位置也是固定的。所以本层的主体不是
> "搜索算法"，而是**一张写死的路径表**。探测链只在表里的路径不存在时兜底。
>
> 定位失败是最高频的故障，因此固定表的判据、兜底顺序与失败提示必须严格按本规格。

---

## 1. 基准路径

全文用三个记号，其余一律写成它们的相对形式。

| 记号 | Windows | macOS / Linux |
|---|---|---|
| `~` | `%USERPROFILE%` | `$HOME` |
| `%APPDATA%` | `~\AppData\Roaming` | `~/.config` |
| `%LOCALAPPDATA%` | `~\AppData\Local` | `~/.local/share` |

- 路径分隔符在规格里统一写成 `\`；POSIX 实现时换成 `/`。
- **环境变量值必须先展开 `~` 与 `%VAR%` 再做判断**，不要假设调用方给的是绝对路径。
- 路径比较在 Windows 上大小写不敏感。

---

## 2. 固定路径总表

20 个目标，顺序即执行顺序。`配置目录` 是主落点所在；`环境变量` 是覆盖项，优先级高于默认路径。

| # | key | 显示名 | 配置目录（默认） | 环境变量覆盖 |
|---|---|---|---|---|
| 1 | `dsh` | DSH (DeepSeek Harness) | `~\.dsh` | `DSH_HOME` |
| 2 | `wb` | WorkBuddy | 数据 `~\.workbuddy`／安装 `%LOCALAPPDATA%\Programs\WorkBuddy` | — |
| 3 | `wbintl` | WorkBuddy Intl | 数据 `~\.workbuddy-ai`／安装 `%LOCALAPPDATA%\Programs\WorkBuddyAI` | — |
| 4 | `zcode` | ZCode | `~\.zcode` | `ZCODE_HOME`、`ZCODE_CONFIG_DIR` |
| 5 | `codex` | Codex | `~\.codex` | `CODEX_HOME` |
| 6 | `cursor` | Cursor | `~\.cursor` | `CURSOR_HOME` |
| 7 | `claude` | Claude | `~\.claude` | `CLAUDE_CONFIG_DIR` |
| 8 | `antigravity` | Antigravity | `~\.gemini` | `GEMINI_CLI_HOME` |
| 9 | `qwen` | Qwen Code | `~\.qwen` | `QWEN_CONFIG_DIR` |
| 10 | `iflow` | iFlow CLI | `~\.iflow` | `IFLOW_CONFIG_DIR` |
| 11 | `trae` | Trae | `~\.trae`（国际）/ `~\.trae-cn`（国内） | `TRAE_HOME`、`TRAE_CN_HOME` |
| 12 | `codebuddy` | CodeBuddy | `~\.codebuddy` | — |
| 13 | `opencode` | OpenCode | `~\.config\opencode` | `OPENCODE_CONFIG`、`XDG_CONFIG_HOME` |
| 14 | `windsurf` | Windsurf | `~\.codeium\windsurf` | `WINDSURF_HOME`、`CODEIUM_HOME` |
| 15 | `cline` | Cline | `~\Documents\Cline\Rules` | `CLINE_CONFIG_DIR` |
| 16 | `copilot` | Copilot CLI | `~\.copilot` | `COPILOT_HOME` |
| 17 | `kiro` | Kiro | `~\.kiro` | `KIRO_HOME` |
| 18 | `reasonix` | Reasonix | `%APPDATA%\reasonix` | `REASONIX_HOME` / `REASONIX_STATE_HOME` |
| 19 | `traecn` | Trae CN | `~\.trae-cn` | `TRAE_CN_HOME` |
| 20 | `qodercn` | Qoder CN | `~\.qoder-cn` | `QODER_CONFIG_DIR` / `QODER_HOME` |

### 2.1 每个目标的"标志物"

一个候选目录只有在**同时满足**"目录存在"与"含下列任一标志物"时才算命中。只判断目录存在不够——用户可能建过同名空目录。

| key | 标志物（相对配置目录） |
|---|---|
| `codex` | 文件 `config.toml` 或 `AGENTS.md`；目录 `skills\` |
| `cursor` | 文件 `.cursorrules`；目录 `rules\` |
| `claude` | 文件 `CLAUDE.md`；目录 `skills\` |
| `antigravity` | 文件 `GEMINI.md`；目录 `antigravity\` |
| `qwen` | 文件 `QWEN.md` 或 `settings.json` |
| `iflow` | 文件 `IFLOW.md` 或 `settings.json` |
| `trae` | 目录 `rules\` |
| `codebuddy` | 文件 `CODEBUDDY.md` |
| `opencode` | 文件 `AGENTS.md` 或 `opencode.json` |
| `windsurf` | 目录 `memories\` |
| `cline` | 目录存在即可（它的目录本身就是规则库） |
| `copilot` | 文件 `copilot-instructions.md` |
| `kiro` | 目录 `steering\` |
| `reasonix` | `AGENTS.md` / `config.toml` / `sessions\` 任一（`~\.reasonix` 只剩 `locks\`，不算安装） |
| `traecn` | 目录 `rules\` / `user_rules\` / `settings.json` 任一 |
| `qodercn` | 目录 `agents\` / `skills\` / `settings.json` 任一 |
| `zcode` | 目录存在，或 `resources\glm\zcode.cjs` 存在 |
| `wb` / `wbintl` | 见 2.2 |
| `dsh` | 见 2.3 |

### 2.2 WorkBuddy 的两个根

WorkBuddy 是"安装根 + 数据根"双根结构，两个都要定位，缺一个就只能改一半。

**安装根**的标志物是模板文件存在：

```
<安装根>\resources\app.asar.unpacked\resources\templates\workbuddy-prompt.tpl
```

默认候选（按序）：

```
%LOCALAPPDATA%\Programs\WorkBuddy
%LOCALAPPDATA%\Programs\WorkBuddyAI
```

区分两个版本靠一个文件：安装根里**存在** `WorkBuddyAI.exe` → 属于国际版（`wbintl`）；**不存在** → 属于国内版（`wb`）。这条判据必须双向生效，否则两个目标会互相抢同一个目录。

**数据根**：

- `wb`：`~\.workbuddy`，回退 `~\.workbuddy-ai`
- `wbintl`：固定 `~\.workbuddy-ai`

### 2.3 DSH 的特殊性

DSH 没有"一个配置文件"的概念，它的落点是 npm 包树里的 JS 与 YAML。所以安装根不是从产品名推出来的，而是**从标志物反推**：找到含 `@deepseek-ai` 的那一层 `node_modules`，它的上两级就是安装根。

配置根与安装根是两棵独立的树：

```
配置根：~\.dsh            （DSH_HOME 可覆盖）
  └─ profiles\<档名>\cordis.patch.yml      ← 有 cordis.patch.yml 的才是有效档
```

安装根候选（按序）：

```
<显式指定>
<手动记住的>
<上次发现的>
<运行中 DSH 进程的镜像路径上溯>
<盘符>\Users\<用户名>\AppData\Local\Programs\DSH
<盘符>\Program Files\DSH
<盘符>\DSH
```

---

## 3. 逐目标写入落点

`配置目录` 下面的相对路径。**这张表就是"注入"层的全部落点**，多写一个文件都算越界。

### 3.1 标记块型（单文件追加/替换）

| key | 主落点 | 附加入口 |
|---|---|---|
| `codex` | `config.toml`（TOML 顶层键 `model_instructions_file` 指向 `managed-prompts\pojia-persona.md`） | `AGENTS.md` |
| `cursor` | `rules\pojia-inject.mdc` | — |
| `claude` | `CLAUDE.md` | `output-styles\pojia.md`、`settings.json`、状态文件 `pojia-output-style.json` |
| `antigravity` | `GEMINI.md` | `config\rules\pojia.md`（第二层，带 `trigger:` frontmatter） |
| `qwen` | `QWEN.md` | — |
| `iflow` | `IFLOW.md` | — |
| `trae` | `rules\project_rules.md` | — |
| `codebuddy` | `CODEBUDDY.md` | — |
| `opencode` | `AGENTS.md` | — |
| `windsurf` | `memories\global_rules.md` | — |
| `cline` | `pojia-inject.md` | — |
| `copilot` | `copilot-instructions.md` | — |
| `kiro` | `steering\pojia-inject.md` | — |
| `reasonix` | `AGENTS.md` | — |
| `traecn` | `rules\project_rules.md` | — |
| `qodercn` | `agents\purge\qodercn.md` | `skills\purge\SKILL.md`（与主文件同批写；文件本身带 `name: purge` 才认） |

### 3.2 ZCode

```
<配置根>\AGENTS.md                                       ← 整文件覆盖，首行带标记注释
<配置根>\cli\memories\global\memory\pojia-modifier.md     ← 记忆条目（带 YAML frontmatter）
<配置根>\memories\global\memory\pojia-modifier.md         ← 同上，旧布局
<配置根>\skills\                                          ← 技能目录
<配置根>\.agents\skills\                                  ← 技能目录（新布局）
<安装根>\resources\glm\zcode.cjs                          ← 仅 --zpatch 时改，改前 node 语法校验
```

### 3.3 DSH

```
<安装根>\resources\app\                                  ← 解包目标（asar → 目录）
<安装根>\resources\app.asar                              ← 原包，解包后改名保留
<安装根>\resources\app.asar.unpacked\                     ← 解包产物
<安装根>\...\node_modules\@deepseek-ai\dsh-agent-instructions\lib\*.js
<安装根>\...\node_modules\@deepseek-ai\dsh-web-app\presets\*.patch.yml
<配置根>\profiles\<档名>\cordis.patch.yml
```

DSH 的 JS 落点用通配匹配，四条模式按序：

```
dsh-agent-instructions/lib/*.js
dsh-agent-instructions/**/*.js
*/node_modules/@deepseek-ai/dsh-agent-instructions/lib/*.js
*/node_modules/@deepseek-ai/dsh-agent-instructions/**/*.js
```

YAML 落点同理：

```
dsh-web-app/presets/*.patch.yml
*/node_modules/@deepseek-ai/dsh-web-app/presets/*.patch.yml
*/presets/*.patch.yml
*/node_modules/@deepseek-ai/*/presets/*.patch.yml
```

### 3.4 WorkBuddy

```
<安装根>\resources\app.asar.unpacked\resources\**\*.tpl        ← 模板（递归）
<安装根>\resources\app.asar.unpacked\resources\**\*.json       ← 同目录下的配置
<安装根>\resources\app.asar.unpacked\cli\dist\*.js             ← 网页过滤/Ask 模式
<安装根>\resources\app.asar.unpacked\cli\product.json          ← 固定单点
<数据根>\plugins\                                              ← 插件模板（递归）
<数据根>\cache\acc-product-config-v3*.json                     ← 固定单点
```

`<安装根>` 里含 `miora-hidden` 的目录**必须跳过**，那是它自己的备份区，改它等于改备份。

### 3.5 备份后缀

每个目标一个后缀，互不共用（共用会导致两个目标互相把对方的备份当原件）：

| 目标 | 后缀 |
|---|---|
| `dsh` | `.dshpurge.bak` |
| `wb` | `.unlockbak` |
| `wbintl` | `.unlockbak-ai` |
| 其余全部 | `.pojia.bak` |

DSH 的备份不是就地加后缀：如果落点在"打包二进制"目录里（asar 内部），备份统一放到

```
<配置根>\dsh-purge\shim-backups\<原文件名>.<路径摘要前20位>.bak
```

路径摘要 = 规范化绝对路径的 SHA1 十六进制前 20 位。这样同一个文件名在不同包里不会互相覆盖。

---

## 4. 兜底链

**只在固定表里的路径全都不存在时启动**。命中即停。

| 优先级 | 来源 |
|---|---|
| 0 | 调用方显式指定的路径（无效时**不静默跳过**，给提示后再往下走） |
| 1 | 用户手动指定过、且仍然存在的目录 |
| 2 | 上次发现并记住的路径 |
| 3 | 环境变量（见 2 表最后一列） |
| 4 | 平台默认位置（见 2 表，本质就是固定表） |
| 5 | 按盘符有界遍历（必须有时间预算） |
| 6 | 运行中进程的命令行反推 |
| 7 | 注册表 / 包管理器元数据（仅 Windows） |

### 4.1 有界遍历

**预算**：总时间上限 3 秒（DSH 这类深目录可放宽），超时即停并返回已找到的结果。

- 按盘符（Windows `C:`…`Z:`；POSIX `/`、`/home`、`/opt`、`/usr/local`）逐个尝试。
- 只沿**固定表里的相对路径模板**往下拼，不做全盘递归。
- 每层 `isdir` 检查后再进入。
- 结果按可执行文件名缓存，同一进程内不重复实扫。

### 4.2 进程反推

- 命令行必须**同时**命中"包管理器缓存路径（含 `_npx`）"**与**"目标包名"才算数。
- 只判断包名会误判；只判断路径会误判。
- 切路径时注意 Windows 的反斜杠与引号。
- 只取存在的目录。

### 4.3 注册表（仅 Windows）

- 读卸载项里的 `InstallLocation` / `DisplayIcon`。
- 只读，不写。权限不足静默跳过。

### 4.4 结果记录

命中后记两件事：**从哪一步找到的**、**找到的根路径**。用于日志与后续复用。

---

## 5. 进程表

### 5.1 读取

**输出**：`[(进程号, 进程名, 完整命令行)]`，读不到时返回空列表，**永不抛异常**。

- Windows：优先一次性批量取全表，拿不到再退化逐个查。
- POSIX：读 `/proc/*/cmdline`；无 procfs 时用 `ps -eo pid=,comm=,args=`。
- 命令行读不到填空串，不要因为取不到命令行就丢掉整条记录（进程名仍然有用）。
- 结果缓存（几十秒量级）。**结束过进程后必须让缓存失效**，否则后续判断仍按旧名单来。

### 5.2 匹配

- 大小写不敏感。
- Windows 进程名通常带 `.exe`，比较时两种形式都要试。
- 只按进程名匹配，**不按命令行匹配**（命令行里出现同名文件很常见，会误判）。

### 5.3 结束进程

- 先按进程号，失败再按镜像名。
- 结束后重新读表确认；仍有残留如实报告"未能结束"。
- 默认不允许擅自杀进程，必须调用方明确同意。

---

## 6. 手动目录

### 6.1 存储

脚本目录的状态目录下一份 JSON：`{目标短标识: 绝对路径}`。

### 6.2 契约

- 读：文件不存在或损坏 → 返回空表。
- 写：读-改-写，只更新指定目标的键，不覆盖其他键。
- 清除：删掉指定键；表空了可以删文件。
- 手动路径优先级**高于**自动探测，但**低于**调用方显式指定的路径。

---

## 7. 目录选择器

**目的**：自动探测失败时，弹系统目录选择窗口让用户点一个。

### 7.1 平台实现

- Windows：系统文件夹选择对话框（Shell API 或 PowerShell 的 `FolderBrowserDialog`）。
- macOS：`osascript` 调 `choose folder`。
- Linux：`zenity --file-selection --directory`，没有则退化为命令行输入。

### 7.2 契约

- 用户取消 → 返回空串，**不报错**。
- 选中的目录做一次"像不像目标目录"的检查（按 2.1 的标志物），不像就提示但仍接受（用户可能选的是上层目录）。
- 非交互环境（管道、无 TTY、`--quiet`）**不得**弹窗，直接返回空串。
- 弹窗标题与提示要说清"选哪个目录"，不要让用户猜。

### 7.3 用户点了上层目录怎么办

用户经常点 `~`、点 `.codex` 的父目录、点 `C:\Users\xxx`。所以选定后要做一次**归一化**：

1. 基名等于目标的默认目录名（如 `.codex`）→ 直接用它。
2. 基名是它的父级名（如 `steering`）→ 取上一级。
3. 逐层往下试固定表里的相对路径模板，命中即用。
4. 都不中 → 原样返回，交给调用方报错。

---

## 8. 权限判断

- Windows：尝试打开受保护资源或写系统目录，成功即管理员。
- POSIX：`geteuid() == 0`。
- 结果缓存，不重复探测。
- 需要管理员但当前不是 → 明确提示，退出码按失败处理，**不静默降级**。

---

## 9. 失败提示

定位失败时的输出必须包含三件事：

1. 目标显示名；
2. 试过哪些位置（最多列 3 条，多了刷屏）；
3. 下一步怎么做（手动指定参数名 / 点选菜单项）。

只说"未找到"是缺陷。

---

## 10. 验收要点

- 固定表里 20 个路径全部能在没有真实安装的机器上被"枚举"出来（不需要全部命中）。
- 显式指定一个不存在的路径 → 有提示，且不会误用其他目录。
- 手动目录存在时不再触发全盘扫描（可用耗时断言）。
- 进程表读不到（无权限）时，兜底链其余步骤照常工作。
- 结束进程后立刻查询，不能返回旧结果。
- `wb` 与 `wbintl` 永远不会定位到同一个安装根。
- 环境变量指向无效路径时，**回落到固定表**，不是直接失败。
