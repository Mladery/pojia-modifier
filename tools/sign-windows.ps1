# 给打包好的可执行文件签名（Windows）
#
# 用法：
#   .\sign-windows.ps1 -Exe build\dist\pojia-modifier.exe -Pfx D:\certs\pojia-signing.pfx
#   .\sign-windows.ps1 -Exe build\dist\pojia-modifier.exe -Pfx ... -Password 'xxx' -NoTimestamp
#
# 不传 -Password 就从 pfx 同目录的 pojia-signing-密码.txt 读。
param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [Parameter(Mandatory = $true)][string]$Pfx,
    [string]$Password = "",
    [switch]$NoTimestamp
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Exe)) { throw "找不到 $Exe" }
if (-not (Test-Path -LiteralPath $Pfx)) { throw "找不到 $Pfx" }

if (-not $Password) {
    $side = Join-Path (Split-Path -Parent $Pfx) "pojia-signing-密码.txt"
    if (Test-Path -LiteralPath $side) {
        $Password = (Get-Content -LiteralPath $side -Raw).Trim()
    } else {
        throw "没给 -Password，同目录也没有 pojia-signing-密码.txt"
    }
}

# signtool 不在 PATH 上是常态 —— GitHub 的 windows runner 就没配，直接 `& signtool`
# 会报 "The term 'signtool' is not recognized"。按顺序找：
#   1. PATH
#   2. Windows Kits 10 的 <version>\x64 与 <version>\x86（版本号从高到低）
#   3. Windows Kits 8.1（根目录下直接就是 x64）
function Find-SignTool {
    $cmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $roots = @()
    if (${env:ProgramFiles(x86)}) {
        $roots += (Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin")
        $roots += (Join-Path ${env:ProgramFiles(x86)} "Windows Kits\8.1\bin\x64")
    }
    if ($env:ProgramFiles) {
        $roots += (Join-Path $env:ProgramFiles "Windows Kits\10\bin")
    }

    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        $p = Join-Path $root "signtool.exe"
        if (Test-Path -LiteralPath $p) { return $p }

        # 只往下看 <version>\<arch> 两层。整棵树递归没必要 —— bin 下几千个文件，
        # 在 runner 上白花好几秒。
        $versions = Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
                    Sort-Object Name -Descending
        foreach ($v in $versions) {
            foreach ($arch in @("x64", "x86")) {
                $p = Join-Path $v.FullName "$arch\signtool.exe"
                if (Test-Path -LiteralPath $p) { return $p }
            }
        }
    }
    return $null
}

$signtool = Find-SignTool
if (-not $signtool) {
    throw "找不到 signtool.exe。装 Windows SDK 或 VS Build Tools（含 Windows 10 SDK 的 Signing Tools），或把它加到 PATH。"
}
Write-Host ("signtool: " + $signtool)

$common = @("sign", "/f", $Pfx, "/p", $Password, "/fd", "sha256")
if (-not $NoTimestamp) {
    # 时间戳让签名在证书过期后仍然有效。自签证书照样能打 —— RFC 3161 的 TSA
    # 不校验签名者证书链。网络不通就退回不带时间戳，别让整条流水线卡死。
    & $signtool @common /tr "http://timestamp.digicert.com" /td sha256 $Exe
    if ($LASTEXITCODE -ne 0) {
        Write-Host "时间戳失败（网络？），改为不带时间戳重签一次" -ForegroundColor Yellow
        & $signtool @common $Exe
    }
} else {
    & $signtool @common $Exe
}
if ($LASTEXITCODE -ne 0) { throw "签名失败（signtool 退出码 $LASTEXITCODE）" }

$sig = Get-AuthenticodeSignature -LiteralPath $Exe
Write-Host ""
Write-Host ("文件    : " + (Resolve-Path -LiteralPath $Exe).Path)
Write-Host ("签名类型: " + $sig.SignatureType)
Write-Host ("签名者  : " + $sig.SignerCertificate.Subject)
Write-Host ("状态    : " + $sig.Status)
if ($sig.Status -ne "Valid") {
    Write-Host "  状态不是 Valid 通常只是本机没信任这张自签根 —— 签名本身是好的。" -ForegroundColor Yellow
    Write-Host "  让本机信任：把 pojia-signing.cer 导入「受信任的根证书颁发机构」，或用 make-signing-cert.ps1 -Trust。" -ForegroundColor Yellow
}
