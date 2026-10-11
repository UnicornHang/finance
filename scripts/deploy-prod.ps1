# 生产环境一键部署（Docker Compose prod）— Windows PowerShell
#
# 用法（仓库根目录）：
#   .\scripts\deploy-prod.ps1
#   .\scripts\deploy-prod.ps1 -Seed
#   .\scripts\deploy-prod.ps1 -Monitoring
#   .\scripts\deploy-prod.ps1 -Down

param(
    [switch]$Seed,
    [switch]$Monitoring,
    [switch]$Down
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Invoke-ProdCompose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$ComposeArgs)
    & docker compose -f docker-compose.prod.yml --env-file .env.prod @ComposeArgs
    if ($LASTEXITCODE -ne 0) { throw "docker compose failed: $LASTEXITCODE" }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "未检测到 docker，请先安装 Docker Desktop"
}

if ($Down) {
    Write-Host "==> 停止生产栈"
    Invoke-ProdCompose --profile monitoring down
    exit 0
}

if (-not (Test-Path .env.prod)) {
    Write-Host "==> 从 .env.prod.example 生成 .env.prod 并随机化密钥"
    Copy-Item .env.prod.example .env.prod

    $jwt = -join ((1..64) | ForEach-Object { "{0:x}" -f (Get-Random -Max 16) })
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $enc = [Convert]::ToBase64String($bytes)
    $dbPass = -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
    $minioPass = -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
    $kmsBytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($kmsBytes)
    $kms = [Convert]::ToBase64String($kmsBytes)
    $grafanaPass = -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 18 | ForEach-Object { [char]$_ })
    $milvusPass = -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 18 | ForEach-Object { [char]$_ })

    $content = Get-Content .env.prod -Raw
    $content = $content -replace '(?m)^JWT_SECRET=.*', "JWT_SECRET=$jwt"
    $content = $content -replace '(?m)^ENCRYPTION_KEY=.*', "ENCRYPTION_KEY=$enc"
    $content = $content -replace '(?m)^POSTGRES_PASSWORD=.*', "POSTGRES_PASSWORD=$dbPass"
    $content = $content -replace '(?m)^DATABASE_URL=.*', "DATABASE_URL=postgresql+asyncpg://finance:${dbPass}@postgres:5432/finance"
    $content = $content -replace '(?m)^MINIO_ROOT_PASSWORD=.*', "MINIO_ROOT_PASSWORD=$minioPass"
    $content = $content -replace '(?m)^MINIO_KMS_SECRET_KEY=.*', "MINIO_KMS_SECRET_KEY=finance-prod:$kms"
    $content = $content -replace '(?m)^GRAFANA_ADMIN_PASSWORD=.*', "GRAFANA_ADMIN_PASSWORD=$grafanaPass"
    $content = $content -replace '(?m)^MILVUS_MINIO_ACCESS_KEY=.*', "MILVUS_MINIO_ACCESS_KEY=milvusminio"
    $content = $content -replace '(?m)^MILVUS_MINIO_SECRET_KEY=.*', "MILVUS_MINIO_SECRET_KEY=$milvusPass"
    Set-Content -Path .env.prod -Value $content -NoNewline
    Write-Host "    已写入随机密钥"
    Write-Host "下一步：编辑 .env.prod 填入 LLM_*_API_KEY，然后再次执行本脚本"
    exit 0
}

if (Select-String -Path .env.prod -Pattern 'REPLACE_WITH_|please-change' -Quiet) {
    throw ".env.prod 仍含占位符，请改完后再部署"
}

$profileArgs = @()
if ($Monitoring) { $profileArgs = @("--profile", "monitoring") }

Write-Host "==> 构建并启动生产栈"
Invoke-ProdCompose @profileArgs up -d --build

Write-Host "==> 等待就绪"
$ok = $false
for ($i = 1; $i -le 90; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1/nginx-health" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
}
if (-not $ok) {
    throw "等待超时，请检查 docker compose logs"
}
Write-Host "服务已就绪"

if ($Seed) {
    Write-Host "==> 执行 seed（演示账号）"
    Invoke-ProdCompose run --rm --no-deps backend python scripts/seed.py
}

Write-Host "生产入口: http://localhost"
Write-Host "说明: docs/deploy-production.md"
