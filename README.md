# WaveControl

WaveControl é um aplicativo que permite controlar apresentações de slides usando gestos manuais capturados pela webcam. Com ele, você pode avançar ou retroceder os slides apenas levantando um ou dois dedos, sem precisar de teclado ou controle remoto.

## Interface Gráfica

A aplicação agora possui uma interface gráfica moderna desenvolvida com PyGObject/GTK que oferece:

- **Visualização da câmera em tempo real** com landmarks dos gestos
- **Controles intuitivos** para iniciar/parar a detecção
- **Painel de status** mostrando o estado atual do sistema
- **Instruções integradas** para facilitar o uso

## Como Funciona

- **1 dedo levantado**: Próximo slide (tecla →)
- **2 dedos levantados**: Slide anterior (tecla ←)  
- **Feche a mão**: Posição neutra (sem ação)

O sistema utiliza um filtro temporal inteligente que garante estabilidade, executando ações apenas quando os gestos são consistentes por alguns frames. Após executar uma ação, o sistema aguarda você retornar à posição neutra antes de aceitar novos comandos.

## Instalação

### Dependências do Sistema (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install python3-pip python3-dev python3-gi python3-gi-cairo gir1.2-gtk-3.0
sudo apt install libcairo2-dev pkg-config python3-dev libgirepository1.0-dev
```

### Dependências Python
```bash
pip install -r requirements.txt
```

### Configuração do uinput (necessário para simular teclas)
```bash
sudo modprobe uinput
sudo chmod 666 /dev/uinput
# Para tornar permanente, adicione "uinput" em /etc/modules
echo "uinput" | sudo tee -a /etc/modules
```

## Uso

### Opção 1: Flatpak (Recomendado)

```bash
# Instalar do Flathub (quando disponível)
flatpak install flathub io.github.lkaranl.WaveControl

# Executar
flatpak run io.github.lkaranl.WaveControl
```

### Opção 2: AppImage

```bash
# Gerar AppImage portável com todas as dependências
./build.sh

# Executar (289MB, totalmente autocontido)
./appimage/WaveControl-x86_64.AppImage
```

#### Instalação permanente:
```bash
mkdir -p ~/.local/bin
cp appimage/WaveControl-x86_64.AppImage ~/.local/bin/wavecontrol
chmod +x ~/.local/bin/wavecontrol
```

### Opção 3: Execução direta

1. Execute a aplicação:
```bash
python3 main.py
```

### Como usar

1. A interface gráfica será aberta. Clique em "Iniciar Detecção" para começar.

2. Posicione sua mão na frente da câmera e faça os gestos:
   - Levante 1 dedo para avançar
   - Levante 2 dedos para retroceder
   - Feche a mão para voltar à posição neutra

3. Use durante suas apresentações em qualquer software (PowerPoint, LibreOffice, etc.)

## Configurações

Você pode ajustar algumas configurações no início do arquivo `main.py`:

- `MIN_DET`: Confiança mínima para detecção (padrão: 0.6)
- `MIN_TRK`: Confiança mínima para rastreamento (padrão: 0.6)
- `CALIBRATION_S`: Tempo de calibração inicial (padrão: 2.0 segundos)
- `GESTURE_WINDOW_SIZE`: Tamanho da janela do filtro temporal (padrão: 8 frames)
- `CONSISTENCY_THRESHOLD`: Threshold de consistência (padrão: 75%)
- `CAM_INDEX`: Índice da webcam (padrão: 0)

## Criando AppImage

Para criar seu próprio AppImage:

```bash
# AppImage portável (recomendado - todas as dependências incluídas)
./build.sh

# Ou scripts alternativos (dentro de appimage/scripts/)
cd appimage/scripts
./build_portable.sh  # Versão completa
./build_simple.sh    # Versão compacta
./build_appimage.sh  # Versão básica
```

O AppImage gerado (`WaveControl-x86_64.AppImage`) é um executável portável que:
- Funciona em qualquer distribuição Linux moderna
- Não requer instalação de dependências Python 
- Verifica automaticamente se as dependências do sistema estão instaladas
- Pode ser executado diretamente ou "instalado" copiando para `~/.local/bin/`

### Vantagens do AppImage

- **Portabilidade**: Funciona em Ubuntu, Fedora, openSUSE, etc.
- **Autocontido**: Não interfere com o sistema
- **Fácil distribuição**: Um único arquivo executável
- **Não requer privilégios de root** para executar

## Requisitos

### Para AppImage
- Sistema Linux com Python3 e GTK 3.0+
- Dependências mínimas: `python3-gi`, `python3-gi-cairo`, `gir1.2-gtk-3.0`
- Todas as dependências Python estão incluídas no AppImage

### Para execução direta
- Python 3.8+
- Webcam funcional
- Sistema Linux com suporte a uinput
- GTK 3.0+

## Estrutura do Projeto

```
WaveControl/
├── main.py                     # Aplicação principal
├── requirements.txt            # Dependências Python
├── README.md                   # Documentação principal
├── LICENSE                     # Licença MIT
├── build.sh                    # Script de conveniência para gerar AppImage
├── flatpak/                    # Empacotamento Flatpak
│   ├── io.github.lkaranl.WaveControl.yml      # Manifesto Flatpak
│   ├── io.github.lkaranl.WaveControl.desktop  # Arquivo desktop
│   ├── io.github.lkaranl.WaveControl.metainfo.xml # Metadados AppStream
│   ├── icon.png                # Ícone da aplicação
│   ├── build-flatpak.sh        # Script de build local
│   ├── prepare-flathub.sh      # Script para submissão Flathub
│   └── README.md               # Documentação do Flatpak
├── appimage/                   # Empacotamento AppImage
│   ├── WaveControl-x86_64.AppImage  # AppImage portável (289MB)
│   ├── scripts/                # Scripts de build
│   │   ├── build_portable.sh   # Cria AppImage portável (recomendado)
│   │   ├── build_simple.sh     # Cria AppImage compacto
│   │   └── build_appimage.sh   # Script básico
│   └── docs/                   # Documentação específica do AppImage
│       ├── APPIMAGE.md         # Documentação técnica
│       └── PORTABLE_README.md  # Guia de uso do AppImage
└── tools/                      # Ferramentas de build
    └── appimagetool-x86_64.AppImage  # Ferramenta para criar AppImages
```
