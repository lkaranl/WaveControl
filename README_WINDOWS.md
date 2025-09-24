# WaveControl - Windows

Controle por gestos de mão para apresentações no Windows.

## 📋 Requisitos

### Sistema
- Windows 10/11
- Python 3.8 ou superior
- Câmera (webcam ou câmera integrada)

### Dependências
- OpenCV (opencv-python)
- MediaPipe
- PyGObject (GTK para Windows)
- pynput (simulação de teclas)

## 🚀 Instalação Rápida

### Opção 1: Instalador Automático
```batch
# Execute o instalador
install_windows.bat
```

### Opção 2: Instalação Manual

#### 1. Instalar Python
- Baixe de: https://python.org
- **IMPORTANTE**: Marque "Add Python to PATH" durante a instalação

#### 2. Instalar dependências Python
```bash
pip install -r requirements_windows.txt
```

#### 3. Configurar GTK no Windows

**Método A: MSYS2 (Recomendado)**
1. Instale MSYS2: https://www.msys2.org/
2. No terminal MSYS2:
```bash
pacman -S mingw-w64-x86_64-gtk3 mingw-w64-x86_64-python3-gobject
```
3. Adicione `C:\msys64\mingw64\bin` ao PATH do Windows
4. Instale PyGObject:
```bash
pip install PyGObject
```

**Método B: Instalador All-in-One**
- Use o instalador PyGObject: https://pygobject.readthedocs.io/en/latest/getting_started.html#windows-getting-started

## 🎮 Como Usar

### Executar
```bash
python main_windows.py
```

### Gestos Suportados
- 👆 **1 dedo** → Próximo slide (Seta →)
- ✌️ **2 dedos** → Slide anterior (Seta ←)  
- 🤟 **3 dedos** → Primeiro slide (Home)
- 🖖 **4 dedos** → Último slide (End)
- ✊ **0 dedos** → Neutro (sem ação)

### Funcionalidades
- **Interface moderna**: Design harmonioso com tema do sistema
- **Zoom digital**: 1x a 4x com controles intuitivos
- **Filtro temporal**: Evita ações acidentais
- **Configurações**: Mostrar/ocultar landmarks da mão
- **Status em tempo real**: Acompanhe o sistema e gestos detectados

## 🔧 Configurações

### Câmera
- Por padrão usa a câmera índice 0
- Modifique `CAM_INDEX` no código se necessário

### Sensibilidade
- `MIN_DET`: Confiança mínima para detecção (0.6)
- `MIN_TRK`: Confiança mínima para rastreamento (0.6)
- `CONSISTENCY_THRESHOLD`: Consistência do filtro temporal (75%)

### Calibração
- Sistema calibra por 2 segundos ao iniciar
- Mantenha a mão visível durante a calibração

## 🎯 Uso em Apresentações

### PowerPoint
- Funciona diretamente com teclas de seta
- Use no modo apresentação (F5)

### LibreOffice Impress
- Compatible com navegação padrão
- Use no modo apresentação

### Google Slides / Web
- Funciona em modo apresentação
- Teclas Home/End podem não funcionar em alguns navegadores

## 🛠️ Solução de Problemas

### Erro de Câmera
- Verifique se a câmera está conectada
- Feche outros aplicativos que usam a câmera
- Tente alterar `CAM_INDEX` (0, 1, 2...)

### Erro GTK
- Verifique se MSYS2 está instalado corretamente
- Confirme se `C:\msys64\mingw64\bin` está no PATH
- Reinstale PyGObject

### Gestos não funcionam
- Verifique se a mão está bem iluminada
- Mantenha a mão a uma distância adequada da câmera
- Aguarde a calibração inicial (2 segundos)

### Ações duplicadas
- O sistema usa filtro temporal para evitar isso
- Retorne à posição neutra (punho fechado) entre gestos

## 📊 Performance

- **FPS**: ~30 frames por segundo
- **Latência**: <100ms para detecção de gestos
- **CPU**: Uso moderado (depende da resolução da câmera)
- **RAM**: ~150-300MB durante execução

## 🔒 Privacidade

- **Processamento local**: Todas as imagens são processadas localmente
- **Sem internet**: Não requer conexão com a internet
- **Sem armazenamento**: Imagens não são salvas ou transmitidas

## 📝 Diferenças da Versão Linux

### Principais mudanças:
- **uinput** → **pynput**: Simulação de teclas compatível com Windows
- **GTK**: Requer configuração específica para Windows
- **Instalador**: Script `.bat` para facilitar instalação
- **Dependências**: Requirements específicos para Windows

### Funcionalidades mantidas:
- ✅ Interface gráfica idêntica
- ✅ Detecção de gestos
- ✅ Zoom digital
- ✅ Filtro temporal
- ✅ Configurações
- ✅ Performance

## 📞 Suporte

Em caso de problemas:
1. Verifique os requisitos do sistema
2. Confirme se todas as dependências estão instaladas
3. Execute `python --version` e `pip list` para verificar o ambiente
4. Consulte a seção "Solução de Problemas"

---

**WaveControl Windows** - Controle por gestos para apresentações  
Criado por Karan Luciano
