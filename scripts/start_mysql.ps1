# start_mysql.ps1 — 启动本地学习用 MySQL 8.4
# 用法：右键"使用 PowerShell 运行"，或终端执行 .\start_mysql.ps1
# 数据目录：C:\Users\28929\mysql84-data（root 空密码，仅本机 3306）

$mysqld = "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqld.exe"
$datadir = "C:\Users\28929\mysql84-data"

# 已在运行则跳过
$running = Get-Process mysqld -ErrorAction SilentlyContinue
if ($running) { Write-Host "MySQL 已在运行 (PID $($running.Id))"; exit }

# 数据目录不存在则先初始化
if (-not (Test-Path "$datadir\mysql")) {
    & $mysqld --initialize-insecure --datadir="$datadir" --basedir="C:\Program Files\MySQL\MySQL Server 8.4"
    Write-Host "数据目录已初始化"
}

Start-Process -FilePath $mysqld -ArgumentList "--datadir=`"$datadir`"","--port=3306","--local-infile=1","--console" -WindowStyle Hidden
Start-Sleep -Seconds 5
& "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe" -u root --skip-password -e "SELECT VERSION() AS mysql_version;"
Write-Host "MySQL 已启动。连接方式：mysql -u root（无密码）"
