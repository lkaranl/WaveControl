#!/bin/bash
# Script para preparar submissão ao Flathub

set -e

echo "🚀 Preparando WaveControl para submissão ao Flathub..."

# Variáveis
GITHUB_USER=${1:-"seuusuario"}
APP_ID="io.github.${GITHUB_USER}.WaveControl"
FLATHUB_REPO_NAME="${APP_ID}"

echo "📋 Usando GitHub user: ${GITHUB_USER}"
echo "📋 App ID: ${APP_ID}"

# Verificar se git está configurado
if ! git config user.name >/dev/null || ! git config user.email >/dev/null; then
    echo "❌ Git não está configurado!"
    echo "Configure com:"
    echo "git config --global user.name 'Seu Nome'"
    echo "git config --global user.email 'seu@email.com'"
    exit 1
fi

# Criar diretório para o repositório Flathub
FLATHUB_DIR="../flathub-${APP_ID}"
echo "📁 Criando diretório: ${FLATHUB_DIR}"
mkdir -p "${FLATHUB_DIR}"
cd "${FLATHUB_DIR}"

# Inicializar repositório Git
if [ ! -d ".git" ]; then
    echo "🔧 Inicializando repositório Git..."
    git init
    git branch -M main
fi

# Copiar arquivos necessários
echo "📄 Copiando arquivos do Flatpak..."
cp "../flatpak/${APP_ID}.yml" .
cp "../flatpak/${APP_ID}.desktop" .
cp "../flatpak/${APP_ID}.metainfo.xml" .
cp "../flatpak/icon.png" .
cp "../flatpak/README.md" .

# Criar .gitignore específico para Flatpak
cat > .gitignore << 'EOF'
# Flatpak build artifacts
build-dir/
.flatpak-builder/
repo/
*.flatpak

# IDE files
.vscode/
.idea/

# Temporary files
*.tmp
*~
EOF

# Atualizar manifesto com o usuário correto
if [ "${GITHUB_USER}" != "seuusuario" ]; then
    echo "🔧 Atualizando manifesto com usuário: ${GITHUB_USER}"
    sed -i "s/seuusuario/${GITHUB_USER}/g" "${APP_ID}.yml"
    sed -i "s/seuusuario/${GITHUB_USER}/g" "${APP_ID}.metainfo.xml"
fi

# Criar arquivo flathub.json (metadados do Flathub)
cat > flathub.json << EOF
{
    "only-arches": ["x86_64"]
}
EOF

# Adicionar arquivos ao Git
echo "📦 Adicionando arquivos ao Git..."
git add .
git commit -m "Initial commit: WaveControl Flatpak

- Hand gesture-based slide controller
- Real-time camera processing with MediaPipe
- GTK3 interface
- Cross-platform Linux support" || true

echo ""
echo "✅ Preparação concluída!"
echo ""
echo "📋 Próximos passos para submeter ao Flathub:"
echo ""
echo "1. 🌐 Vá para https://github.com/flathub/flathub"
echo "2. 🍴 Clique em 'Fork' para fazer um fork"
echo "3. 🆕 Crie um novo repositório: https://github.com/flathub/${APP_ID}"
echo "4. 📤 Faça push dos arquivos:"
echo "   cd ${FLATHUB_DIR}"
echo "   git remote add origin https://github.com/flathub/${APP_ID}.git"
echo "   git push -u origin main"
echo ""
echo "5. 📝 Crie Pull Request no repositório principal flathub/flathub:"
echo "   - Adicione submodule: git submodule add https://github.com/flathub/${APP_ID}.git ${APP_ID}"
echo "   - Ou siga o processo atual do Flathub"
echo ""
echo "6. 📸 Adicione screenshots reais à aplicação"
echo "7. 🔍 Aguarde review da equipe Flathub"
echo ""
echo "📂 Arquivos preparados em: ${FLATHUB_DIR}"
echo "📋 App ID: ${APP_ID}"
echo ""
echo "⚡ Para testar localmente:"
echo "cd ${FLATHUB_DIR} && flatpak-builder build-dir ${APP_ID}.yml --install --user --force-clean"
