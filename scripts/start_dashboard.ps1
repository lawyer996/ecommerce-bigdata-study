# start_dashboard.ps1 — 启动 Stage1 交互式数据大屏（Streamlit）
#
# 用法（任选其一）：
#   .\scripts\start_dashboard.ps1                 # 在仓库根目录
#   powershell -File scripts\start_dashboard.ps1  # 从任意目录（自动定位仓库根）
#   .\scripts\start_dashboard.ps1 -Port 8502      # 换端口
#
# 说明：MySQL 不是必需的——大屏会自动回退读取 dataset/clean_behavior.csv。

param(
    [int]$Port = 8501
)

$ErrorActionPreference = "Stop"

# ---------- 定位仓库根目录（$PSScriptRoot 在部分调用方式下为空，故多重回退） ----------
function Get-RepoRoot {
    $candidates = @()
    if ($PSScriptRoot) { $candidates += (Split-Path -Parent $PSScriptRoot) }
    if ($PSCommandPath) { $candidates += (Split-Path -Parent (Split-Path -Parent $PSCommandPath)) }
    if ($MyInvocation.MyCommand.Path) {
        $candidates += (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
    }
    foreach ($c in $candidates) {
        if ($c -and (Test-Path (Join-Path $c "run_pipeline.py"))) { return (Resolve-Path $c).Path }
    }
    # 回退：从当前目录逐级向上找 run_pipeline.py
    $cur = (Get-Location).Path
    while ($cur) {
        if (Test-Path (Join-Path $cur "run_pipeline.py")) { return $cur }
        $parent = Split-Path -Parent $cur
        if (-not $parent -or $parent -eq $cur) { break }
        $cur = $parent
    }
    return $null
}

$root = Get-RepoRoot
if (-not $root) {
    Write-Host "[X] 未找到仓库根目录（缺少 run_pipeline.py），请在仓库内运行本脚本" -ForegroundColor Red
    exit 1
}

$app = Join-Path $root "stage1_data_analysis\dashboard.py"
if (-not (Test-Path $app)) {
    Write-Host "[X] 找不到 $app" -ForegroundColor Red
    exit 1
}

# ---------- 检查依赖（用与运行脚本相同的解释器，避免装到别的 Python 里） ----------
$ver = & py -3.10 -c "import streamlit,sys; sys.stdout.write(streamlit.__version__)" 2>$null
if (-not $ver) {
    Write-Host "[!] 未检测到 streamlit，正在安装（阿里云镜像）..." -ForegroundColor Yellow
    & py -3.10 -m pip install streamlit -i https://mirrors.aliyun.com/pypi/simple/
}

# ---------- 提示数据源状态 ----------
$csv = Join-Path $root "dataset\clean_behavior.csv"
if (-not (Test-Path $csv)) {
    Write-Host "[!] 未找到 dataset\clean_behavior.csv，请先运行：" -ForegroundColor Yellow
    Write-Host "    py -3.10 stage1_data_analysis/clean_real_data.py" -ForegroundColor Yellow
}

Write-Host "[OK] 启动数据大屏： http://localhost:$Port" -ForegroundColor Green
Write-Host "     停止服务：在此窗口按 Ctrl+C" -ForegroundColor DarkGray
Set-Location $root
# --server.headless true：跳过首次运行的邮箱询问（否则非交互环境下会直接退出）
& py -3.10 -m streamlit run $app --server.port $Port --server.headless true --browser.gatherUsageStats false
