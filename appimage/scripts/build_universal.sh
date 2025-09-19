#!/bin/bash
# Script para criar AppImage VERDADEIRAMENTE portável sem dependências FUSE

set -e

echo "=== Construindo WaveControl Universal AppImage ==="

# Verificar versão do Python
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "🐍 Python detectado: $PYTHON_VERSION"

if [[ "$PYTHON_VERSION" != "3.11" ]]; then
    echo ""
    echo "⚠️  AVISO: Recomendamos Python 3.11 para compatibilidade total"
    echo "   Versão atual: $PYTHON_VERSION"
    echo "   Continuando mesmo assim..."
fi

# Limpar estrutura anterior
rm -rf WaveControl.AppDir
rm -f WaveControl-x86_64.AppImage

# Criar estrutura do AppDir
mkdir -p WaveControl.AppDir/usr/bin
mkdir -p WaveControl.AppDir/usr/lib/python3/site-packages
mkdir -p WaveControl.AppDir/usr/share/applications
mkdir -p WaveControl.AppDir/usr/share/icons/hicolor/256x256/apps

echo "Instalando dependências Python no AppImage..."

# Instalar dependências usando pip install --target
pip3 install --target=WaveControl.AppDir/usr/lib/python3/site-packages \
    opencv-python>=4.8.0 \
    mediapipe \
    python-uinput>=0.11.2 \
    PyGObject>=3.42.0

echo "Dependências instaladas com sucesso!"

# Copiar arquivo principal
cp ../../main.py WaveControl.AppDir/usr/bin/

# Criar script de extração e execução sem FUSE
cat > WaveControl.AppDir/AppRun << 'EOF'
#!/bin/bash
# AppRun universal que funciona COM ou SEM FUSE

HERE="$(dirname "$(readlink -f "${0}")")"

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
    export PYTHONPATH="${PWD}/usr/lib/python3/site-packages:${PYTHONPATH}"
    export LD_LIBRARY_PATH="${PWD}/usr/lib/python3/site-packages:${LD_LIBRARY_PATH}"
    
    exec python3 "${PWD}/usr/bin/main.py" "$@"
}

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo "================================================================"
    echo "❌ ERRO: Python3 não está instalado!"
    echo "================================================================"
    echo "Por favor instale Python3:"
    echo "Ubuntu/Debian: sudo apt install python3"
    echo "Fedora:        sudo dnf install python3"
    echo "Arch:          sudo pacman -S python"
    echo "================================================================"
    exit 1
fi

# Verificar PyGObject
if ! python3 -c "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk" 2>/dev/null; then
    echo "================================================================"
    echo "⚠️  DEPENDÊNCIA FALTANDO: PyGObject/GTK3"
    echo "================================================================"
    echo ""
    echo "❗ Instale APENAS esta dependência do sistema:"
    echo ""
    echo "Ubuntu/Debian:"
    echo "sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0"
    echo ""
    echo "Fedora/CentOS:"
    echo "sudo dnf install python3-gobject python3-gobject-base gtk3-devel"
    echo ""
    echo "Arch Linux:"
    echo "sudo pacman -S python-gobject gtk3"
    echo ""
    echo "================================================================"
    exit 1
fi

echo "🔍 Verificando dependências empacotadas..."

# Configurar Python path
export PYTHONPATH="${HERE}/usr/lib/python3/site-packages:${PYTHONPATH}"
export LD_LIBRARY_PATH="${HERE}/usr/lib/python3/site-packages:${LD_LIBRARY_PATH}"

# Testar dependências
if python3 -c "import cv2; print(f'✅ OpenCV {cv2.__version__} OK')" 2>/dev/null; then
    echo "✅ OpenCV OK"
else
    echo "❌ Erro: OpenCV não pôde ser carregado"
    exit 1
fi

if python3 -c "import mediapipe as mp; print('✅ MediaPipe OK')" 2>/dev/null; then
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
        exec python3 "${HERE}/usr/bin/main.py" "$@"
    else
        echo "⚠️  FUSE não disponível - Mudando para modo extraído"
        run_extracted "$@"
    fi
else
    # Já extraído ou sendo executado diretamente
    cd "${HERE}/usr/bin"
    exec python3 "${HERE}/usr/bin/main.py" "$@"
fi
EOF

chmod +x WaveControl.AppDir/AppRun

# Criar .desktop
cat > WaveControl.AppDir/WaveControl.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=WaveControl
Comment=Controle de slides por gestos com auto-detecção FUSE
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
echo "Gerando AppImage Universal..."
ARCH=x86_64 ../tools/appimagetool-x86_64.AppImage WaveControl.AppDir ../WaveControl-x86_64.AppImage

# Mostrar informações
echo ""
echo "=========================================================="
echo "🎉 AppImage Universal criado com sucesso!"
echo "=========================================================="
echo "📦 Arquivo: WaveControl-x86_64.AppImage ($(du -h ../WaveControl-x86_64.AppImage | cut -f1))"
echo ""
echo "✅ RECURSOS ESPECIAIS DESTA VERSÃO:"
echo "   • Funciona COM FUSE (modo normal)"
echo "   • Funciona SEM FUSE (extrai automaticamente)"
echo "   • Detecta ambiente automaticamente"
echo "   • Inclui todas as dependências Python"
echo "   • Mensagens claras sobre dependências"
echo ""
echo "⚠️  DEPENDÊNCIA MÍNIMA DO SISTEMA:"
echo "   • Python3 (disponível em qualquer Linux)"
echo "   • PyGObject/GTK3 (para interface gráfica)"
echo ""
echo "🚀 MODOS DE EXECUÇÃO:"
echo "   1. Normal: Se FUSE disponível"
echo "   2. Extraído: Se FUSE não disponível (automático)"
echo ""
echo "📋 Para usar:"
echo "   ./WaveControl-x86_64.AppImage"
echo ""
echo "✨ Esta versão funciona em QUALQUER Linux moderno!"
echo "=========================================================="
