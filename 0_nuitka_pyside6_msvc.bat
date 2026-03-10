chcp 65001 >nul
cls

echo 正在清理旧构建文件...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist build_output rmdir /s /q build_output

echo 开始构建 ScreenToGIF...

rem 获取 Python 环境路径
for /f "tokens=*" %%i in ('python -c "import sys; print(sys.prefix)"') do set PYTHON_PREFIX=%%i
echo Python 路径: %PYTHON_PREFIX%

nuitka --standalone ^
    --enable-plugin=pyside6 ^
    --enable-plugin=numpy ^
    --windows-console-mode=disable ^
    --windows-icon-from-ico=icon.ico ^
    --include-data-files=icon.ico=icon.ico ^
    --include-package=PySide6 ^
    --include-package=cv2 ^
    --include-package=PIL ^
    --include-package=numpy ^
    --nofollow-import-to=cupy ^
    --follow-imports ^
    --jobs=4 ^
    --output-dir=build_output ^
    ScreenToGIF.py

if %errorlevel% equ 0 (
    echo.
    echo 构建成功！
    echo 正在复制必要的 DLL 文件...
    
    rem 创建目标目录（如果不存在）
    if not exist build_output\ScreenToGIF.dist mkdir build_output\ScreenToGIF.dist
    
    rem 复制 OpenCV DLLs
    if exist "%PYTHON_PREFIX%\Library\bin\opencv*.dll" (
        echo 复制 OpenCV DLLs...
        copy "%PYTHON_PREFIX%\Library\bin\opencv*.dll" build_output\ScreenToGIF.dist\
    ) else (
        echo 未找到 OpenCV DLLs，尝试从 site-packages 复制...
        rem 尝试从 site-packages 中的 cv2 目录复制
        for /f "tokens=*" %%i in ('python -c "import cv2; import os; print(os.path.dirname(cv2.__file__))" 2^>nul') do set OPENCV_DIR=%%i
        if defined OPENCV_DIR (
            if exist "!OPENCV_DIR!\*.dll" (
                copy "!OPENCV_DIR!\*.dll" build_output\ScreenToGIF.dist\
            )
        )
    )
    
    echo 构建完成！可执行文件在 build_output\ScreenToGIF.dist\ 目录
    dir build_output\ScreenToGIF.dist\*.exe
) else (
    echo.
    echo 构建失败，错误代码：%errorlevel%
)
