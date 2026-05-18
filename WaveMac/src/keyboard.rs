/// Módulo de teclado — emite eventos de tecla via enigo/CGEventPost (macOS).
///
/// Substitui o `uinput.Device` do Python com suporte exclusivo a macOS.
/// Requer permissão de Acessibilidade em:
///   Configurações do Sistema → Privacidade & Segurança → Acessibilidade
use anyhow::Result;
use enigo::{Direction, Enigo, Key, Keyboard, Settings};

pub struct KeyboardEmulator {
    enigo: Enigo,
}

impl KeyboardEmulator {
    pub fn new() -> Result<Self> {
        let settings = Settings::default();
        let enigo = Enigo::new(&settings)
            .map_err(|e| anyhow::anyhow!("Falha ao inicializar enigo: {e}"))?;
        Ok(Self { enigo })
    }

    /// Próximo slide → seta direita
    pub fn press_next(&mut self) -> Result<()> {
        self.enigo
            .key(Key::RightArrow, Direction::Click)
            .map_err(|e| anyhow::anyhow!("Erro ao pressionar →: {e}"))
    }

    /// Slide anterior → seta esquerda
    pub fn press_prev(&mut self) -> Result<()> {
        self.enigo
            .key(Key::LeftArrow, Direction::Click)
            .map_err(|e| anyhow::anyhow!("Erro ao pressionar ←: {e}"))
    }

    /// Início da apresentação → Home
    pub fn press_home(&mut self) -> Result<()> {
        self.enigo
            .key(Key::Home, Direction::Click)
            .map_err(|e| anyhow::anyhow!("Erro ao pressionar Home: {e}"))
    }

    /// Fim da apresentação → End
    pub fn press_end(&mut self) -> Result<()> {
        self.enigo
            .key(Key::End, Direction::Click)
            .map_err(|e| anyhow::anyhow!("Erro ao pressionar End: {e}"))
    }
}
