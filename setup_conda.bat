@echo off
echo [資訊] 正在檢查 Minianaconda/Conda 環境...

:: 檢查 conda 指令是否存在
where conda >nul 2>nul
if %errorlevel% neq 0 (
    echo [錯誤] 找不到 conda 指令。請確保已安裝 Minianaconda 並將其加入 PATH。
    pause
    exit /b
)

echo [資訊] 正在根據 environment.yml 建立 cow_env 環境...
call conda env create -f environment.yml --prune

if %errorlevel% neq 0 (
    echo [資訊] 環境可能已存在，嘗試更新環境...
    call conda env update -f environment.yml --prune
)

echo.
echo [成功] 環境配置完成！
echo [提示] 請執行以下指令來啟用環境：
echo        conda activate cow_env
echo.
pause
