# 网关 RPM + TPM 联调脚本（需先启动服务且 Redis 可用）
# 用法: .\scripts\test-rate-limit.ps1 [-BaseUrl "http://localhost:8080"]

param(
    [string]$BaseUrl = "http://localhost:8080"
)

$ErrorActionPreference = "Stop"

function Write-Case([string]$Name, [bool]$Pass, [string]$Detail = "") {
    $mark = if ($Pass) { "[PASS]" } else { "[FAIL]" }
    $color = if ($Pass) { "Green" } else { "Red" }
    Write-Host "$mark $Name" -ForegroundColor $color
    if ($Detail) { Write-Host "       $Detail" -ForegroundColor DarkGray }
}

function Invoke-Gw {
    param(
        [string]$Method,
        [string]$Path,
        [string]$Tenant,
        [string]$Body = $null
    )
    $headers = @{ "X-Tenant-Id" = $Tenant }
    $uri = "$BaseUrl$Path"
    try {
        if ($Body) {
            return Invoke-WebRequest -Uri $uri -Method $Method `
                -Headers $headers -ContentType "application/json" `
                -Body $Body -UseBasicParsing -TimeoutSec 60
        }
        return Invoke-WebRequest -Uri $uri -Method $Method `
            -Headers $headers -UseBasicParsing -TimeoutSec 60
    } catch {
        if ($_.Exception.Response) {
            return $_.Exception.Response
        }
        throw
    }
}

function Get-StatusCode($Response) {
    if ($Response -is [System.Net.HttpWebResponse]) {
        return [int]$Response.StatusCode
    }
    return [int]$Response.StatusCode
}

Write-Host "=== Gateway Rate Limit DT ===" -ForegroundColor Cyan
Write-Host "BaseUrl: $BaseUrl`n"

# 1. 存活
try {
    $r = Invoke-Gw -Method GET -Path "/httpbin/get" -Tenant "dt_probe"
    Write-Case "1. 网关可达" ($r.StatusCode -eq 200) "HTTP $($r.StatusCode)"
} catch {
    Write-Case "1. 网关可达" $false $_.Exception.Message
    Write-Host "`n请先执行: .\mvnw.cmd spring-boot:run" -ForegroundColor Yellow
    exit 1
}

# 2. LLM 小请求
$smallBody = '{"model":"gpt-4","messages":[{"role":"user","content":"hello"}]}'
try {
    $r = Invoke-Gw -Method POST -Path "/v1/chat/completions" -Tenant "default_tenant" -Body $smallBody
    Write-Case "2. LLM 小请求 (RPM+TPM 通过)" ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) "HTTP $($r.StatusCode)"
} catch {
    Write-Case "2. LLM 小请求" $false $_.Exception.Message
}

# 3. RPM：新租户连打 11 次（VIP 限额 10/min）
$rpmTenant = "dt_rpm_" + [guid]::NewGuid().ToString("N").Substring(0, 8)
$lastCode = 200
for ($i = 1; $i -le 11; $i++) {
    try {
        $r = Invoke-Gw -Method GET -Path "/httpbin/get" -Tenant $rpmTenant
        $lastCode = $r.StatusCode
    } catch {
        $lastCode = Get-StatusCode $_.Exception.Response
    }
}
Write-Case "3. RPM 第11次应 429" ($lastCode -eq 429) "末次 HTTP $lastCode (tenant=$rpmTenant)"

# 4. TPM 输入：超大 prompt 应 429（default_tenant 限额 2000 token/min，约需 >8000 字符）
$big = "x" * 9000
$bigBody = "{`"model`":`"gpt-4`",`"messages`":[{`"role`":`"user`",`"content`":`"$big`"}]}"
$tpmTenant = "dt_tpm_" + [guid]::NewGuid().ToString("N").Substring(0, 8)
try {
    $r = Invoke-Gw -Method POST -Path "/v1/chat/completions" -Tenant $tpmTenant -Body $bigBody
    $code = $r.StatusCode
} catch {
    $code = Get-StatusCode $_.Exception.Response
}
Write-Case "4. TPM 输入超大 body 应 429" ($code -eq 429) "HTTP $code (tenant=$tpmTenant)"

# 5. 非 LLM：大 body 不应被 TPM 输入拦截
$plainBig = "{`"data`":`"$('y' * 2000)`"}"
try {
    $r = Invoke-Gw -Method POST -Path "/httpbin/post" -Tenant "default_tenant" -Body $plainBig
    $code = $r.StatusCode
} catch {
    $code = Get-StatusCode $_.Exception.Response
}
Write-Case "5. 非 /v1 大 body 应 2xx (跳过 TPM 输入)" ($code -ge 200 -and $code -lt 300) "HTTP $code"

Write-Host "`n完成。集成测试: .\mvnw.cmd test -Dtest=RateLimitIntegrationTest" -ForegroundColor Cyan
Write-Host "Live JUnit: .\mvnw.cmd test -Dtest=RateLimitLiveTest -Dgateway.live=true" -ForegroundColor Cyan
