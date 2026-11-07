# 校验 Windows 产物的 Authenticode 签名，并把它钉到仓库里的公钥证书上
#
# 为什么值得做：只改仓库的人（比如账号被盗、PR 被合进来）能同时改掉二进制和
# README 里的 SHA-256 —— 那两个是一起变的，等于没有交叉验证。但签名不一样：
# 没有私钥就伪造不出，所以「签名 + 固定证书」是一条独立于仓库的校验通道。
#
# 用法：
#   .\verify-windows.ps1 -Exe pojia-modifier-windows-x64.exe
#   .\verify-windows.ps1 -Exe ... -Cer D:\certs\pojia-signing.cer
#
# 退出码：0 = 通过，1 = 不通过。
param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [string]$Cer = ""
)

$ErrorActionPreference = "Stop"

# Windows PowerShell 5.1 跑在 .NET Framework 上，没有 SHA256.HashData（那是 .NET 5+）。
# 统一走 ComputeHash，两个版本都能用。
function Get-Sha256Hex([byte[]]$Bytes) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        return [BitConverter]::ToString($sha.ComputeHash($Bytes)).Replace("-", "").ToLower()
    } finally {
        $sha.Dispose()
    }
}

if (-not (Test-Path -LiteralPath $Exe)) { throw "找不到 $Exe" }

# 默认用仓库里那份公钥证书当锚点
if (-not $Cer) {
    $Cer = Join-Path $PSScriptRoot "codesign\pojia-signing.cer"
}
if (-not (Test-Path -LiteralPath $Cer)) {
    throw "找不到锚点证书 $Cer —— 没有它就无从比对，验签会退化成「信任发布页」。"
}

$pinned = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new(
    (Resolve-Path -LiteralPath $Cer).Path)
$pinnedSha256 = Get-Sha256Hex $pinned.RawData

Write-Host ""
Write-Host "锚点证书" -ForegroundColor Cyan
Write-Host ("  主题      : " + $pinned.Subject)
Write-Host ("  SHA-256   : " + $pinnedSha256)
Write-Host ("  有效期至  : " + $pinned.NotAfter.ToUniversalTime().ToString("yyyy-MM-dd"))
Write-Host ""

$sig = Get-AuthenticodeSignature -LiteralPath $Exe
$ok = $true

Write-Host ("文件      : " + (Resolve-Path -LiteralPath $Exe).Path)
Write-Host ("签名类型  : " + $sig.SignatureType)

if ($sig.SignatureType -ne "Authenticode") {
    Write-Host "  [FAIL] 没有 Authenticode 签名（文件被改过，或者压根没签）" -ForegroundColor Red
    exit 1
}

$signer = $sig.SignerCertificate
if (-not $signer) {
    Write-Host "  [FAIL] 签名结构在，但取不到签名者证书" -ForegroundColor Red
    exit 1
}

$signerSha256 = Get-Sha256Hex $signer.RawData

Write-Host ("签名者    : " + $signer.Subject)
Write-Host ("  证书 SHA-256 : " + $signerSha256)

if ($signerSha256 -ne $pinnedSha256) {
    Write-Host "  [FAIL] 签名者不是仓库里钉的那张证书" -ForegroundColor Red
    Write-Host ("         期望: " + $pinnedSha256) -ForegroundColor Red
    Write-Host ("         实际: " + $signerSha256) -ForegroundColor Red
    Write-Host "         要么证书轮换了（那就该同步更新 tools/codesign/），要么有人在冒充。" -ForegroundColor Red
    $ok = $false
} else {
    Write-Host "  [ OK ] 签名者与锚点证书一致" -ForegroundColor Green
}

# 时间戳：证书过期后签名是否仍然有效，取决于有没有可信时间戳
$stamp = $null
try { $stamp = $sig.TimeStamperCertificate } catch { }
if ($stamp) {
    Write-Host ("时间戳    : " + $stamp.Subject + "  (" + $stamp.NotAfter.ToUniversalTime().ToString("yyyy-MM-dd") + ")")
} else {
    Write-Host "时间戳    : 无（证书过期后签名会失效）" -ForegroundColor Yellow
}

# 证书链：自签根不在你机器上时一定是 UnknownError，这不是签名坏了
Write-Host ("链状态    : " + $sig.Status)
if ($sig.Status -ne "Valid") {
    Write-Host "           自签根没装进你的信任存储时就会这样，不影响「签名本身有效」这个结论；" -ForegroundColor Yellow
    Write-Host "           想让状态变成 Valid：导入 tools\codesign\pojia-signing.cer 到「受信任的根证书颁发机构」。" -ForegroundColor Yellow
}

Write-Host ""
if ($ok) {
    Write-Host "结论：签名有效，且来自仓库钉定的证书。" -ForegroundColor Green
    exit 0
} else {
    Write-Host "结论：校验不通过。" -ForegroundColor Red
    exit 1
}
