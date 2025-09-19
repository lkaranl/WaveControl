# AppImage Build

Scripts para criar AppImage portável do WaveControl.

## Build rápido

```bash
# No diretório raiz do projeto
./build.sh
```

## Scripts disponíveis

### build_portable.sh (Recomendado)
- AppImage completo com todas dependências Python
- Tamanho: ~289MB
- Funciona em qualquer distro Linux moderna

### build_simple.sh
- AppImage compacto
- Requer dependências Python no sistema
- Tamanho: menor

### build_appimage.sh
- Build básico
- Para desenvolvimento/teste

## Uso

1. Execute o build:
```bash
cd appimage/scripts
./build_portable.sh
```

2. Execute o AppImage:
```bash
./WaveControl-x86_64.AppImage
```

3. Instalar permanente (opcional):
```bash
mkdir -p ~/.local/bin
cp WaveControl-x86_64.AppImage ~/.local/bin/wavecontrol
chmod +x ~/.local/bin/wavecontrol
```

## Requisitos

- AppImageTool (baixado automaticamente)
- Python 3.8+
- GTK 3.0+

O AppImage funciona em Ubuntu, Fedora, openSUSE, Arch e outras distros.
