# WaveControl - Windows (Versão Simples)

🎯 **Solução definitiva para Windows - SEM complicações com GTK!**

## 🚀 Instalação Super Simples

### 1. Instalar Python
- Baixe de: https://python.org
- **IMPORTANTE**: Marque "Add Python to PATH"

### 2. Instalar automaticamente
```batch
# Execute o instalador simples
install_windows_simple.bat
```

### 3. Executar
```bash
# Versão recomendada (Tkinter - nativo do Python)
python main_windows_tkinter.py

# Versão moderna (PySide6 - mais bonita)
pip install PySide6
python main_windows_modern.py
```

## ✨ Duas Versões Disponíveis

### 🥇 **Tkinter** (Recomendada)
- ✅ **Zero configuração** - Vem com Python
- ✅ **Aparência nativa** do Windows
- ✅ **Estável e confiável**
- ✅ **Instalação em 30 segundos**
- 📁 Arquivo: `main_windows_tkinter.py`

### 🎨 **PySide6** (Moderna)
- ✅ **Interface mais bonita**
- ✅ **Componentes modernos**
- ✅ **Animações suaves**
- ⚠️ **Dependência extra** (PySide6)
- 📁 Arquivo: `main_windows_modern.py`

## 🎮 Funcionalidades

### Gestos Suportados
- 👆 **1 dedo** → Próximo slide (Seta →)
- ✌️ **2 dedos** → Slide anterior (Seta ←)
- 🤟 **3 dedos** → Primeiro slide (Home)
- 🖖 **4 dedos** → Último slide (End)
- ✊ **0 dedos** → Neutro (sem ação)

### Interface
- **Zoom digital**: 1x a 4x
- **Filtro temporal**: Evita ações acidentais
- **Status em tempo real**: Acompanhe gestos detectados
- **Configurações**: Mostrar/ocultar landmarks
- **Aparência nativa**: Integra perfeitamente com Windows

## 📊 Comparação das Versões

| Recurso | Tkinter | PySide6 | GTK (❌) |
|---------|---------|---------|----------|
| **Instalação** | ✅ Nativa | ⚠️ Extra | ❌ Complexa |
| **Aparência** | ✅ Nativa | ✅ Moderna | ⚠️ Linux-like |
| **Performance** | ✅ Rápida | ✅ Rápida | ⚠️ Média |
| **Estabilidade** | ✅ Alta | ✅ Alta | ❌ Problemas |
| **Manutenção** | ✅ Simples | ✅ Simples | ❌ Complexa |

## 🔧 Solução de Problemas

### Erro de Câmera
```
Erro: Não foi possível acessar a câmera
```
**Solução:**
- Feche outros apps que usam câmera (Skype, Teams, etc.)
- Tente mudar `CAM_INDEX` de 0 para 1 no código

### Gestos não funcionam
**Solução:**
- Aguarde calibração (2 segundos)
- Melhore iluminação
- Mantenha mão a 30-60cm da câmera

### Python não encontrado
```
'python' is not recognized...
```
**Solução:**
- Reinstale Python marcando "Add to PATH"
- Ou use `py` em vez de `python`

## 🎯 Uso em Apresentações

### PowerPoint
1. Abra apresentação
2. Pressione F5 (modo apresentação)
3. Execute WaveControl
4. Use gestos para navegar

### Google Slides
1. Abra apresentação no navegador
2. Clique em "Apresentar"
3. Execute WaveControl
4. Navegue com gestos

### LibreOffice Impress
1. Abra apresentação
2. Pressione F5
3. Execute WaveControl
4. Controle com gestos

## ⚡ Performance

- **Latência**: <100ms
- **FPS**: ~30 frames/segundo
- **CPU**: Uso moderado
- **RAM**: ~200MB
- **Compatibilidade**: Windows 10/11

## 🔒 Privacidade

- ✅ **100% local** - sem internet
- ✅ **Sem armazenamento** de imagens
- ✅ **Sem transmissão** de dados
- ✅ **Código aberto** - você vê tudo

## 📈 Por que essa solução é melhor?

### ❌ Problemas da versão GTK:
- Requer MSYS2 (500MB+ de download)
- Configuração manual complexa
- Aparência inconsistente no Windows
- Possíveis conflitos de dependências

### ✅ Vantagens Tkinter/PySide6:
- **Instalação em segundos**
- **Aparência nativa do Windows**
- **Zero conflitos**
- **Suporte oficial Microsoft**
- **Manutenção simples**

## 🏆 Resultado Final

**Antes (GTK):**
```bash
# 20+ passos de configuração
# Downloads gigantes (MSYS2)
# Configuração manual PATH
# Possíveis erros
# Aparência estranha
```

**Agora (Tkinter):**
```bash
# 3 passos simples
install_windows_simple.bat
python main_windows_tkinter.py
# FUNCIONANDO! 🎉
```

---

**WaveControl Windows** - A solução definitiva para controle por gestos no Windows!  
Criado por Karan Luciano
