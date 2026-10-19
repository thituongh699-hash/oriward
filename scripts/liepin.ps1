param(
    [switch]$Setup,
    [switch]$Status,
    [string]$Query = '产品经理',
    [string]$Location = '苏州',
    [switch]$Refresh,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw '此凭证保存辅助脚本依赖 Windows DPAPI；项目主程序不依赖该脚本。凭证配置见 docs/LIEPIN_INTEGRATION.md。'
}
$project = Split-Path $PSScriptRoot -Parent
$secretFile = Join-Path $project 'data\private\liepin-token.dpapi'
if ($Setup) {
    Write-Host '猎聘是可选扩展，默认关闭。启用前请自行确认平台条款是否允许第三方客户端访问。'
    Write-Host '本项目仅调用职位搜索，不读取简历、不修改简历、不投递。'
    Write-Host '请自行在 https://www.liepin.com/mcp/auth 生成凭证，再粘贴到下方。不要发送到聊天。'
    Write-Host '凭证由 Windows 当前用户加密保存；此步骤不校验、不读取简历。'
    $secureToken = Read-Host '猎聘 Token（输入不显示）' -AsSecureString
    if ($secureToken.Length -eq 0) { throw '未输入凭证，未保存。' }
    New-Item -ItemType Directory -Force -Path (Split-Path $secretFile -Parent) | Out-Null
    ConvertFrom-SecureString $secureToken | Set-Content -LiteralPath $secretFile -Encoding utf8
    $secureToken.Dispose()
    Write-Host '凭证已加密保存。本地配置完成，尚未执行远程搜索。'
    Write-Host '运行搜索前需设置 ORIWARD_ENABLE_LIEPIN=1（本脚本会自动设置）。'
    exit 0
}
if ($Status) {
    [pscustomobject]@{ configured = (Test-Path -LiteralPath $secretFile); scope = 'job_search_only'; remote_verified = $false; extension_enabled = ($env:ORIWARD_ENABLE_LIEPIN -eq '1') } | ConvertTo-Json
    exit 0
}
if (-not (Test-Path -LiteralPath $secretFile)) { throw '尚未配置凭证，请先运行 scripts\liepin.ps1 -Setup' }
$oldToken = $env:LIEPIN_USER_TOKEN
$oldEnable = $env:ORIWARD_ENABLE_LIEPIN
$oldUtf8 = $env:PYTHONUTF8
$oldBytecode = $env:PYTHONDONTWRITEBYTECODE
$secretPtr = [IntPtr]::Zero
Push-Location $project
try {
    $secureToken = (Get-Content -LiteralPath $secretFile -Raw).Trim() | ConvertTo-SecureString
    $secretPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    $env:LIEPIN_USER_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPtr)
    $env:ORIWARD_ENABLE_LIEPIN = '1'
    $env:PYTHONUTF8 = '1'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $searchArgs = @('-m', 'oriward', 'jobs', 'search', '--provider', 'liepin', '--query', $Query, '--location', $Location)
    if ($Refresh) { $searchArgs += '--refresh' }
    & $Python @searchArgs
    $resultCode = $LASTEXITCODE
} finally {
    $env:LIEPIN_USER_TOKEN = $oldToken
    $env:ORIWARD_ENABLE_LIEPIN = $oldEnable
    $env:PYTHONUTF8 = $oldUtf8
    $env:PYTHONDONTWRITEBYTECODE = $oldBytecode
    if ($secretPtr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPtr) }
    if ($secureToken) { $secureToken.Dispose() }
    Pop-Location
}
exit $resultCode
