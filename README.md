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

### Opção 1: AppImage (Recomendado)

1. Baixe o AppImage da seção [Releases](https://github.com/seuusuario/WaveControl/releases) ou gere localmente:
```bash
./build_simple.sh
```

2. Execute o AppImage:
```bash
./WaveControl-x86_64.AppImage
```

3. Para instalar permanentemente:
```bash
mkdir -p ~/.local/bin
cp WaveControl-x86_64.AppImage ~/.local/bin/
chmod +x ~/.local/bin/WaveControl-x86_64.AppImage
```

### Opção 2: Execução direta

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
# Script simplificado (recomendado)
./build_simple.sh

# Ou script completo
./build_appimage.sh
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
- Sistema Linux com GTK 3.0+
- Dependências do sistema: `python3-gi`, `python3-gi-cairo`, `gir1.2-gtk-3.0`
- Dependências Python: `opencv-python`, `mediapipe`, `python-uinput`

### Para execução direta
- Python 3.8+
- Webcam funcional
- Sistema Linux com suporte a uinput
- GTK 3.0+
