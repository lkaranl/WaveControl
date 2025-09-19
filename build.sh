#!/bin/bash
# Script de conveniência para gerar AppImage portável

echo "🚀 Construindo WaveControl AppImage..."
echo "Diretório: $(pwd)"

cd appimage/scripts
./build_portable.sh
cd ../..

# Verificar se o AppImage foi realmente criado
if [ -f "appimage/WaveControl-x86_64.AppImage" ]; then
    echo ""
    echo "✅ AppImage criado com sucesso!"
    echo "📦 Localização: ./appimage/WaveControl-x86_64.AppImage"
    echo "📏 Tamanho: $(du -h appimage/WaveControl-x86_64.AppImage | cut -f1)"
    echo ""
    echo "Para executar:"
    echo "./appimage/WaveControl-x86_64.AppImage"
else
    echo ""
    echo "❌ Erro: AppImage não foi encontrado!"
    echo "Verifique se o build foi executado corretamente."
    exit 1
fi
