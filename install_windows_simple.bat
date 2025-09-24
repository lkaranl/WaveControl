@echo off
echo ========================================
echo  WaveControl - Instalador Simples Windows
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

echo ========================================
echo  Instalando dependencias basicas...
echo ========================================
echo.

REM Atualiza pip
echo Atualizando pip...
python -m pip install --upgrade pip

REM Instala dependências básicas (Tkinter é nativo do Python)
echo Instalando OpenCV e MediaPipe...
pip install opencv-python>=4.8.0
pip install mediapipe>=0.10.0

echo Instalando pynput para simulacao de teclas...
pip install pynput>=1.7.6

echo Instalando Pillow para processamento de imagens...
pip install Pillow>=9.0.0

echo.
echo ========================================
echo  SUCESSO! Instalacao concluida
echo ========================================
echo.
echo Versoes disponiveis:
echo.
echo 1. TKINTER (Recomendada - zero configuracao):
echo    python main_windows_tkinter.py
echo.
echo 2. MODERNA (Opcional - interface mais bonita):
echo    pip install PySide6
echo    python main_windows_modern.py
echo.
echo A versao Tkinter ja esta pronta para usar!
echo.
pause
