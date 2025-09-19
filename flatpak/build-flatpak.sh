#!/bin/bash
# Script para construir e testar o Flatpak do WaveControl

set -e

FLATPAK_ID="io.github.lkaranl.WaveControl"
MANIFEST="${FLATPAK_ID}.yml"

echo "🏗️  Construindo Flatpak do WaveControl..."

# Verificar se Flatpak está instalado
if ! command -v flatpak &> /dev/null; then
    echo "❌ Flatpak não está instalado!"
    echo "Para instalar:"
    echo "Ubuntu/Debian: sudo apt install flatpak"
    echo "Fedora:        sudo dnf install flatpak"
    echo "Arch:          sudo pacman -S flatpak"
    exit 1
fi

# Verificar se flatpak-builder está instalado
if ! command -v flatpak-builder &> /dev/null; then
    echo "❌ flatpak-builder não está instalado!"
    echo "Para instalar:"
    echo "Ubuntu/Debian: sudo apt install flatpak-builder"
    echo "Fedora:        sudo dnf install flatpak-builder"
    echo "Arch:          sudo pacman -S flatpak-builder"
    exit 1
fi

# Adicionar repositório Flathub se não existir
if ! flatpak remotes | grep -q flathub; then
    echo "📦 Adicionando repositório Flathub..."
    flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
fi

# Instalar runtime e SDK se não estiverem instalados
echo "📦 Verificando runtime e SDK..."
flatpak install -y flathub org.freedesktop.Platform//23.08 org.freedesktop.Sdk//23.08 || true

# Limpar builds anteriores
echo "🧹 Limpando builds anteriores..."
rm -rf build-dir .flatpak-builder

# Construir o Flatpak
echo "🔨 Construindo Flatpak..."
flatpak-builder build-dir ${MANIFEST} --force-clean --install-deps-from=flathub

# Criar repositório local
echo "📚 Criando repositório local..."
flatpak-builder --repo=repo --force-clean build-dir ${MANIFEST}

# Instalar localmente para teste
echo "📦 Instalando localmente para teste..."
flatpak --user remote-add --no-gpg-verify wavecontrol-origin repo || true
flatpak --user install -y wavecontrol-origin ${FLATPAK_ID} || true

echo ""
echo "✅ Flatpak construído com sucesso!"
echo ""
echo "📋 Para testar:"
echo "flatpak run ${FLATPAK_ID}"
echo ""
echo "📋 Para desinstalar:"
echo "flatpak --user uninstall ${FLATPAK_ID}"
echo ""
echo "📋 Para exportar como bundle:"
echo "flatpak build-bundle repo ${FLATPAK_ID}.flatpak ${FLATPAK_ID}"
echo ""
echo "🚀 Para enviar ao Flathub:"
echo "1. Fork https://github.com/flathub/flathub"
echo "2. Adicione este manifesto como ${FLATPAK_ID}"
echo "3. Faça Pull Request seguindo as diretrizes do Flathub"
