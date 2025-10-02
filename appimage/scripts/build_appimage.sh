#!/bin/bash
set -e

echo "=== Construindo WaveControl AppImage ==="

# Verificar se estamos no diretório correto (deve ter main.py na raiz)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Mudar para o diretório raiz do projeto
cd "$ROOT_DIR"

if [ ! -f "main.py" ]; then
    echo "Erro: main.py não encontrado no diretório raiz: $ROOT_DIR"
    exit 1
fi

echo "📁 Diretório raiz: $ROOT_DIR"

# Mudar para o diretório de scripts
cd "$SCRIPT_DIR"

# Criar estrutura do AppDir se não existir
mkdir -p WaveControl.AppDir/usr/bin
mkdir -p WaveControl.AppDir/usr/share/applications  
mkdir -p WaveControl.AppDir/usr/share/icons/hicolor/256x256/apps

# Baixar AppImageTool se não existir
if [ ! -f "../tools/appimagetool-x86_64.AppImage" ]; then
    echo "Baixando AppImageTool..."
    mkdir -p ../tools
    wget -q -O ../tools/appimagetool-x86_64.AppImage https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x ../tools/appimagetool-x86_64.AppImage
fi

# Nota: Este AppImage assume que as dependências já estão instaladas no sistema
echo "Criando AppImage (dependências do sistema serão usadas)..."

# Copiar arquivos sempre (força atualização)
echo "📋 Copiando arquivos Python..."
cp "$ROOT_DIR/main.py" WaveControl.AppDir/usr/bin/
echo "   ✓ main.py copiado"

# Copiar analytics.py se existir
if [ -f "$ROOT_DIR/analytics.py" ]; then
    cp "$ROOT_DIR/analytics.py" WaveControl.AppDir/usr/bin/
    echo "   ✓ analytics.py copiado"
fi

# Verificar se o script WaveControl já existe no AppDir
# (Caso contrário, será criado depois ou já deve existir na estrutura)

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
../tools/appimagetool-x86_64.AppImage WaveControl.AppDir ../WaveControl-x86_64.AppImage

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
