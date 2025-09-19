# WaveControl AppImage

## Informações do AppImage

- **Nome**: WaveControl-x86_64.AppImage
- **Tamanho**: ~198KB
- **Arquitetura**: x86_64 (64-bit)
- **Dependências**: Sistema (GTK3, Python3, bibliotecas de vídeo)

## Como usar

1. **Baixar e executar**:
```bash
chmod +x WaveControl-x86_64.AppImage
./WaveControl-x86_64.AppImage
```

2. **Instalar localmente**:
```bash
mkdir -p ~/.local/bin
cp WaveControl-x86_64.AppImage ~/.local/bin/wavecontrol
chmod +x ~/.local/bin/wavecontrol
```

3. **Integração com desktop** (opcional):
```bash
# O AppImage já contém o arquivo .desktop
# Para integração manual:
cp WaveControl.AppDir/WaveControl.desktop ~/.local/share/applications/
cp WaveControl.AppDir/wavecontrol.png ~/.local/share/icons/
```

## Dependências necessárias

O AppImage verifica automaticamente se as seguintes dependências estão instaladas:

### Sistema (via apt/yum/pacman):
- python3
- python3-gi 
- python3-gi-cairo
- gir1.2-gtk-3.0

### Python (via pip):
- opencv-python
- mediapipe  
- python-uinput

## Resolução de problemas

### Erro "Dependências não encontradas"
Instale as dependências do sistema e Python conforme listado acima.

### Erro de permissão uinput
```bash
sudo modprobe uinput
sudo chmod 666 /dev/uinput
```

### AppImage não executa
- Verifique se o arquivo tem permissão de execução: `chmod +x WaveControl-x86_64.AppImage`
- Teste em terminal para ver mensagens de erro
- Verifique se FUSE está instalado: `sudo apt install fuse`

## Características técnicas

- **AppImage Tipo 2**: Formato moderno com suporte a zsync
- **Compressão**: Squashfs com gzip
- **Executável**: ELF 64-bit dinâmico
- **Runtime**: AppImageKit continuous build

## Criando uma nova versão

Para gerar um novo AppImage após modificações:

```bash
# Método rápido
./build_simple.sh

# Método completo com dependências empacotadas (experimental)
./build_appimage.sh
```
