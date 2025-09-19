# WaveControl

Controle apresentações com gestos da mão usando a webcam. Interface gráfica moderna com PyGObject/GTK.

## Gestos

- **1 dedo**: Próximo slide (→)
- **2 dedos**: Slide anterior (←)
- **3 dedos**: Início da apresentação (Home)
- **4 dedos**: Fim da apresentação (End)
- **Mão fechada**: Neutro

## Instalação

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

#### Configurar uinput
```bash
sudo modprobe uinput
sudo chmod 666 /dev/uinput
echo "uinput" | sudo tee -a /etc/modules
```

## Uso

### AppImage (Recomendado)
```bash
./build.sh
./appimage/WaveControl-x86_64.AppImage
```

### Execução direta
```bash
python3 main.py
```

## Como usar

1. Clique em "Iniciar Detecção"
2. Posicione a mão na frente da câmera
3. Faça os gestos para controlar slides
4. Retorne à posição neutra entre gestos
