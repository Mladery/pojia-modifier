# POJIA 1.0 · 独立重写版

按 `docs/spec/` 六份行为规格从零写的一份实现。**没有读过 `src/pojia.py` 或任何既有实现**，
只依据规格文本与 `tests/contract/` 的契约用例。

- 入口：`src/pojia.py`（单文件，4119 行，零第三方依赖，Python 3.8+）
- 契约测试：`tests/contract/`（从主仓复制，`conftest.py` 的 `CORE` 自动指向本目录的 `src/pojia.py`）
- 自检脚本：`tools/selftest.py`（17 个目标的往返验证，不属于交付物）

## 跑起来

```bash
# 契约测试（21 条）
python -m pytest tests/contract -q --basetemp=/tmp/pt

# 17 目标往返自检
python tools/selftest.py

# 本机只读体检 / 预演
python src/pojia.py --status
python src/pojia.py --check
python src/pojia.py --apply --dry-run --yes
```

## 验收结果

| 项 | 结果 |
|---|---|
| 契约测试 C1–C10 + 标记稳定性 + 无残留 | **21 / 21 通过** |
| 17 个目标 apply → apply（字节不变）→ revert（字节还原） | **17 / 17 通过** |
| 只读动作（`--status` / `--check` / `--persona-*`）零落盘 | 通过（整目录指纹比对） |
| 预演零落盘 | 通过（含日志、护照、备份） |
| TOML 键落顶层、撤回逐字节 | 通过（含多张表） |
| 带注释/尾逗号的 JSON 注入，其余字节不动 | 通过 |
| BOM / CRLF / 无末尾换行 / 中文 四种边界 | 通过 |

## 分层对照

| 规格 | 实现位置 |
|---|---|
| `00` 不变量、数据模型、错误约定 | 全文；`Res` / `Ctx` / 常量区 |
| `10` 宽容读 / 严格读 / 原子写 / 行尾 / 哈希 / JSON 扫描 / 备份 / 清单 | §1–§3 |
| `20` 固定路径表、标志物、兜底链、进程表、选择器、权限 | §5 |
| `30` 文本组装、三种注入形态、状态判定、云记忆 | §4、§6 |
| `40` 目标契约、17 目标、DSH / WorkBuddy / ZCode 特殊流程 | §7 |
| `50` 护照、体检、计划任务、命令行、菜单、编排 | §3、§8–§12 |

## 规格里那十个坑，逐条对应

1. **先删后判** —— 整段替换走「先算新内容、与现内容比对、相同就返回」，`apply_one` 里没有任何
   "先清空再判断"的分支。
2. **TOML 键被吞进最后一张表** —— `toml_first_table()` 按「括号深度 0 且行首为 `[`」找表头，
   字符串里的 `[` 会被跳过；键插在表头之前的顶层区域。
3. **读失败当空文件** —— `read_or_default()` 用 `None` 表示"存在但读不动"，调用方直接失败，
   绝不拿空串覆盖。
4. **预演/只读写日志** —— `log_flush()` 与 `save_json()` 在 `OPT["dry"]` 下直接返回；
   只读动作全程不碰 `log_line`。
5. **护照存带后缀的版本号** —— `VERSION = "1.0"`，`DISPLAY_VERSION` 只用于界面。
6. **asar unpacked 条目缺失静默跳过** —— `unpack_asar()` 回落数据区读，读不到计入 `missing`
   并让上层拒绝后续改名。
7. **杀进程后缓存不失效** —— `kill_processes()` 结束进程后强制 `invalidate_process_cache()` 并重查。
8. **命名撞车** —— 写入口统一叫 `write_text` / `atomic_write` / `read_strict`，不覆盖内建名。
9. **行尾先加后归** —— `to_eol()` 一律先把 `\r\n`、`\r` 归一成 `\n` 再转目标行尾，二次写入不变长。
10. **BOM 跟着还原路径走** —— `restore_backup()` 走 `read_bytes` + 字节写，不解码不编码。

## 与规格的取舍（诚实清单）

规格没写死、或写死了但实现上必须做判断的地方，都在这里：

1. **护照位置**：规格说"目标专属目录下"，实现取 `<目标根>/.pojia/passport.json`；
   撤回成功后连目录一起删（所以撤回后 `--status` 会显示"没有护照"，这是预期）。
2. **护照多了两个字段** `kinds` 与 `created`：前者记录每个文件用的是哪种写入形态，后者记录
   哪些文件是本工具新建的。没有它们，撤回时无法区分"该删块"和"该删键"，也判断不出
   "空文件要不要删"。读取侧对未知字段全部忽略。
3. **ZCode 默认不碰 `zcode.cjs`**：按 `20-locate` 3.2，只有 `--zpatch` 才改；改之前做
   `node --check`（没有 node 时退化为括号配对检查），不通过就回滚。
4. **DSH 保险丝只读**：`--dsh-mode` 接受并影响报告，但**不做二进制补丁**——改 Electron
   fuses 需要对可执行文件做定长改写，风险与收益不成比例，且规格只要求"能判断、能还原"。
5. **云记忆路径**：规格只给了文件格式没给路径，实现取 `<数据根>/memory/account-memory.md`。
6. **人格片段库**：README 的边界里写明不在范围，这里只留三个最小片段 + `--persona-name`，
   `--persona` 走外部文件。
7. **`--guard` / `--git-bash` / `--resign`**：同上，明确回一句"不在本实现范围内"，不假装做了。
8. **WorkBuddy 模板过滤**：规格说递归匹配 `**/*.tpl`，但真实机器上 PPT 技能的
   `templates/**.tpl` 也是 `.tpl`。直接改会毁掉 Office 模板，所以加了"必须是 UTF-8 文本且带
   提示词特征（`{{`、`You are`、`你是` 等）或文件名在白名单里"这一层。本机预演从 683 个
   降到 23 个，剩下的全是真提示词模板。
9. **契约测试改了一处**：`test_revert_leaves_no_residue` 原本带 `xfail(strict=True)`，
   用例自己的说明写着"新实现清了残留后会 xpass，把标记删掉即可"。本实现确实清了
   （`settings.json` 与 `output-styles/` 在撤回时一并删除），所以按说明删掉了 xfail 标记。

## 边界

不在范围内、保持不做的：图形界面以外的安装包与自更新、macOS 签名重签、Git Bash 接管、
人格片段库、运行时守卫、取证与免责声明。`--gui` 用 tkinter 做了最小可用版（无 tkinter 时
退回菜单）。
