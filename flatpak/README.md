# WaveControl Flatpak

Este diretório contém os arquivos necessários para construir e distribuir o WaveControl como um Flatpak.

## 📦 Arquivos Incluídos

- `io.github.seuusuario.WaveControl.yml` - Manifesto principal do Flatpak
- `io.github.seuusuario.WaveControl.desktop` - Arquivo desktop para integração
- `io.github.seuusuario.WaveControl.metainfo.xml` - Metadados AppStream
- `icon.png` - Ícone da aplicação (256x256)
- `build-flatpak.sh` - Script de build e teste
- `README.md` - Esta documentação

## 🛠️ Construindo Localmente

### Pré-requisitos

```bash
# Ubuntu/Debian
sudo apt install flatpak flatpak-builder

# Fedora
sudo dnf install flatpak flatpak-builder

# Arch Linux
sudo pacman -S flatpak flatpak-builder
```

### Build e Teste

```bash
# Construir e instalar localmente
./build-flatpak.sh

# Executar para teste
flatpak run io.github.seuusuario.WaveControl
```

## 🚀 Enviando para o Flathub

### Passos para submissão:

1. **Fork do repositório Flathub**:
   ```bash
   # Vá para https://github.com/flathub/flathub
   # Clique em "Fork"
   ```

2. **Clone seu fork**:
   ```bash
   git clone https://github.com/seuusuario/flathub.git
   cd flathub
   ```

3. **Crie nova aplicação**:
   ```bash
   # Crie submodule para sua app
   git submodule add https://github.com/seuusuario/WaveControl.git io.github.seuusuario.WaveControl
   ```

4. **Ou crie repositório separado** (método recomendado):
   ```bash
   # Crie novo repositório: https://github.com/flathub/io.github.seuusuario.WaveControl
   # Copie os arquivos do Flatpak para lá
   ```

5. **Faça Pull Request**:
   - Siga as [diretrizes do Flathub](https://docs.flathub.org/docs/for-app-authors/submission)
   - Inclua todas as informações necessárias
   - Aguarde review da equipe

### Checklist para Flathub:

- ✅ Manifesto válido e testado
- ✅ Metadados AppStream completos
- ✅ Ícone em alta resolução
- ✅ Arquivo .desktop válido
- ✅ Screenshots (adicionar ao metainfo.xml)
- ✅ Licença especificada
- ✅ URL do projeto definida

## 🔧 Personalização

### Antes de enviar ao Flathub:

1. **Atualize as URLs** no manifesto e metadados:
   - Substitua `seuusuario` pelo seu usuário GitHub real
   - Atualize URLs dos screenshots
   - Atualize informações do desenvolvedor

2. **Adicione screenshots reais**:
   - Capture telas da aplicação funcionando
   - Coloque no repositório e atualize as URLs

3. **Verifique permissões**:
   - O manifesto inclui todas as permissões necessárias
   - Remove permissões desnecessárias por segurança

## 📋 Testando Localmente

```bash
# Instalar dependências
flatpak install flathub org.freedesktop.Platform//23.08
flatpak install flathub org.freedesktop.Sdk//23.08

# Build
flatpak-builder build-dir io.github.seuusuario.WaveControl.yml --force-clean

# Testar sem instalar
flatpak-builder --run build-dir io.github.seuusuario.WaveControl.yml wavecontrol

# Criar repositório e instalar
flatpak-builder --repo=repo --force-clean build-dir io.github.seuusuario.WaveControl.yml
flatpak --user remote-add --no-gpg-verify test-repo repo
flatpak --user install test-repo io.github.seuusuario.WaveControl
flatpak run io.github.seuusuario.WaveControl
```

## 🐛 Problemas Comuns

### Erro de permissões uinput:
O Flatpak pode ter limitações com uinput. Se necessário, adicione:
```yaml
finish-args:
  - --device=all  # Já incluído
  - --talk-name=org.freedesktop.login1  # Para acesso avançado ao sistema
```

### Dependências Python:
Se houver problemas com as dependências, verifique:
- URLs dos wheels estão corretas
- Hashes SHA256 estão atualizados
- Versões são compatíveis

### Câmera não funciona:
Verifique se `--device=all` está nas finish-args.

## 📖 Recursos Úteis

- [Documentação Flatpak](https://docs.flatpak.org/)
- [Diretrizes Flathub](https://docs.flathub.org/)
- [Manifesto Builder](https://flatpak.github.io/flatpak-builder/)
- [AppStream Specification](https://www.freedesktop.org/software/appstream/docs/)
