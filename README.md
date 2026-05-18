# WaveControl

Controle apresentações com gestos da mão usando a webcam. Interface gráfica moderna com PyGObject/GTK.

## Gestos

- **1 dedo**: Próximo slide (→)
- **2 dedos**: Slide anterior (←)
- **3 dedos**: Início da apresentação (Home)
- **4 dedos**: Fim da apresentação (End)
- **Mão fechada**: Neutro

## Instalação

⚠️ **Requer Python 3.11** para compatibilidade total com mediapipe

### Automática (Recomendado)
```bash
./install.sh
```

### Manual

#### Ubuntu/Debian
```bash
sudo apt install python3-pip python3-gi python3-gi-cairo gir1.2-gtk-3.0 libgirepository1.0-dev
pip install -r requirements.txt
```

#### Fedora
```bash
sudo dnf install python3-pip python3-gobject python3-gobject-devel gtk3-devel cairo-gobject-devel
pip install -r requirements.txt
```

#### Arch Linux
```bash
sudo pacman -S python-pip python-gobject gtk3 gobject-introspection
pip install -r requirements.txt
```

#### macOS (CLI)
No macOS, o WaveControl CLI (`main_cli.py`) pode rodar de forma nativa. Recomenda-se o uso de um ambiente Python 3.11 (por exemplo, usando conda ou pyenv) para compatibilidade com o `mediapipe`.

1. Instale as dependências usando o arquivo de requisitos do macOS:
```bash
pip install -r requirements_mac.txt
```
> ✨ O arquivo de requisitos do macOS inclui `opencv-python`, `mediapipe` e a biblioteca `pynput` para emulação de teclado de alto desempenho e baixíssima latência. Se a biblioteca `pynput` não estiver instalada, o script possui um fallback inteligente que usa comandos nativos do AppleScript (`osascript`), embora o `pynput` seja altamente recomendado para melhor performance.

2. **Permissão de Acessibilidade**:
   Para simular teclas no macOS, conceda permissão de **Acessibilidade** ao seu terminal (ex. Terminal, iTerm ou VSCode Terminal):
   - Vá em `Configurações do Sistema` → `Privacidade & Segurança` → `Acessibilidade`.
   - Adicione e ative o seu terminal na lista.

#### Configurar uinput (Linux)
```bash
sudo modprobe uinput
sudo chmod 666 /dev/uinput
echo "uinput" | sudo tee -a /etc/modules
```

## Uso

### AppImage (Recomendado para Linux)
```bash
./build.sh
./appimage/WaveControl-x86_64.AppImage
```
> ✨ Funciona em qualquer distro Linux, com ou sem FUSE automaticamente

### Execução direta (macOS / Linux)
Para executar a interface gráfica (apenas Linux):
```bash
python3 main.py
```

Para executar o modo linha de comando (CLI - recomendado para macOS e servidores sem tela):
```bash
python3 main_cli.py
```

## Como usar

1. Clique em "Iniciar Detecção"
2. Posicione a mão na frente da câmera
3. Faça os gestos para controlar slides
4. Retorne à posição neutra entre gestos
