; 破甲修改器 —— Windows 安装程序（NSIS 3）
;
; 拿 onedir 产物打一个 setup.exe：解到 %LOCALAPPDATA%\Programs\pojia-modifier，
; 建开始菜单项、登记卸载项、可选桌面图标和 PATH。
;
; 同一个 setup 既是安装器也是升级器：第二次运行读到 HKCU 里的 InstallDir，
; 就装回原处、跳过目录页、不产生第二份。
;
; 「已经装过」这件事要让用户一眼看出来，不能还摆一张「欢迎使用安装程序」的
; 脸。但也不能为这件事在向导之前再加一个弹窗 —— 多一个「确定」就多一次点击，
; 而且那个框跟向导的第一页说的是同一件事。所以改的是这一页自己的字：
; 标题、正文、任务栏、安装进度页、完成页，凡是「安装」的位置，升级时都写
; 「升级」，正文里还带上「从哪个版本升到哪个版本」。整条路上只有向导本身。
;
; 装完把下载的安装包删掉（完成页第二个复选框，默认勾上）。删的是「正在运行的
; 那个 exe」—— Windows 不给删，所以交给一个等两秒的批处理，本进程退了它才动手。
;
; 为什么是 onedir 而不是单文件：单文件版每次启动都要把自身解包到 %TEMP%\
; _MEIxxxxxx，有些机器的安全软件不放行在临时目录建可执行文件，启动即报
; "Could not create temporary directory!"。安装版把 _internal/ 放在 exe 旁边，
; 一步都不碰临时目录。
;
; 为什么装用户目录：RequestExecutionLevel user + $LOCALAPPDATA，全程不要 UAC，
; 装完目录可写 —— 这样 --update 的换装脚本能直接覆盖，不必再提一次权。
;
; 编译（由 tools/build_installer.py 调用）：
;   makensis /DVERSION=1.0 /DSRCDIR=build\dist-onedir\pojia-modifier \
;            /DOUTFILE=out\pojia-modifier-windows-x64-setup.exe tools\installer.nsi

Unicode true
SetCompressor /SOLID lzma
SetCompressorDictSize 32

!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"
!include "StrFunc.nsh"

; 安装段只用 StrStr（查 PATH 里有没有自己）和它对应的卸载版；StrRep 只在
; 卸载时摘 PATH 用得上，所以别声明安装版 —— 不然 makensis 会报「声明了没用到」。
${StrStr}
${UnStrStr}
${UnStrRep}

!ifndef VERSION
  !define VERSION "0.0"
!endif
; 给人看的版本号（1.01.4-beta）。VERSION 只能是纯数字，VIProductVersion 只吃
; 四段数字；而界面上写「升到 1.01.4」会让 beta 用户以为装错了包。
!ifndef DISPLAYVER
  !define DISPLAYVER "${VERSION}"
!endif
!ifndef SRCDIR
  !define SRCDIR "build\dist-onedir\pojia-modifier"
!endif
!ifndef OUTFILE
  !define OUTFILE "out\pojia-modifier-windows-x64-setup.exe"
!endif

!define APP_NAME      "破甲修改器"
!define APP_ID        "pojia-modifier"
!define APP_EXE       "pojia-modifier.exe"
!define APP_PUBLISHER "Mladery"
!define APP_URL       "https://github.com/Mladery/pojia-modifier"
!define APP_KEY       "Software\Mladery\pojia-modifier"
!define UNINST_KEY    "Software\Microsoft\Windows\CurrentVersion\Uninstall\pojia-modifier"

Name "${APP_NAME}"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\${APP_ID}"
InstallDirRegKey HKCU "${APP_KEY}" "InstallDir"
RequestExecutionLevel user
BrandingText "${APP_NAME} ${VERSION}"
ShowInstDetails show
ShowUninstDetails show

; NSIS 只认四段 X.X.X.X，而对外版本号可能带 -beta 或不是四段。
; 归一在 tools/build_installer.py 的 quad_version() 里做，这里直接用。
!ifndef VERSION4
  !define VERSION4 "0.0.0.0"
!endif
VIProductVersion "${VERSION4}"
VIAddVersionKey "ProductName"      "${APP_NAME}"
VIAddVersionKey "FileDescription"  "${APP_NAME} 安装程序"
VIAddVersionKey "FileVersion"      "${VERSION}"
VIAddVersionKey "ProductVersion"   "${VERSION}"
VIAddVersionKey "CompanyName"      "${APP_PUBLISHER}"
VIAddVersionKey "LegalCopyright"   "${APP_PUBLISHER}"

Var IsUpgrade
Var OldVer
Var DoRevert

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "立即启动 ${APP_NAME}"
!define MUI_FINISHPAGE_LINK "项目主页"
!define MUI_FINISHPAGE_LINK_LOCATION "${APP_URL}"

; 完成页的第二个复选框：把这个安装包删掉。
; MUI 只给两个复选框位置（RUN 和 SHOWREADME），没有「自定义复选框」这种插槽，
; 所以借 SHOWREADME 的位置挂自己的回调 —— 文案和动作都是自己的，跟 readme 无关。
;
; 默认勾上：不定义 _NOTCHECKED 就是勾选态。装完还留着几十兆的 setup.exe，
; 大多数人不会自己去删，攒几个版本就是一堆同名文件。
!define MUI_FINISHPAGE_SHOWREADME "$EXEPATH"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "删除这个安装包（已经装好了，留着占地方）"
!define MUI_FINISHPAGE_SHOWREADME_FUNCTION DeleteSetup

; 组件页默认是「左边一窄条列表、右边一块描述」，四条选项在窄条里会被截成
; 「加入 PATH（命令行直接…」。改成列表占满整行、描述挪到下面一行，宽度就够
; 了。代价是描述只剩一条，所以下面每条描述都压到一句话。
!define MUI_COMPONENTSPAGE_SMALLDESC

; MUI2 自己占着 .onGUIInit。这里不改标题 —— MUI 在这个钩子之后还会按
; $(^SetupCaption) 重写一次，写在钩子里会被立刻盖掉。标题统一放到每页的
; SHOW 回调里改（那时窗口已经在，也没人再改它）。

; 欢迎页照旧出，但升级时这一页的文字要换成「升级」。
;
; MUI 的标题和正文是编译期定死的字符串，只有拿到控件句柄之后才改得动 ——
; 所以挂 SHOW 回调，在对话框建好、还没显示的那一瞬间把两个标签重写一遍。
; 这样不用自己画一页，也不会在向导前面多出任何弹窗。
!define MUI_PAGE_CUSTOMFUNCTION_SHOW WelcomePageShow
!insertmacro MUI_PAGE_WELCOME

; 协议页。正文是 docs/免责声明.md 转成的纯文本，由 build_installer.py 生成后
; 用 /DLICENSE= 传进来 —— 条款只有那一份源文件，改 md 就等于改安装包里的协议。
;
; 必须勾了才能往下走：复选框是这一步的全部意义，不加等于只是给人看了一眼。
;
; 上下那两句提示都压到一行。MUI 给它们留的是固定高度，写长了会折行、把协议框
; 挤小 —— 这里每多一行，正文就少一行。
!define MUI_LICENSEPAGE_CHECKBOX
!define MUI_LICENSEPAGE_CHECKBOX_TEXT "我已阅读并同意上述免责声明"
!define MUI_LICENSEPAGE_TEXT_TOP "不同意就点「取消」。"
!define MUI_LICENSEPAGE_TEXT_BOTTOM "勾选后才能继续。"
!define MUI_LICENSEPAGE_BUTTON "同意并继续"
!define MUI_PAGE_HEADER_TEXT "许可协议"
!define MUI_PAGE_HEADER_SUBTEXT "读一遍再决定"
!define MUI_PAGE_CUSTOMFUNCTION_PRE LicensePagePre
!insertmacro MUI_PAGE_LICENSE "${LICENSE}"

; 组件页也要改标题：NSIS 每建一页都按「Name + ^SetupCaption」重写一次窗口标题，
; 上一页改过的会被盖回去。
!define MUI_PAGE_CUSTOMFUNCTION_SHOW ComponentsPageShow
!insertmacro MUI_PAGE_COMPONENTS

; 升级时不让人再选目录：装到别处就是两份，PATH 和卸载项各指一处。
; 这个 define 只作用于紧随其后的那一个页面宏，所以必须贴着 DIRECTORY 放。
!define MUI_PAGE_CUSTOMFUNCTION_PRE DirPagePre
!insertmacro MUI_PAGE_DIRECTORY

; 进度页的抬头默认是「正在安装 破甲修改器」。升级时改成「正在升级」——
; 这一页停留时间最长，抬头写着安装，前面几页就白改了。
!define MUI_PAGE_CUSTOMFUNCTION_SHOW InstFilesShow
!insertmacro MUI_PAGE_INSTFILES

; 完成页的标题和正文按「装」还是「更新」现改 —— MUI 的这两段文字是编译期
; 定死的，只有拿到控件句柄之后才能换。不换的话，升级完还写着「安装完成」。
!define MUI_PAGE_CUSTOMFUNCTION_SHOW FinishPageShow
!insertmacro MUI_PAGE_FINISH

; 还原的询问放在「确认卸载」之后：先问要不要卸，再问卸之前要不要把改动退回去。
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE un.AskRevert
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

; ---- 安装 -------------------------------------------------------------------

Section "主程序（必需）" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  ; 整个 onedir 树原样铺进来：_internal/ 必须和 exe 同级。升级时同名覆盖，
  ; 用户数据（状态/、备份/）不在这个树里，不受影响。
  File /r "${SRCDIR}\*.*"

  ; 程序靠这条判断「我是装出来的」：HERE 等于这里，也是绿色版没有的凭据。
  ; 升级时 --update 据此改下 setup.exe 走静默覆盖，而不是把自己替换成裸 exe。
  WriteRegStr HKCU "${APP_KEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${APP_KEY}" "Version" "${VERSION}"

  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; 应用和功能里的独立一项。NoModify/NoRepair：没有"修改"和"修复"按钮，
  ; 点它只会进卸载流程 —— 这个程序没有可勾的组件需要事后改。
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayName"     "${APP_NAME}"
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayVersion"  "${VERSION}"
  WriteRegStr   HKCU "${UNINST_KEY}" "Publisher"       "${APP_PUBLISHER}"
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayIcon"     "$INSTDIR\${APP_EXE}"
  WriteRegStr   HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKCU "${UNINST_KEY}" "URLInfoAbout"    "${APP_URL}"
  WriteRegStr   HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr   HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${UNINST_KEY}" "EstimatedSize" "$0"
SectionEnd

; 默认勾选按「第一次装电脑的人会不会用」来排：桌面图标看得见，双击就开；
; PATH 是给命令行用户准备的，让不明就里的人勾上，只会往环境变量里塞一条
; 他看不懂、也不知道怎么删的路径。开始菜单保持勾选 —— 那是卸载入口的常规位置。
Section "开始菜单项" SecMenu
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortCut  "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
  ; 卸载单独一项，和启动项并列 —— 不用去控制面板翻。
  CreateShortCut  "$SMPROGRAMS\${APP_NAME}\卸载 ${APP_NAME}.lnk" "$INSTDIR\uninstall.exe"
SectionEnd

Section "桌面快捷方式" SecDesktop
  CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
SectionEnd

Section /o "加入 PATH" SecPath
  ; 只动 HKCU\Environment，不碰系统 PATH。已经在了就不重复追加。
  ReadRegStr $0 HKCU "Environment" "PATH"
  ${StrStr} $1 "$0" "$INSTDIR"
  ${If} $1 == ""
    ${If} $0 == ""
      WriteRegStr HKCU "Environment" "PATH" "$INSTDIR"
    ${Else}
      WriteRegStr HKCU "Environment" "PATH" "$0;$INSTDIR"
    ${EndIf}
    ; 通知资源管理器环境变量变了，否则新开的 cmd 读到的还是旧 PATH。
    System::Call 'user32::SendMessageW(i 0xffff, i 0x001A, i 0, w "Environment")'
  ${EndIf}
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain}    "程序本体。"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMenu}    "开始菜单里放启动和卸载两项。"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "在桌面放一个快捷方式。"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecPath}    "写进当前用户 PATH，之后在任意终端直接敲 ${APP_ID}。"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Function .onInit
  ; 已经装过就装回原处：同一个 setup，第一次是安装，第二次就是更新。
  ;
  ; 判定不能只看注册表：卸载程序被强删、注册表被清理工具扫掉，程序目录还在，
  ; 那也算「已装」—— 不然会在旁边再摊一份，PATH 和卸载项指哪个都说不清。
  ReadRegStr $0 HKCU "${APP_KEY}" "InstallDir"
  ${If} $0 == ""
    ${If} ${FileExists} "$LOCALAPPDATA\Programs\${APP_ID}\${APP_EXE}"
      StrCpy $0 "$LOCALAPPDATA\Programs\${APP_ID}"
    ${EndIf}
  ${EndIf}

  ${If} $0 != ""
    StrCpy $INSTDIR $0
    ; 目录在、exe 不在 = 上次没卸干净。照常装到这儿，但不算「更新」——
    ; 没有可更新的东西，也就别弹「正在运行」之外的提示。
    ${If} ${FileExists} "$0\${APP_EXE}"
      StrCpy $IsUpgrade 1
      ReadRegStr $OldVer HKCU "${APP_KEY}" "Version"
    ${EndIf}
  ${EndIf}

  ; 正在运行时覆盖文件会失败（_internal 里的 dll 被锁着）。静默模式是
  ; --update 拉起来的，那时主进程已经在退出，不查。
  ;
  ; 不用 `tasklist | find`：从 Git Bash 拉起来的安装程序，PATH 里排在前面的
  ; find.exe 是 GNU 的，`find /i "x"` 会被它当成「从 /i 开始遍历」——整个盘扫
  ; 一遍，安装程序在开装前就地卡住。这里直接调 tasklist 取输出，再用 StrStr
  ; 找进程名：没有管道，也就不需要 cmd /c 去背那套引号规则。
  IfSilent on_init_done
  nsExec::ExecToStack '"$SYSDIR\tasklist.exe" /nh /fi "imagename eq ${APP_EXE}"'
  Pop $0
  Pop $1
  ${StrStr} $2 "$1" "${APP_EXE}"
  ${If} $2 != ""
    MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION \
      "${APP_NAME} 正在运行。$\r$\n$\r$\n请先退出程序再继续，否则文件会被占用。" \
      IDOK on_init_done
    Abort
  ${EndIf}

  on_init_done:
  ; 注册表被清理工具扫过时读不到旧版本号，欢迎页正文得有个说法。
  ${If} $IsUpgrade == 1
  ${AndIf} $OldVer == ""
    StrCpy $OldVer "旧版"
  ${EndIf}
FunctionEnd

Function SetUpgradeCaption
  ; 窗口标题（任务栏上那行）。只在升级时改：安装时 MUI 给的
  ; 「破甲修改器 安装」是对的。
  ${If} $IsUpgrade == 1
    System::Call 'user32::SetWindowTextW(i $HWNDPARENT, w "${APP_NAME} 升级")'
  ${EndIf}
FunctionEnd

Function WelcomePageShow
  Call SetUpgradeCaption
  ; 升级时把这一页的字改成「升级」。标签是 MUI 建的，句柄就摆在
  ; $mui.WelcomePage.Title / .Text 里，SHOW 回调运行时已经有效。
  ;
  ; 正文压到三小段：MUI 给这块文字留的高度是固定的，写长了会被掐掉下半截。
  ${If} $IsUpgrade != 1
    Return
  ${EndIf}
  SendMessage $mui.WelcomePage.Title ${WM_SETTEXT} 0 "STR:欢迎使用 ${APP_NAME} 升级程序"
  SendMessage $mui.WelcomePage.Text ${WM_SETTEXT} 0 "STR:已检测到 $OldVer，将就地升级到 ${DISPLAYVER}。$\r$\n备份、状态和你的设置都留在原处。$\r$\n$\r$\n升级前请先关闭正在运行的 ${APP_NAME}，否则文件会被占用。$\r$\n$\r$\n点击 [下一步(N)] 继续。"
FunctionEnd

Function ComponentsPageShow
  Call SetUpgradeCaption
FunctionEnd

Function InstFilesShow
  Call SetUpgradeCaption
  ; 进度页抬头默认写「正在安装」。这一页停得最久，不换掉，前面几页就白换了。
  ${If} $IsUpgrade != 1
    Return
  ${EndIf}
  GetDlgItem $0 $HWNDPARENT 1037
  ${If} $0 != 0
    SendMessage $0 ${WM_SETTEXT} 0 "STR:正在升级 ${APP_NAME}"
  ${EndIf}
  GetDlgItem $0 $HWNDPARENT 1038
  ${If} $0 != 0
    SendMessage $0 ${WM_SETTEXT} 0 "STR:覆盖旧版文件，备份和设置都保留"
  ${EndIf}
FunctionEnd

Function LicensePagePre
  ; 升级不重放协议。条款没变，用户早就同意过；每次更新都逼一遍，只会让人
  ; 养成闭眼点「下一步」的习惯 —— 那反而让协议变得没有意义。
  ${If} $IsUpgrade == 1
    Abort
  ${EndIf}
FunctionEnd

Function DirPagePre
  ; 升级不给改目录，直接跳过这一页。
  ${If} $IsUpgrade == 1
    Abort
  ${EndIf}
FunctionEnd

Function FinishPageShow
  Call SetUpgradeCaption
  ; 升级完还写着「安装完成」，跟欢迎页是同一个毛病：把升级说成安装。
  ${If} $IsUpgrade == 1
    SendMessage $mui.FinishPage.Title ${WM_SETTEXT} 0 "STR:升级完成"
    SendMessage $mui.FinishPage.Text ${WM_SETTEXT} 0 "STR:已升级到 ${DISPLAYVER}。备份、状态和你的设置都在原处。"
  ${EndIf}
FunctionEnd

Function DeleteSetup
  ; 删掉「正在运行的自己」。Windows 不给删已加载的 exe，所以写一个守在旁边的
  ; 批处理：它先等两秒，等本进程退出后再动手；删不掉就再等，最多三十次
  ; （杀毒软件刚扫完的那几十秒会把文件锁住）。批处理自己最后把自己也删掉。
  ;
  ; 静默安装也从这里走 —— 那条路没有完成页，也就没有那个复选框。
  ${IfNot} ${FileExists} "$EXEPATH"
    Return
  ${EndIf}
  StrCpy $0 "$TEMP\pojia-del-setup.cmd"
  ClearErrors
  FileOpen $1 "$0" w
  ${If} ${Errors}
    Return
  ${EndIf}
  FileWrite $1 "@echo off$\r$\n"
  FileWrite $1 "set TARGET=$EXEPATH$\r$\n"
  FileWrite $1 "for /l %%i in (1,1,30) do ($\r$\n"
  FileWrite $1 '  del /f /q "%TARGET%" >nul 2>&1$\r$\n'
  FileWrite $1 '  if not exist "%TARGET%" goto done$\r$\n'
  FileWrite $1 "  ping -n 2 127.0.0.1 >nul$\r$\n"
  FileWrite $1 ")$\r$\n"
  FileWrite $1 ":done$\r$\n"
  FileWrite $1 'del /f /q "%~f0" >nul 2>&1$\r$\n'
  FileClose $1
  ExecShell "" "$0" SW_HIDE
FunctionEnd

Function .onInstSuccess
  ; 非静默的装完由完成页那个复选框决定删不删。
  ;
  ; 静默安装不替人删自己：/S 谁都会敲 —— 批量部署、CI、脚本里都可能来一发，
  ; 把人家脚本里的 setup.exe 吃掉是越界。只有程序自己的 --update 拉起来的那次
  ; 才带 /POJIA_SELFDEL，才删。
  IfSilent try_selfdel
  Return

  try_selfdel:
  ${GetParameters} $1
  ${StrStr} $0 "$1" "/POJIA_SELFDEL"
  ${If} $0 == ""
    Return
  ${EndIf}
  Call DeleteSetup
FunctionEnd

; ---- 卸载 -------------------------------------------------------------------

Function un.onInit
  StrCpy $DoRevert 0
FunctionEnd

Function un.AskRevert
  ; 静默卸载（/S）不弹窗，默认不还原 —— 安静的卸载不该顺手改别人的软件。
  IfSilent unAskDone
  ${IfNot} ${FileExists} "$INSTDIR\${APP_EXE}"
    Goto unAskDone
  ${EndIf}
  MessageBox MB_YESNO|MB_ICONQUESTION \
    "卸载前要不要把破甲改过的文件还原回去？$\r$\n$\r$\n\
     选「是」：对 DSH / WorkBuddy 等目标执行还原（从备份恢复原文件）。$\r$\n\
     选「否」：只删程序，目标软件保持当前状态。$\r$\n$\r$\n\
     备份和状态目录不会被删除，之后仍可手动还原。" \
    IDNO unAskDone
  StrCpy $DoRevert 1
  unAskDone:
FunctionEnd

Section "Uninstall"
  ; 先还原，再删程序 —— 顺序反了就找不到 exe 了。
  ${If} $DoRevert == 1
    ${If} ${FileExists} "$INSTDIR\${APP_EXE}"
      DetailPrint "正在还原目标软件…"
      nsExec::ExecToStack '"$INSTDIR\${APP_EXE}" --revert --yes'
      Pop $0
      ${If} $0 == 0
        DetailPrint "还原完成"
      ${Else}
        DetailPrint "还原未全部成功（退出码 $0），程序仍会继续卸载"
      ${EndIf}
    ${Else}
      DetailPrint "程序文件已不在，跳过还原"
    ${EndIf}
  ${EndIf}

  ; RMDir /r 只在该目录确实是我们的安装目录时才执行 —— 注册表被改坏时
  ; 一个手滑就是删掉别人的目录。
  ${If} ${FileExists} "$INSTDIR\${APP_EXE}"
  ${AndIf} ${FileExists} "$INSTDIR\uninstall.exe"
    Delete "$INSTDIR\${APP_EXE}"
    RMDir /r "$INSTDIR\_internal"
    Delete "$INSTDIR\uninstall.exe"
    Delete "$INSTDIR\*.*"
    RMDir "$INSTDIR"
    ; 用户数据（状态/、备份/）不跟着卸 —— 里面是用户自己的快照和还原点。
    ${If} ${FileExists} "$INSTDIR\状态\*.*"
      DetailPrint "保留用户数据：$INSTDIR\状态"
    ${EndIf}
  ${Else}
    DetailPrint "安装目录已不是预期结构，跳过删除：$INSTDIR"
  ${EndIf}

  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\卸载 ${APP_NAME}.lnk"
  RMDir  "$SMPROGRAMS\${APP_NAME}"
  Delete "$DESKTOP\${APP_NAME}.lnk"

  ; 从 PATH 里摘掉自己。摘完是空串就把值删了，别留一个空的 PATH。
  ReadRegStr $0 HKCU "Environment" "PATH"
  ${UnStrStr} $1 "$0" "$INSTDIR"
  ${If} $1 != ""
    ${UnStrRep} $0 "$0" ";$INSTDIR" ""
    ${UnStrRep} $0 "$0" "$INSTDIR;" ""
    ${UnStrRep} $0 "$0" "$INSTDIR" ""
    ${If} $0 == ""
      DeleteRegValue HKCU "Environment" "PATH"
    ${Else}
      WriteRegStr HKCU "Environment" "PATH" "$0"
    ${EndIf}
    System::Call 'user32::SendMessageW(i 0xffff, i 0x001A, i 0, w "Environment")'
  ${EndIf}

  DeleteRegKey HKCU "${UNINST_KEY}"
  DeleteRegKey HKCU "${APP_KEY}"
SectionEnd
