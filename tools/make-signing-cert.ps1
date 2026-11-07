# 生成一张可用的 Windows 代码签名证书（自签）
#
# 为什么不用 makecert + cert2spc：那套 1998 年的工具只能出 MD5/SHA1 签名的
# 1024 位证书，现代 Windows 直接不认 —— signtool 会报 "No certificates were
# found that met all the given criteria"，因为它连选都不会选这张证书。
# New-SelfSignedCertificate 能出 SHA-256 + RSA 4096 + 正确的 CodeSigning EKU。
#
# 用法：
#   .\make-signing-cert.ps1                                   # 只生成，导出到当前目录
#   .\make-signing-cert.ps1 -OutDir D:\certs -Trust            # 顺带信任（本机免"未知发布者"）
#   .\make-signing-cert.ps1 -Subject "CN=YourName" -Years 5
#
# 生成物：
#   pojia-signing.pfx   含私钥，用来签名。**绝不能提交到仓库，也别外发。**
#   pojia-signing.cer   只含公钥，用来让别的机器信任你。
#   pojia-signing-密码.txt  pfx 密码（本机保存）
param(
    [string]$Subject = "CN=Mladery, O=Mladery CE, C=CN",
    [string]$OutDir = ".",
    [int]$Years = 10,
    [switch]$Trust
)

$ErrorActionPreference = "Stop"
$OutDir = (Resolve-Path -LiteralPath (New-Item -ItemType Directory -Force -Path $OutDir)).Path

$cert = New-SelfSignedCertificate `
    -Type CodeSigningCert `
    -Subject $Subject `
    -KeyAlgorithm RSA `
    -KeyLength 4096 `
    -HashAlgorithm SHA256 `
    -KeyExportPolicy Exportable `
    -NotAfter (Get-Date).AddYears($Years) `
    -CertStoreLocation Cert:\CurrentUser\My

# 密码：随机 24 位。用 X509Certificate2.Export 直接吃明文字符串，
# 不走 SecureString（那条路在非交互环境里容易卡在弹窗上）。
$chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
$password = -join (1..24 | ForEach-Object { $chars[(Get-Random -Maximum $chars.Length)] })

$pfx = Join-Path $OutDir "pojia-signing.pfx"
$cer = Join-Path $OutDir "pojia-signing.cer"
$txt = Join-Path $OutDir "pojia-signing-密码.txt"

[IO.File]::WriteAllBytes($pfx, $cert.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Pfx, $password))
[IO.File]::WriteAllBytes($cer, $cert.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert))
[IO.File]::WriteAllText($txt, $password, (New-Object System.Text.UTF8Encoding($false)))

Write-Host ""
Write-Host "证书已生成" -ForegroundColor Green
Write-Host ("  主题      : " + $cert.Subject)
Write-Host ("  指纹      : " + $cert.Thumbprint)
Write-Host ("  有效期至  : " + $cert.NotAfter)
Write-Host ("  PFX       : " + $pfx)
Write-Host ("  CER       : " + $cer)
Write-Host ("  PFX 密码  : " + $password + "   （存在 " + $txt + "）")
Write-Host ""
Write-Host "签名：" -ForegroundColor Cyan
Write-Host ("  signtool sign /f `"$pfx`" /p <密码> /fd sha256 /tr http://timestamp.digicert.com /td sha256 你的.exe")
Write-Host ""

if ($Trust) {
    $cerObj = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($cer)
    foreach ($name in @("Root", "TrustedPublisher")) {
        $store = [System.Security.Cryptography.X509Certificates.X509Store]::new($name, "CurrentUser")
        $store.Open("ReadWrite")
        $store.Add($cerObj)
        $store.Close()
        Write-Host ("  已加入 CurrentUser\$name") -ForegroundColor Green
    }
    Write-Host "  撤销信任：Get-ChildItem Cert:\CurrentUser\Root, Cert:\CurrentUser\TrustedPublisher | Where-Object Thumbprint -eq $($cert.Thumbprint) | Remove-Item"
} else {
    Write-Host "想在本机去掉「未知发布者」，加 -Trust 重跑，或手动导入 $cer 到「受信任的根证书颁发机构」。" -ForegroundColor Yellow
}
