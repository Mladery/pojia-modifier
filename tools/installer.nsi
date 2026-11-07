; 破甲修改器 —— Windows 安装程序（NSIS 3）
;
; 拿 onedir 产物打一个 setup.exe：解到 %LOCALAPPDATA%\Programs\pojia-ce，
; 建开始菜单项、登记卸载项、可选桌面图标和 PATH。
;
; 同一个 setup 既是安装器也是升级器：第二次运行读到 HKCU 里的 InstallDir，就
; 装回原处、跳过目录页、标题改成「更新」，不产生第二份。
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
;   makensis /DVERSION=8.63 /DSRCDIR=build\dist-onedir\pojia-ce \
;            /DOUTFILE=out\pojia-ce-windows-x64-setup.exe tools\installer.nsi

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
!ifndef SRCDIR
  !define SRCDIR "build\dist-onedir\pojia-ce"
!endif
!ifndef OUTFILE
  !define OUTFILE "out\pojia-ce-windows-x64-setup.exe"
!endif

!define APP_NAME      "破甲修改器"
!define APP_ID        "pojia-ce"
!define APP_EXE       "pojia-ce.exe"
!define APP_PUBLISHER "Mladery"
!define APP_URL       "https://github.com/Mladery/pojia-ce"
!define APP_KEY       "Software\Mladery\pojia-ce"
!define UNINST_KEY    "Software\Microsoft\Windows\CurrentVersion\Uninstall\pojia-ce"

Name "${APP_NAME}"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\${APP_ID}"
InstallDirRegKey HKCU "${APP_KEY}" "InstallDir"
RequestExecutionLevel user
BrandingText "${APP_NAME} ${VERSION}"
ShowInstDetails show
ShowUninstDetails show

; NSIS 要求四段 X.X.X.X。VERSION 是 "8.63"，补两个 0 就是 8.63.0.0。
VIProductVersion "${VERSION}.0.0"
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

; 组件页默认是「左边一窄条列表、右边一块描述」，四条选项在窄条里会被截成
; 「加入 PATH（命令行直接…」。改成列表占满整行、描述挪到下面一行，宽度就够
; 了。代价是描述只剩一条，所以下面每条描述都压到一句话。
!define MUI_COMPONENTSPAGE_SMALLDESC

; MUI2 自己占着 .onGUIInit，改标题要走它的钩子。
!define MUI_CUSTOMFUNCTION_GUIINIT PojiaGuiInit

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

!insertmacro MUI_PAGE_COMPONENTS

; 升级时不让人再选目录：装到别处就是两份，PATH 和卸载项各指一处。
; 这个 define 只作用于紧随其后的那一个页面宏，所以必须贴着 DIRECTORY 放。
!define MUI_PAGE_CUSTOMFUNCTION_PRE DirPagePre
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
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
  ReadRegStr $0 HKCU "${APP_KEY}" "InstallDir"
  ${If} $0 != ""
    StrCpy $INSTDIR $0
    StrCpy $IsUpgrade 1
    ReadRegStr $OldVer HKCU "${APP_KEY}" "Version"
  ${EndIf}

  ; 正在运行时覆盖文件会失败（_internal 里的 dll 被锁着）。静默模式是
  ; --update 拉起来的，那时主进程已经在退出，不查。
  IfSilent done
  nsExec::ExecToStack 'cmd /c tasklist /fi "imagename eq ${APP_EXE}" 2>nul | find /i "${APP_EXE}"'
  Pop $0
  ${If} $0 == 0
    MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION \
      "${APP_NAME} 正在运行。$\r$\n$\r$\n请先退出程序再继续，否则文件会被占用。" \
      IDOK done
    Abort
  ${EndIf}
  done:
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

Function PojiaGuiInit
  ${If} $IsUpgrade == 1
    ${If} $OldVer == ""
      StrCpy $OldVer "旧版"
    ${EndIf}
    System::Call 'user32::SetWindowTextW(i $HWNDPARENT, w "更新 ${APP_NAME}：$OldVer → ${VERSION}")'
  ${EndIf}
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
