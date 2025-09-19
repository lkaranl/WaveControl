#!/bin/bash
# Script de conveniência para gerar AppImage portável

echo "🚀 Construindo WaveControl AppImage..."
echo "Diretório: $(pwd)"

cd appimage/scripts
./build_portable.sh
cd ../..

echo ""
echo "✅ AppImage criado em: ./appimage/WaveControl-x86_64.AppImage"
echo ""
echo "Para executar:"
echo "./appimage/WaveControl-x86_64.AppImage"
