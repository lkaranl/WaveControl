#!/bin/bash
# Script simplificado para criar AppImage do WaveControl

set -e

echo "=== Construindo WaveControl AppImage ==="

# Limpar estrutura anterior
rm -rf WaveControl.AppDir
rm -f WaveControl-x86_64.AppImage

# Criar estrutura básica
mkdir -p WaveControl.AppDir/usr/share/applications
mkdir -p WaveControl.AppDir/usr/share/icons/hicolor/256x256/apps

# Copiar arquivos principais
cp main.py WaveControl.AppDir/

# Criar AppRun
cat > WaveControl.AppDir/AppRun << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"

# Verificar dependências
if ! python3 -c "import cv2, mediapipe, uinput, gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk" 2>/dev/null; then
    echo "Erro: Dependências não encontradas!"
    echo "Por favor, instale as dependências:"
    echo "sudo apt install python3-pip python3-gi python3-gi-cairo gir1.2-gtk-3.0"
    echo "pip3 install opencv-python mediapipe python-uinput"
    exit 1
fi

cd "${HERE}"
exec python3 "${HERE}/main.py" "$@"
EOF

chmod +x WaveControl.AppDir/AppRun

# Criar .desktop
cat > WaveControl.AppDir/WaveControl.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=WaveControl
Comment=Controle de slides por gestos usando webcam
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

# Baixar AppImageTool se necessário
if [ ! -f "appimagetool-x86_64.AppImage" ]; then
    echo "Baixando AppImageTool..."
    wget -q https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x appimagetool-x86_64.AppImage
fi

# Gerar AppImage
echo "Gerando AppImage..."
ARCH=x86_64 ./appimagetool-x86_64.AppImage WaveControl.AppDir WaveControl-x86_64.AppImage

echo ""
echo "=== AppImage criado com sucesso! ==="
echo "Arquivo: WaveControl-x86_64.AppImage ($(du -h WaveControl-x86_64.AppImage | cut -f1))"
echo ""
echo "Para testar:"
echo "./WaveControl-x86_64.AppImage"
echo ""
echo "Para instalar:"
echo "mkdir -p ~/.local/bin"
echo "cp WaveControl-x86_64.AppImage ~/.local/bin/"
echo "chmod +x ~/.local/bin/WaveControl-x86_64.AppImage"
