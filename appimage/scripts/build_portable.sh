#!/bin/bash
# Script final para criar AppImage portável

set -e

echo "=== Construindo WaveControl AppImage Portável FINAL ==="

# Limpar estrutura anterior
rm -rf WaveControl.AppDir
rm -f WaveControl-Portable-x86_64.AppImage

# Criar estrutura do AppDir
mkdir -p WaveControl.AppDir/usr/bin
mkdir -p WaveControl.AppDir/usr/lib/python3/site-packages
mkdir -p WaveControl.AppDir/usr/share/applications
mkdir -p WaveControl.AppDir/usr/share/icons/hicolor/256x256/apps

echo "Instalando dependências Python no AppImage..."

# Instalar dependências usando pip install --target
pip3 install --target=WaveControl.AppDir/usr/lib/python3/site-packages \
    opencv-python \
    mediapipe \
    python-uinput \
    numpy

echo "Dependências instaladas com sucesso!"

# Copiar arquivo principal
cp ../../main.py WaveControl.AppDir/usr/bin/

# Criar AppRun totalmente portável
cat > WaveControl.AppDir/AppRun << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"

# Configurar Python path para usar as bibliotecas empacotadas
export PYTHONPATH="${HERE}/usr/lib/python3/site-packages:${PYTHONPATH}"

# Configurar LD_LIBRARY_PATH para bibliotecas nativas
export LD_LIBRARY_PATH="${HERE}/usr/lib/python3/site-packages/cv2:${HERE}/usr/lib/python3/site-packages:${LD_LIBRARY_PATH}"

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo "================================================================"
    echo "❌ ERRO: Python3 não está instalado!"
    echo "================================================================"
    echo "Por favor instale Python3:"
    echo "Ubuntu/Debian: sudo apt install python3"
    echo "Fedora:        sudo dnf install python3"
    echo "================================================================"
    exit 1
fi

# Verificar PyGObject - ÚNICA dependência do sistema necessária
if ! python3 -c "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk" 2>/dev/null; then
    echo "================================================================"
    echo "⚠️  DEPENDÊNCIA FALTANDO: PyGObject/GTK3"
    echo "================================================================"
    echo ""
    echo "✅ Este AppImage JÁ INCLUI:"
    echo "   • OpenCV"
    echo "   • MediaPipe"
    echo "   • NumPy"
    echo "   • python-uinput"
    echo "   • Todas as outras dependências Python"
    echo ""
    echo "❗ Precisa instalar APENAS esta dependência do sistema:"
    echo ""
    echo "Ubuntu/Debian:"
    echo "sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0"
    echo ""
    echo "Fedora/CentOS:"
    echo "sudo dnf install python3-gobject python3-gobject-base gtk3-devel"
    echo ""
    echo "openSUSE:"
    echo "sudo zypper install python3-gobject python3-gobject-Gdk"
    echo ""
    echo "Arch Linux:"
    echo "sudo pacman -S python-gobject gtk3"
    echo ""
    echo "================================================================"
    exit 1
fi

echo "🔍 Verificando dependências empacotadas..."

# Testar OpenCV
if python3 -c "import cv2; print(f'✅ OpenCV {cv2.__version__} carregado do AppImage')" 2>/dev/null; then
    echo "✅ OpenCV OK"
else
    echo "❌ Erro: OpenCV não pôde ser carregado"
    exit 1
fi

# Testar MediaPipe
if python3 -c "import mediapipe as mp; print('✅ MediaPipe carregado do AppImage')" 2>/dev/null; then
    echo "✅ MediaPipe OK"
else
    echo "❌ Erro: MediaPipe não pôde ser carregado"
    exit 1
fi

# Testar NumPy
if python3 -c "import numpy as np; print('✅ NumPy carregado do AppImage')" 2>/dev/null; then
    echo "✅ NumPy OK"
else
    echo "❌ Erro: NumPy não pôde ser carregado"
    exit 1
fi

echo "🚀 Todas as dependências OK! Iniciando WaveControl..."
echo ""

cd "${HERE}/usr/bin"
exec python3 "${HERE}/usr/bin/main.py" "$@"
EOF

chmod +x WaveControl.AppDir/AppRun

# Criar .desktop
cat > WaveControl.AppDir/WaveControl.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=WaveControl Portable
Comment=Controle de slides por gestos - Versão portável com dependências incluídas
Exec=AppRun
Icon=wavecontrol
Categories=Office;Presentation;
Terminal=false
StartupNotify=true
EOF

cp WaveControl.AppDir/WaveControl.desktop WaveControl.AppDir/usr/share/applications/

# Criar ícone
python3 -c "
import cv2
import numpy as np

icon = np.zeros((256, 256, 3), dtype=np.uint8)
icon[:] = (30, 30, 30)
cv2.circle(icon, (128, 180), 60, (0, 150, 255), -1)
cv2.rectangle(icon, (98, 80), (118, 140), (0, 150, 255), -1)
cv2.rectangle(icon, (118, 60), (138, 140), (0, 150, 255), -1)
cv2.rectangle(icon, (138, 70), (158, 140), (0, 150, 255), -1)
cv2.rectangle(icon, (158, 80), (178, 140), (0, 150, 255), -1)
cv2.putText(icon, 'WAVE', (70, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
cv2.imwrite('WaveControl.AppDir/wavecontrol.png', icon)
"

cp WaveControl.AppDir/wavecontrol.png WaveControl.AppDir/usr/share/icons/hicolor/256x256/apps/

# Usar AppImageTool da pasta tools
if [ ! -f "../../tools/appimagetool-x86_64.AppImage" ]; then
    echo "Baixando AppImageTool..."
    mkdir -p ../../tools
    wget -q -O ../../tools/appimagetool-x86_64.AppImage https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x ../../tools/appimagetool-x86_64.AppImage
fi

echo ""
echo "Gerando AppImage portável..."
ARCH=x86_64 ../../tools/appimagetool-x86_64.AppImage WaveControl.AppDir ../WaveControl-x86_64.AppImage

# Mostrar informações
echo ""
echo "=========================================================="
echo "🎉 AppImage Portável criado com sucesso!"
echo "=========================================================="
echo "📦 Arquivo: WaveControl-x86_64.AppImage ($(du -h ../WaveControl-x86_64.AppImage | cut -f1))"
echo ""
echo "✅ INCLUÍDO NO APPIMAGE:"
echo "   • OpenCV ($(pip3 show opencv-python | grep Version | cut -d' ' -f2 2>/dev/null || echo 'latest'))"
echo "   • MediaPipe ($(pip3 show mediapipe | grep Version | cut -d' ' -f2 2>/dev/null || echo 'latest'))"
echo "   • NumPy ($(pip3 show numpy | grep Version | cut -d' ' -f2 2>/dev/null || echo 'latest'))"
echo "   • python-uinput"
echo "   • Todas as dependências Python necessárias"
echo ""
echo "⚠️  DEPENDÊNCIA MÍNIMA DO SISTEMA:"
echo "   • Python3 (já instalado)"
echo "   • PyGObject/GTK3 (para interface gráfica)"
echo ""
echo "📦 Para instalar a dependência em outros PCs:"
echo "   Ubuntu: sudo apt install python3-gi gir1.2-gtk-3.0"
echo "   Fedora: sudo dnf install python3-gobject gtk3-devel"
echo ""
echo "🚀 PARA USAR:"
echo "   ./appimage/WaveControl-x86_64.AppImage"
echo ""
echo "📋 O AppImage irá:"
echo "   1. Verificar se as dependências mínimas estão instaladas"
echo "   2. Carregar todas as bibliotecas Python empacotadas"
echo "   3. Mostrar mensagens claras se algo estiver faltando"
echo "   4. Executar a aplicação normalmente"
echo "=========================================================="
