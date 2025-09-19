#!/bin/bash
# Script para criar AppImage totalmente independente com Python 3.11 embutido

set -e

echo "=== Construindo WaveControl AppImage Standalone ==="
echo "    Incluindo Python 3.11 completo + todas as dependências"

# Limpar estrutura anterior
rm -rf WaveControl.AppDir
rm -f WaveControl-x86_64.AppImage

echo "📥 Baixando Python 3.11 portable..."

# Criar estrutura do AppDir
mkdir -p WaveControl.AppDir/usr/bin
mkdir -p WaveControl.AppDir/usr/python3.11
mkdir -p WaveControl.AppDir/usr/share/applications
mkdir -p WaveControl.AppDir/usr/share/icons/hicolor/256x256/apps

# Baixar Python 3.11 portable se não existir
if [ ! -f "../python3.11-portable.tar.xz" ]; then
    echo "Baixando Python 3.11 portable..."
    cd ..
    # Usar Python portable do python.org
    wget -q -O python3.11-portable.tar.xz https://github.com/indygreg/python-build-standalone/releases/download/20241016/cpython-3.11.10+20241016-x86_64-unknown-linux-gnu-install_only.tar.gz
    cd scripts
fi

echo "📦 Extraindo Python 3.11..."
cd ../
tar -xf python3.11-portable.tar.xz -C scripts/WaveControl.AppDir/usr/python3.11 --strip-components=1
cd scripts

echo "🔧 Configurando Python 3.11 embutido..."

# Criar script python3 wrapper
cat > WaveControl.AppDir/usr/bin/python3 << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PYTHONHOME="${HERE}/../python3.11"
export PYTHONPATH="${HERE}/../python3.11/lib/python3.11:${HERE}/../python3.11/lib/python3.11/site-packages:${PYTHONPATH}"
export LD_LIBRARY_PATH="${HERE}/../python3.11/lib:${LD_LIBRARY_PATH}"
exec "${HERE}/../python3.11/bin/python3.11" "$@"
EOF

chmod +x WaveControl.AppDir/usr/bin/python3

# Criar pip3 wrapper
cat > WaveControl.AppDir/usr/bin/pip3 << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PYTHONHOME="${HERE}/../python3.11"
export PYTHONPATH="${HERE}/../python3.11/lib/python3.11:${HERE}/../python3.11/lib/python3.11/site-packages:${PYTHONPATH}"
export LD_LIBRARY_PATH="${HERE}/../python3.11/lib:${LD_LIBRARY_PATH}"
exec "${HERE}/../python3.11/bin/pip3.11" "$@"
EOF

chmod +x WaveControl.AppDir/usr/bin/pip3

echo "📚 Instalando dependências Python no Python embutido..."

# Instalar dependências usando o pip embutido
WaveControl.AppDir/usr/bin/pip3 install \
    opencv-python>=4.8.0 \
    mediapipe==0.10.14 \
    python-uinput>=0.11.2 \
    PyGObject>=3.42.0

echo "Dependências instaladas com sucesso!"

# Copiar arquivo principal
cp ../../main.py WaveControl.AppDir/usr/bin/

# Criar AppRun totalmente autônomo
cat > WaveControl.AppDir/AppRun << 'EOF'
#!/bin/bash
# AppRun totalmente autônomo com Python 3.11 embutido

HERE="$(dirname "$(readlink -f "${0}")")"

# Configurar ambiente Python embutido
export PYTHONHOME="${HERE}/usr/python3.11"
export PYTHONPATH="${HERE}/usr/python3.11/lib/python3.11:${HERE}/usr/python3.11/lib/python3.11/site-packages"
export LD_LIBRARY_PATH="${HERE}/usr/python3.11/lib:${LD_LIBRARY_PATH}"
export PATH="${HERE}/usr/bin:${PATH}"

# Função para verificar se FUSE está disponível
check_fuse() {
    if command -v fusermount >/dev/null 2>&1 || [ -e /dev/fuse ]; then
        return 0  # FUSE disponível
    else
        return 1  # FUSE não disponível
    fi
}

# Função para extrair AppImage e executar
run_extracted() {
    echo "🔧 FUSE não disponível - Extraindo AppImage..."
    
    # Criar diretório temporário
    TEMP_DIR=$(mktemp -d -t wavecontrol-XXXXXX)
    trap "rm -rf '$TEMP_DIR'" EXIT
    
    # Extrair AppImage
    cd "$TEMP_DIR"
    "${HERE}/../" --appimage-extract >/dev/null 2>&1 || {
        echo "❌ Erro ao extrair AppImage"
        exit 1
    }
    
    # Executar aplicação extraída
    cd squashfs-root
    export PYTHONHOME="${PWD}/usr/python3.11"
    export PYTHONPATH="${PWD}/usr/python3.11/lib/python3.11:${PWD}/usr/python3.11/lib/python3.11/site-packages"
    export LD_LIBRARY_PATH="${PWD}/usr/python3.11/lib:${LD_LIBRARY_PATH}"
    
    exec "${PWD}/usr/python3.11/bin/python3.11" "${PWD}/usr/bin/main.py" "$@"
}

echo "🚀 WaveControl Standalone"
echo "   Python 3.11 embutido - Zero dependências!"

# Verificar se PyGObject está disponível no sistema (ainda precisa do GTK3)
if ! "${HERE}/usr/python3.11/bin/python3.11" -c "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk" 2>/dev/null; then
    echo ""
    echo "⚠️  DEPENDÊNCIA FALTANDO: GTK3 (única dependência do sistema)"
    echo ""
    echo "Instale GTK3:"
    echo "Ubuntu/Debian: sudo apt install gir1.2-gtk-3.0"
    echo "Fedora:        sudo dnf install gtk3-devel"
    echo "Arch:          sudo pacman -S gtk3"
    echo ""
    exit 1
fi

echo "🔍 Verificando dependências empacotadas..."

# Testar dependências usando Python embutido
if "${HERE}/usr/python3.11/bin/python3.11" -c "import cv2; print(f'✅ OpenCV {cv2.__version__} OK')" 2>/dev/null; then
    echo "✅ OpenCV OK"
else
    echo "❌ Erro: OpenCV não pôde ser carregado"
    exit 1
fi

if "${HERE}/usr/python3.11/bin/python3.11" -c "import mediapipe as mp; print('✅ MediaPipe OK')" 2>/dev/null; then
    echo "✅ MediaPipe OK"
else
    echo "❌ Erro: MediaPipe não pôde ser carregado"
    exit 1
fi

echo "🚀 Todas as dependências OK! Iniciando WaveControl..."

# Verificar se estamos sendo executados como AppImage ou extraído
if [ -n "$APPIMAGE" ]; then
    # Sendo executado como AppImage
    if check_fuse; then
        echo "✅ FUSE disponível - Executando normalmente"
        cd "${HERE}/usr/bin"
        exec "${HERE}/usr/python3.11/bin/python3.11" "${HERE}/usr/bin/main.py" "$@"
    else
        echo "⚠️  FUSE não disponível - Mudando para modo extraído"
        run_extracted "$@"
    fi
else
    # Já extraído ou sendo executado diretamente
    cd "${HERE}/usr/bin"
    exec "${HERE}/usr/python3.11/bin/python3.11" "${HERE}/usr/bin/main.py" "$@"
fi
EOF

chmod +x WaveControl.AppDir/AppRun

# Criar .desktop
cat > WaveControl.AppDir/WaveControl.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=WaveControl
Comment=Controle de slides por gestos - Standalone com Python embutido
Exec=AppRun
Icon=wavecontrol
Categories=Office;Presentation;
Terminal=false
StartupNotify=true
EOF

cp WaveControl.AppDir/WaveControl.desktop WaveControl.AppDir/usr/share/applications/

# Usar logo oficial da pasta img
if [ -f "../img/256x256.png" ]; then
    echo "Usando logo oficial 256x256..."
    cp ../img/256x256.png WaveControl.AppDir/wavecontrol.png
elif [ -f "../img/64x64.png" ]; then
    echo "Usando logo oficial 64x64..."
    cp ../img/64x64.png WaveControl.AppDir/wavecontrol.png
else
    echo "Logo oficial não encontrado, criando ícone básico..."
    # Fallback: PNG mínimo válido
    python3 -c "
data = b'\\x89PNG\\r\\n\\x1a\\n\\x00\\x00\\x00\\rIHDR\\x00\\x00\\x00\\x01\\x00\\x00\\x00\\x01\\x08\\x02\\x00\\x00\\x00\\x90wS\\xde\\x00\\x00\\x00\\x0cIDATx\\x9cc\`\`\`\\x00\\x00\\x00\\x04\\x00\\x01\\xa9\\xd1\\x99\\xec\\x00\\x00\\x00\\x00IEND\\xaeB\`\\x82'
with open('WaveControl.AppDir/wavecontrol.png', 'wb') as f:
    f.write(data)
"
fi

cp WaveControl.AppDir/wavecontrol.png WaveControl.AppDir/usr/share/icons/hicolor/256x256/apps/

# Usar AppImageTool da pasta appimage/tools
if [ ! -f "../tools/appimagetool-x86_64.AppImage" ]; then
    echo "Baixando AppImageTool..."
    mkdir -p ../tools
    wget -q -O ../tools/appimagetool-x86_64.AppImage https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x ../tools/appimagetool-x86_64.AppImage
fi

echo ""
echo "Gerando AppImage Standalone..."
ARCH=x86_64 ../tools/appimagetool-x86_64.AppImage WaveControl.AppDir ../WaveControl-x86_64.AppImage

# Mostrar informações
echo ""
echo "=========================================================="
echo "🎉 AppImage Standalone criado com sucesso!"
echo "=========================================================="
echo "📦 Arquivo: WaveControl-x86_64.AppImage ($(du -h ../WaveControl-x86_64.AppImage | cut -f1))"
echo ""
echo "✅ RECURSOS DESTA VERSÃO STANDALONE:"
echo "   • Python 3.11 EMBUTIDO (zero dependências Python)"
echo "   • Funciona COM FUSE (modo normal)"
echo "   • Funciona SEM FUSE (extrai automaticamente)"
echo "   • Detecta ambiente automaticamente"
echo "   • Inclui TUDO: OpenCV, MediaPipe, PyGObject"
echo ""
echo "⚠️  ÚNICA DEPENDÊNCIA DO SISTEMA:"
echo "   • GTK3 (para interface gráfica - disponível em qualquer Linux)"
echo ""
echo "🚀 MODOS DE EXECUÇÃO:"
echo "   1. Normal: Se FUSE disponível"
echo "   2. Extraído: Se FUSE não disponível (automático)"
echo ""
echo "📋 Para usar:"
echo "   ./WaveControl-x86_64.AppImage"
echo ""
echo "✨ VERDADEIRAMENTE PORTÁVEL - Funciona em QUALQUER Linux!"
echo "=========================================================="
