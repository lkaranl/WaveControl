# AppImage Build

Cria AppImage que funciona em qualquer distro Linux, com ou sem FUSE.

## Build

```bash
# No diretório raiz do projeto
./build.sh
```

## Características

- **Universal**: Funciona em Ubuntu, Fedora, Arch, openSUSE, etc.
- **Auto-detecção**: Funciona com ou sem FUSE automaticamente
- **Portável**: Inclui todas as dependências Python (~290MB)
- **Inteligente**: Extrai automaticamente se FUSE não estiver disponível

## Uso

1. Execute o build:
```bash
./build.sh
```

2. Execute o AppImage:
```bash
./appimage/WaveControl-x86_64.AppImage
```

3. Instalar permanente (opcional):
```bash
mkdir -p ~/.local/bin
cp appimage/WaveControl-x86_64.AppImage ~/.local/bin/wavecontrol
chmod +x ~/.local/bin/wavecontrol
```

## Dependências mínimas

- Python3 (disponível em qualquer Linux)
- PyGObject/GTK3 (instalação de uma linha)

## Como funciona

- **Com FUSE**: Executa normalmente (mais rápido)
- **Sem FUSE**: Extrai automaticamente para `/tmp` e executa
- **Limpeza automática**: Remove arquivos temporários ao sair
