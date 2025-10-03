@echo off
echo ========================================
echo  WaveControl - Flet Edition Installer
echo ========================================
echo.

echo [1/2] Atualizando pip...
python -m pip install --upgrade pip

echo.
echo [2/2] Instalando dependencias...
pip install -r requirements_flet.txt

echo.
echo ========================================
echo  Instalacao concluida!
echo ========================================
echo.
echo Para executar: python main_windows_flet.py
echo.
pause

