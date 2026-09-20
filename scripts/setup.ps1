# 一键启动脚本 - Windows PowerShell 版本
#
# 用法（在 PowerShell 中）：
#   .\scripts\setup.ps1           # 启动所有服务并初始化种子数据
#   .\scripts\setup.ps1 -Reset    # 重置：删除 volumes、重新跑 migration + seed

param(
  [switch]$Reset = $false
)

$ErrorActionPreference = "Stop"

# 切到项目根
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Split-Path -Parent $ScriptDir)

Write-Host "🚀 Finance AI Agent - 一键启动" -ForegroundColor Cyan
Write-Host ""

# 1. .env
if (-not (Test-Path ".env")) {
  Write-Host "📋 .env 不存在，从 .env.example 复制..." -ForegroundColor Yellow
  Copy-Item ".env.example" ".env"
  Write-Host "✅ 已生成 .env" -ForegroundColor Green
} else {
  Write-Host "✅ .env 已存在" -ForegroundColor Green
}

# 2. docker compose 命令
$dc = if (Get-Command docker-compose -ErrorAction SilentlyContinue) { "docker-compose" } else { "docker compose" }

# 3. 重置
if ($Reset) {
  Write-Host ""
  Write-Host "🧹 重置 volumes..." -ForegroundColor Yellow
  Invoke-Expression "$dc down -v"
}

# 4. 启动
Write-Host ""
Write-Host "📦 启动 Docker 服务..." -ForegroundColor Cyan
Invoke-Expression "$dc up -d --build"

# 5. 等基础设施
Write-Host ""
Write-Host "⏳ 等待基础设施就绪..." -ForegroundColor Cyan
for ($i = 1; $i -le 60; $i++) {
  $pg = (& docker exec finance-postgres pg_isready -U finance 2>$null) -join ""
  $redis = (& docker exec finance-redis redis-cli ping 2>$null) -join ""
  if ($pg -like "*accepting*" -and $redis -like "*PONG*") {
    Write-Host "✅ 基础设施就绪 (${i}s)" -ForegroundColor Green
    break
  }
  Start-Sleep -Seconds 2
}

# 6. 等 backend
Write-Host ""
Write-Host "⏳ 等待后端 API..." -ForegroundColor Cyan
for ($i = 1; $i -le 60; $i++) {
  try {
    $r = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 3
    if ($r.StatusCode -eq 200) {
      Write-Host "✅ 后端就绪 (${i}s)" -ForegroundColor Green
      break
    }
  } catch { }
  Start-Sleep -Seconds 2
}

Write-Host ""
Write-Host "✨ 启动完成！" -ForegroundColor Green
Write-Host ""
Write-Host "📍 访问地址：" -ForegroundColor Cyan
Write-Host "   - 平台入口：http://localhost"
Write-Host "   - 前端直连：http://localhost:5173"
Write-Host "   - API 文档：http://localhost/docs"
Write-Host "   - MinIO 控制台：http://localhost:9001"
Write-Host ""
Write-Host "🔑 默认账号：" -ForegroundColor Cyan
Write-Host "   - admin / Admin@123"
Write-Host "   - finance01 / Finance@123"
Write-Host "   - employee01 / Emp@123"
Write-Host ""
Write-Host "📜 后续："
Write-Host "   - 查看日志：$dc logs -f backend"
Write-Host "   - 跑烟测：  bash scripts/smoke.sh"
Write-Host "   - 重置：    .\scripts\setup.ps1 -Reset"
