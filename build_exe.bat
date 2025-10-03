@echo off
echo ============================================================
echo  WaveControl - Build Script
echo  Gerando executável com PyInstaller
echo ============================================================
echo.

REM Limpar builds anteriores
echo [1/4] Limpando builds anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo ✓ Limpeza concluída
echo.

REM Instalar PyInstaller se necessário
echo [2/4] Verificando PyInstaller...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Instalando PyInstaller...
    pip install pyinstaller
) else (
    echo ✓ PyInstaller já instalado
)
echo.

REM Compilar com o .spec
echo [3/4] Compilando aplicação...
echo Isso pode demorar alguns minutos...
pyinstaller main_windows_flet.spec --clean
echo.

REM Verificar resultado
echo [4/4] Verificando resultado...
if exist dist\WaveControl.exe (
    echo.
    echo ============================================================
    echo  ✓ BUILD CONCLUÍDO COM SUCESSO!
    echo ============================================================
    echo.
    echo  Executável gerado em: dist\WaveControl.exe
    echo  Tamanho: 
    dir dist\WaveControl.exe | find "WaveControl.exe"
    echo.
    echo ============================================================
    echo.
    echo Deseja testar o executável agora? (S/N)
    set /p teste=
    if /i "%teste%"=="S" (
        echo Executando WaveControl...
        cd dist
        WaveControl.exe
    )
) else (
    echo.
    echo ============================================================
    echo  ❌ ERRO: Build falhou!
    echo ============================================================
    echo.
    echo Verifique os logs acima para mais detalhes.
    echo.
)

pause

