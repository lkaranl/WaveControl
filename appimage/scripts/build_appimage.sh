#!/bin/bash
set -e

echo "=== Construindo WaveControl AppImage ==="

# Verificar se estamos no diretório correto
if [ ! -f "main.py" ]; then
    echo "Erro: Execute este script no diretório raiz do WaveControl"
    exit 1
fi

# Criar estrutura do AppDir se não existir
mkdir -p WaveControl.AppDir/usr/bin
mkdir -p WaveControl.AppDir/usr/share/applications  
mkdir -p WaveControl.AppDir/usr/share/icons/hicolor/256x256/apps

# Baixar AppImageTool se não existir
if [ ! -f "appimagetool-x86_64.AppImage" ]; then
    echo "Baixando AppImageTool..."
    wget -q https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x appimagetool-x86_64.AppImage
fi

# Nota: Este AppImage assume que as dependências já estão instaladas no sistema
echo "Criando AppImage (dependências do sistema serão usadas)..."

# Copiar arquivos se necessário
if [ ! -f "WaveControl.AppDir/usr/bin/main.py" ]; then
    cp main.py WaveControl.AppDir/usr/bin/
fi

if [ ! -f "WaveControl.AppDir/usr/bin/WaveControl" ]; then
    cp WaveControl.AppDir/usr/bin/WaveControl WaveControl.AppDir/usr/bin/
    chmod +x WaveControl.AppDir/usr/bin/WaveControl
fi

# Criar symlink para AppRun
if [ ! -L "WaveControl.AppDir/AppRun" ]; then
    ln -sf usr/bin/WaveControl WaveControl.AppDir/AppRun
fi

# Verificar arquivos essenciais
echo "Verificando estrutura..."
for file in "WaveControl.AppDir/WaveControl.desktop" "WaveControl.AppDir/wavecontrol.png" "WaveControl.AppDir/usr/bin/WaveControl" "WaveControl.AppDir/usr/bin/main.py"; do
    if [ ! -f "$file" ]; then
        echo "Erro: Arquivo $file não encontrado!"
        exit 1
    fi
done

# Gerar AppImage
echo "Gerando AppImage..."
./appimagetool-x86_64.AppImage WaveControl.AppDir WaveControl-x86_64.AppImage

echo ""
echo "=== AppImage criado com sucesso! ==="
echo "Arquivo: WaveControl-x86_64.AppImage"
echo ""
echo "Para executar:"
echo "./WaveControl-x86_64.AppImage"
echo ""
echo "Para instalar:"
echo "mv WaveControl-x86_64.AppImage ~/.local/bin/"
echo "chmod +x ~/.local/bin/WaveControl-x86_64.AppImage"
