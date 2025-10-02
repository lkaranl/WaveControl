#!/bin/bash
# Script para gerar AppImage Standalone do WaveControl

echo "🚀 Construindo WaveControl AppImage Standalone..."
echo "Diretório: $(pwd)"

echo "🌟 Criando versão standalone que funciona em qualquer distro Linux"
echo "   • Python 3.11 EMBUTIDO - zero dependências Python"
echo "   • Funciona com ou sem FUSE automaticamente"
echo "   • Inclui TODAS as dependências (OpenCV, MediaPipe, etc.)"
echo "   • Compatível com Ubuntu, Fedora, Arch, etc."

cd appimage/scripts
./build_standalone.sh
cd ../..

# Verificar se o AppImage foi realmente criado
APPIMAGE_FILE="appimage/WaveControl-x86_64.AppImage"

if [ -f "$APPIMAGE_FILE" ]; then
    echo ""
    echo "✅ AppImage criado com sucesso!"
    echo "📦 Localização: ./$APPIMAGE_FILE"
    echo "📏 Tamanho: $(du -h "$APPIMAGE_FILE" | cut -f1)"
    echo ""
    echo "Para executar:"
    echo "./$APPIMAGE_FILE"
else
    echo ""
    echo "❌ Erro: AppImage não foi encontrado!"
    echo "Verifique se o build foi executado corretamente."
    exit 1
fi