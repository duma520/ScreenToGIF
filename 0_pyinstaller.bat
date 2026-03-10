pyinstaller --noconfirm ^
    --onefile ^
    --windowed ^
    --icon=icon.ico ^
    --name="ScreenToGIF" ^
    --add-data="icon.ico;." ^
    --hidden-import=PySide6.QtCore ^
    --hidden-import=PySide6.QtGui ^
    --hidden-import=PySide6.QtWidgets ^
    --hidden-import=cv2 ^
    --hidden-import=numpy ^
    --hidden-import=PIL ^
    --collect-all=PySide6 ^
    ScreenToGIF.py