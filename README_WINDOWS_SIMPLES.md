# WaveControl - Windows (Versão Simples)

Controle de apresentações por gestos usando apenas OpenCV (sem MediaPipe).

## 🚀 Instalação Rápida

### 1. Instalar Python
- Baixe Python 3.8+ do site oficial
- ✅ Marque "Add Python to PATH" durante a instalação

### 2. Instalar Dependências
```bash
pip install opencv-python pynput Pillow
```

### 3. Executar
```bash
python main_windows_simple.py
```

## 🎮 Como Usar

### Gestos (baseados em movimento)
- **Pouco movimento** → Próximo slide (→)
- **Movimento médio** → Slide anterior (←)
- **Movimento grande** → Primeiro slide (Home)
- **Movimento máximo** → Último slide (End)
- **Sem movimento** → Neutro

### Controles da Interface
- **▶ Iniciar/⏹ Parar**: Liga/desliga a detecção
- **Zoom Digital**: 1x a 4x para melhorar precisão
- **Mostrar detecção**: Visualiza o que a câmera está detectando

## 🔧 Configuração

### Posicionamento da Câmera
- Posicione-se de frente para a câmera
- Mantenha a mão no centro do frame
- Use zoom digital para ajustar a área de detecção

### Calibração
- O sistema calibra automaticamente por 2 segundos
- Mantenha-se parado durante a calibração
- Após a calibração, faça movimentos para testar

## 🛠️ Solução de Problemas

### Câmera não funciona
- Verifique se a câmera está conectada
- Feche outros programas que usam a câmera
- Tente reiniciar o programa

### Detecção não funciona bem
- Ajuste o zoom digital (2x ou 3x)
- Melhore a iluminação
- Mantenha fundo simples (sem muito movimento)
- Use a opção "Mostrar detecção" para ver o que está sendo detectado

### Teclas não funcionam
- Certifique-se de que o foco está na apresentação
- Teste manualmente as teclas ← → Home End
- Verifique se não há outro programa interceptando as teclas

## 📋 Requisitos Mínimos

- **Sistema**: Windows 7/8/10/11
- **Python**: 3.8 ou superior
- **Câmera**: Webcam ou câmera USB
- **RAM**: 4GB (recomendado)
- **CPU**: Dual-core 2GHz+

## 🆚 Diferenças da Versão Completa

Esta versão simples:
- ✅ **Mais estável** - sem problemas de DLL
- ✅ **Instalação fácil** - menos dependências
- ✅ **Funciona em qualquer PC** - sem requisitos especiais
- ❌ **Menos preciso** - baseado em movimento, não gestos específicos
- ❌ **Menos gestos** - apenas 4 ações principais

## 📞 Suporte

Se tiver problemas:
1. Verifique se todas as dependências estão instaladas
2. Teste com zoom digital 2x-3x
3. Melhore a iluminação do ambiente
4. Use fundo simples sem movimento

---

**Criado por Karan Luciano** | Versão Simples - Sem MediaPipe