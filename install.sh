#!/bin/bash

set -e

echo "=== WaveControl - Script de Instalação ==="
echo

# Detectar distribuição
detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DISTRO=$ID
    elif type lsb_release >/dev/null 2>&1; then
        DISTRO=$(lsb_release -si | tr '[:upper:]' '[:lower:]')
    else
        echo "❌ Não foi possível detectar a distribuição"
        exit 1
    fi
}

# Instalar dependências do sistema
install_system_deps() {
    case "$DISTRO" in
        ubuntu|debian|linuxmint|pop)
            echo "📦 Detectado: Ubuntu/Debian"
            echo "Instalando dependências do sistema..."
            sudo apt update
            sudo apt install -y python3-pip python3-gi python3-gi-cairo gir1.2-gtk-3.0 libgirepository1.0-dev
            ;;
        fedora|centos|rhel)
            echo "📦 Detectado: Fedora/Red Hat"
            echo "Instalando dependências do sistema..."
            sudo dnf install -y python3-pip python3-gobject python3-gobject-devel gtk3-devel cairo-gobject-devel
            ;;
        arch|manjaro)
            echo "📦 Detectado: Arch Linux"
            echo "Instalando dependências do sistema..."
            sudo pacman -S --needed python-pip python-gobject gtk3 gobject-introspection
            ;;
        *)
            echo "❌ Distribuição '$DISTRO' não suportada"
            echo "Distribuições suportadas: Ubuntu, Debian, Fedora, Arch Linux"
            exit 1
            ;;
    esac
}

# Instalar dependências Python
install_python_deps() {
    echo
    echo "🐍 Instalando dependências Python..."
    
    if [ -f "requirements.txt" ]; then
        pip install --user -r requirements.txt
    else
        echo "❌ Arquivo requirements.txt não encontrado"
        exit 1
    fi
}

# Configurar uinput
setup_uinput() {
    echo
    echo "⚙️  Configurando uinput..."
    
    # Carregar módulo
    sudo modprobe uinput
    
    # Dar permissão
    sudo chmod 666 /dev/uinput
    
    # Tornar permanente
    if ! grep -q "uinput" /etc/modules 2>/dev/null; then
        echo "uinput" | sudo tee -a /etc/modules > /dev/null
        echo "✅ Módulo uinput adicionado para carregamento automático"
    else
        echo "✅ Módulo uinput já configurado"
    fi
}

# Criar atalho de execução
create_launcher() {
    echo
    echo "🚀 Criando atalho de execução..."
    
    # Criar diretório se não existir
    mkdir -p ~/.local/bin
    
    # Criar script de execução
    cat > ~/.local/bin/wavecontrol << EOF
#!/bin/bash
cd "$(dirname "$(readlink -f "\$0")")/../.."
python3 "$(pwd)/main.py"
EOF
    
    chmod +x ~/.local/bin/wavecontrol
    
    echo "✅ Atalho criado em ~/.local/bin/wavecontrol"
    echo "   Execute com: wavecontrol"
    echo "   (Certifique-se de que ~/.local/bin está no seu PATH)"
}

# Verificar se está no diretório correto
if [ ! -f "main.py" ] || [ ! -f "requirements.txt" ]; then
    echo "❌ Execute este script no diretório raiz do WaveControl"
    exit 1
fi

# Executar instalação
detect_distro
install_system_deps
install_python_deps
setup_uinput
create_launcher

echo
echo "🎉 Instalação concluída com sucesso!"
echo
echo "Para executar o WaveControl:"
echo "  ./wavecontrol        (se ~/.local/bin está no PATH)"
echo "  python3 main.py      (execução direta)"
echo
echo "Para testar se tudo está funcionando:"
echo "  python3 -c 'import cv2, mediapipe, gi; print(\"✅ Dependências OK\")'"
