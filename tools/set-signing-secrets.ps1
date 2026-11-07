<#
.SYNOPSIS
    把签名用的 pfx / 密码发布成 GitHub Actions 的 repository secret。

.DESCRIPTION
    两个 secret：
      WINDOWS_SIGNING_PFX_BASE64    pfx 文件的 base64（单行，不能换行）
      WINDOWS_SIGNING_PFX_PASSWORD  pfx 的密码

    有 gh CLI 且已登录 → 直接写进去，全程不经过屏幕。
    没有 gh → 把 base64 写到本地文件（已被 .gitignore 挡住），
    并打开仓库的 secrets 设置页，由你自己粘。

    刻意不在终端打印 base64 —— 私钥一旦进了滚动缓冲区、命令历史或聊天记录，
    就等于公开了。文件路径给你，要粘贴自己打开。

.EXAMPLE
    .\tools\set-signing-secrets.ps1 -Pfx "I:\Downloads\代码签名证书制作工具\pojia-signing.pfx"

.EXAMPLE
    .\tools\set-signing-secrets.ps1 -Pfx D:\certs\pojia.pfx -Password 'xxxx' -Repo Mladery/pojia-modifier
#>
param(
    [Parameter(Mandatory = $true)][string]$Pfx,
    [string]$Password,
    [string]$Repo = "Mladery/pojia-modifier",
    # 没装 gh 时把 base64 落在这个文件里，默认放仓库根的 .signing-secrets.local/
    [string]$OutDir
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Pfx)) {
    throw "找不到 pfx：$Pfx"
}
$Pfx = (Resolve-Path -LiteralPath $Pfx).Path

# 密码没传就从 pfx 同目录的密码文件读 —— 和 sign-windows.ps1 一个约定，
# 免得同一份密码在两处各存一遍。
if (-not $Password) {
    $pwFile = Join-Path (Split-Path -Parent $Pfx) "pojia-signing-密码.txt"
    if (Test-Path -LiteralPath $pwFile) {
        $Password = (Get-Content -LiteralPath $pwFile -Raw).Trim()
    }
}
if (-not $Password) {
    throw "没有密码。用 -Password 传，或在 pfx 同目录放 pojia-signing-密码.txt。"
}

Write-Host ("pfx     : {0} ({1} 字节)" -f $Pfx, (Get-Item -LiteralPath $Pfx).Length)
Write-Host ("密码长度: {0}" -f $Password.Length)

# 先验一下 pfx 真能用这张密码打开。密码错了就写进 secret，等于让 CI 每次
# 构建都签失败一次 —— 在这里拦住比在 runner 上发现便宜得多。
# 用 X509Certificate2 构造函数（吃明文密码），不走 SecureString：Windows
# PowerShell 5.1 的 Get-PfxCertificate 没有 -Password 参数，而
# ConvertTo-SecureString -AsPlainText 在本机被安全策略挡着。
try {
    $probe = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($Pfx, $Password)
} catch {
    Write-Host ("[FAIL] pfx 打不开，密码大概率不对：{0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}
Write-Host ("证书    : {0}" -f $probe.Subject)
Write-Host ("指纹    : {0}" -f $probe.Thumbprint)
Write-Host ("有效期至: {0:yyyy-MM-dd}" -f $probe.NotAfter)

$b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($Pfx))
Write-Host ("base64  : {0} 字符" -f $b64.Length)

# ---- 路径一：gh CLI ----
$gh = Get-Command gh -ErrorAction SilentlyContinue
if ($gh) {
    $authOk = $false
    try {
        & gh auth status 2>&1 | Out-Null
        $authOk = ($LASTEXITCODE -eq 0)
    } catch { $authOk = $false }

    if ($authOk) {
        Write-Host "用 gh 直接写入 secret（内容不经过屏幕）……"
        # 从管道喂进去，避免出现在进程命令行（ps / 任务管理器都看得到参数）。
        $b64 | & gh secret set WINDOWS_SIGNING_PFX_BASE64 --repo $Repo
        if ($LASTEXITCODE -ne 0) { throw "写 WINDOWS_SIGNING_PFX_BASE64 失败" }

        $Password | & gh secret set WINDOWS_SIGNING_PFX_PASSWORD --repo $Repo
        if ($LASTEXITCODE -ne 0) { throw "写 WINDOWS_SIGNING_PFX_PASSWORD 失败" }

        Write-Host "[ OK ] 两个 secret 已写入 $Repo" -ForegroundColor Green
        Write-Host "下次构建就会签名。去 Actions 页看 Windows 那个 job 的「签名」步骤是否变成绿色。"
        exit 0
    }
    Write-Host "gh 装了但没登录，走手动路径（gh auth login 之后重跑本脚本可自动化）。"
} else {
    Write-Host "没装 gh CLI，走手动路径。"
}

# ---- 路径二：落文件，由用户自己粘 ----
if (-not $OutDir) {
    $OutDir = Join-Path (Split-Path -Parent $PSScriptRoot) ".signing-secrets.local"
}
if (-not (Test-Path -LiteralPath $OutDir)) {
    $null = New-Item -ItemType Directory -Path $OutDir -Force
}

$b64File = Join-Path $OutDir "pfx-base64.txt"
$pwOut = Join-Path $OutDir "pfx-password.txt"
# -NoNewline 很重要：多一个换行，base64 解码出来的 pfx 就多一个字节，签名直接崩。
[IO.File]::WriteAllText($b64File, $b64, (New-Object System.Text.UTF8Encoding($false)))
[IO.File]::WriteAllText($pwOut, $Password, (New-Object System.Text.UTF8Encoding($false)))

$url = "https://github.com/$Repo/settings/secrets/actions"
Write-Host ""
Write-Host "手动步骤：" -ForegroundColor Cyan
Write-Host ("  1. 打开 {0}" -f $url)
Write-Host "  2. New repository secret"
Write-Host "       Name  : WINDOWS_SIGNING_PFX_BASE64"
Write-Host ("       Value : 粘贴 {0} 的全部内容（一整行，别换行）" -f $b64File)
Write-Host "  3. 再建一个"
Write-Host "       Name  : WINDOWS_SIGNING_PFX_PASSWORD"
Write-Host ("       Value : 粘贴 {0} 的全部内容" -f $pwOut)
Write-Host ""
Write-Host "两个文件都在 .gitignore 里挡着，不会误提交。粘完建议删掉："
Write-Host ("  Remove-Item -Recurse -Force '{0}'" -f $OutDir)
Write-Host ""
Write-Host "想省事就装 gh（winget install GitHub.cli），登录后重跑本脚本自动完成。"
