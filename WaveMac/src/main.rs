/// WaveMac — Controle de apresentações por gestos de mão (macOS)
///
/// Arquitetura:
///   camera.rs    — Captura de frames via nokhwa/AVFoundation
///   inference.rs — Pipeline ONNX: palm detection + hand landmark
///   gesture.rs   — Lógica de dedos, histórico, classificação
///   keyboard.rs  — Emissão de teclas via enigo/CGEventPost
///   pipeline.rs  — Orquestração: threads producer/consumer
mod camera;
mod gesture;
mod inference;
mod keyboard;
mod pipeline;

use anyhow::Result;
use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(
    name = "wavemac",
    about = "🌊 WaveMac — Controle apresentações com gestos de mão",
    version = "0.1.0"
)]
struct Cli {
    #[command(subcommand)]
    command: Option<Commands>,
}

#[derive(Subcommand)]
enum Commands {
    /// Lista câmeras disponíveis no sistema
    #[command(name = "list", alias = "-l")]
    List,
}

fn main() -> Result<()> {
    env_logger::init();

    let cli = Cli::parse();

    println!("🌊 WaveMac — Controle por Gestos");
    println!("================================");

    match cli.command {
        Some(Commands::List) => {
            camera::list_cameras();
        }
        None => {
            println!();
            println!("⚠️  Permissão necessária:");
            println!("   Configurações do Sistema → Privacidade & Segurança → Acessibilidade");
            println!("   Adicione o seu terminal à lista para simular teclas.");
            println!();
            pipeline::run()?;
        }
    }

    Ok(())
}
