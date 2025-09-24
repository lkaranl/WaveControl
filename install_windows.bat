@echo off
echo ========================================
echo  WaveControl - Instalador para Windows
echo ========================================
echo.

REM Verifica se Python está instalado
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRO: Python nao esta instalado ou nao esta no PATH
    echo Baixe e instale Python de: https://python.org
    echo Certifique-se de marcar "Add Python to PATH" durante a instalacao
    pause
    exit /b 1
)

echo Python detectado:
python --version
echo.

REM Verifica se pip está disponível
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRO: pip nao esta disponivel
    echo Reinstale Python com pip habilitado
    pause
    exit /b 1
)

echo ========================================
echo  Instalando dependencias Python...
echo ========================================
echo.

REM Atualiza pip
echo Atualizando pip...
python -m pip install --upgrade pip

REM Instala dependências básicas
echo Instalando OpenCV e MediaPipe...
pip install opencv-python>=4.8.0
pip install mediapipe>=0.10.0

echo Instalando pynput para simulacao de teclas...
pip install pynput>=1.7.6

echo.
echo ========================================
echo  IMPORTANTE: Configuracao GTK para Windows
echo ========================================
echo.
echo Para usar a interface grafica GTK no Windows, voce precisa:
echo.
echo 1. Instalar MSYS2 de: https://www.msys2.org/
echo 2. No terminal MSYS2, execute:
echo    pacman -S mingw-w64-x86_64-gtk3 mingw-w64-x86_64-python3-gobject
echo 3. Adicionar C:\msys64\mingw64\bin ao PATH do Windows
echo 4. Instalar PyGObject:
echo    pip install PyGObject
echo.
echo Alternativa: Use o instalador all-in-one do PyGObject:
echo https://pygobject.readthedocs.io/en/latest/getting_started.html#windows-getting-started
echo.
echo ========================================
echo  Instalacao das dependencias Python concluida!
echo ========================================
echo.
echo Para executar o WaveControl:
echo   python main_windows.py
echo.
pause
