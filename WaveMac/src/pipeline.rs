/// Orquestrador: câmera, preview, inferência, gestos e teclado.
///
/// Threads:
///   Principal  → câmera (nokhwa !Send) + janela minifb
///   Separada   → inferência ONNX + teclado
use std::{
    io::Write,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread,
    time::{Duration, Instant},
};

use anyhow::{anyhow, Result};
use crossbeam_channel::{bounded, Receiver, Sender};
use image::{imageops, RgbImage};
use minifb::{Key, Window, WindowOptions};

use crate::{
    camera::CameraCapture,
    gesture::{classify_gesture, GestureHistory, GestureKind, CALIBRATION_SECS},
    inference::InferenceSession,
    keyboard::KeyboardEmulator,
};

// ===== Configurações =====
const FRAME_CHANNEL_SIZE: usize = 2;
const ACTION_COOLDOWN: Duration = Duration::from_millis(800);
const DISPLAY_W: usize = 640;
const DISPLAY_H: usize = 480;

// ===== Entry point =====

pub fn run() -> Result<()> {
    let running = Arc::new(AtomicBool::new(true));
    let running_proc = Arc::clone(&running);

    // Ctrl+C gracioso
    {
        let r = Arc::clone(&running);
        let _ = ctrlc::set_handler(move || {
            println!("\n🛑 Interrompido pelo usuário");
            r.store(false, Ordering::Relaxed);
        });
    }

    // Câmera — fica na thread principal (nokhwa::Camera !Send)
    let mut camera = CameraCapture::find_and_open()?;

    // Modelos ONNX
    println!("🤖 Carregando modelos ONNX...");
    let mut inference = InferenceSession::new()?;
    println!("✅ Modelos carregados!\n");

    print_gestures();

    // Janela de preview (também na thread principal — macOS exige)
    let mut window = Window::new(
        "WaveMac 🌊",
        DISPLAY_W,
        DISPLAY_H,
        WindowOptions { resize: true, ..WindowOptions::default() },
    )
    .map_err(|e| anyhow!("Falha ao criar janela: {e}"))?;
    window.limit_update_rate(Some(Duration::from_millis(33))); // ~30fps

    // Canal: main → proc (frames)
    let (frame_tx, frame_rx): (Sender<RgbImage>, Receiver<RgbImage>) =
        bounded(FRAME_CHANNEL_SIZE);

    // Canal: proc → main (gesto para overlay)
    let (gest_tx, gest_rx): (Sender<GestureKind>, Receiver<GestureKind>) = bounded(1);

    // ── Thread de processamento ──────────────────────────────────────────────
    let proc_thread = thread::spawn(move || -> Result<()> {
        let mut keyboard = KeyboardEmulator::new()?;
        let mut history = GestureHistory::new();
        let mut action_executed = false;
        let mut last_action_time = Instant::now();
        let start = Instant::now();
        let mut calibrated = false;

        println!("⏱️  Calibrando por {} segundos...", CALIBRATION_SECS as u32);

        while running_proc.load(Ordering::Relaxed) {
            let frame = match frame_rx.recv_timeout(Duration::from_millis(150)) {
                Ok(f) => f,
                Err(_) => continue,
            };

            // Inferência ONNX
            let raw_gesture = match inference.detect(&frame) {
                Ok(Some(result)) => classify_gesture(&result.landmarks, result.is_right_hand),
                Ok(None) => GestureKind::Neutral,
                Err(e) => {
                    eprint!("\r⚠️  Inferência: {e:<60}");
                    GestureKind::Neutral
                }
            };

            history.add(raw_gesture);

            // Envia gesto para overlay (non-blocking)
            let _ = gest_tx.try_send(raw_gesture);

            // Feedback no terminal (sobrescreve a linha)
            print!("\r  {}", gesture_terminal_label(raw_gesture));
            std::io::stdout().flush().ok();

            // Aguarda calibração
            if start.elapsed().as_secs_f32() < CALIBRATION_SECS {
                continue;
            }

            if !calibrated {
                calibrated = true;
                println!("\n✅ Calibração concluída! Mostre a mão na câmera...");
            }

            // Gesto estável → ação
            let action = history.get_stable();
            if action == GestureKind::Neutral {
                action_executed = false;
            } else if !action_executed && last_action_time.elapsed() >= ACTION_COOLDOWN {
                let result = match action {
                    GestureKind::Next => { println!("\n➡️  PRÓXIMO slide"); keyboard.press_next() }
                    GestureKind::Prev => { println!("\n⬅️  ANTERIOR slide"); keyboard.press_prev() }
                    GestureKind::Home => { println!("\n🏠 INÍCIO da apresentação"); keyboard.press_home() }
                    GestureKind::End  => { println!("\n🔚 FIM da apresentação"); keyboard.press_end() }
                    GestureKind::Neutral => Ok(()),
                };
                if let Err(e) = result {
                    eprintln!("\n⚠️  Tecla: {e}\n   → Permissão de Acessibilidade necessária");
                } else {
                    action_executed = true;
                    last_action_time = Instant::now();
                }
            }
        }

        println!("\n🛑 Thread de processamento encerrada");
        Ok(())
    });

    // ── Loop principal: câmera + preview ────────────────────────────────────
    let mut display_buf = vec![0u32; DISPLAY_W * DISPLAY_H];
    let mut current_gesture = GestureKind::Neutral;

    while running.load(Ordering::Relaxed)
        && window.is_open()
        && !window.is_key_down(Key::Escape)
    {
        // Recebe gesto mais recente (non-blocking)
        if let Ok(g) = gest_rx.try_recv() {
            current_gesture = g;
        }

        // Captura frame da câmera
        match camera.capture_frame() {
            Ok(frame) => {
                // Preenche buffer de display com frame + overlay
                fill_display_buf(&frame, &mut display_buf, DISPLAY_W, DISPLAY_H, current_gesture);
                // Manda frame para inferência (descarta se fila cheia)
                let _ = frame_tx.try_send(frame);
            }
            Err(e) => {
                eprintln!("\n⚠️  Câmera: {e}");
                running.store(false, Ordering::Relaxed);
                break;
            }
        }

        let _ = window.update_with_buffer(&display_buf, DISPLAY_W, DISPLAY_H);
    }

    running.store(false, Ordering::Relaxed);
    drop(frame_tx);

    if let Ok(Err(e)) = proc_thread.join() {
        eprintln!("❌ Erro: {e}");
    }

    println!("\n👋 WaveMac finalizado");
    Ok(())
}

// ===== Helpers de display ===================================================

/// Converte RgbImage para buffer minifb (u32 XRGB) com overlay de gesto.
///
/// Layout visual:
///   ┌──────────────────────────────┐
///   │     feed da câmera           │
///   │     (espelhado)              │
///   ├──────────────────────────────┤
///   │ banda colorida + emoji       │ ← 70px no rodapé
///   └──────────────────────────────┘
fn fill_display_buf(
    frame: &RgbImage,
    buf: &mut Vec<u32>,
    w: usize,
    h: usize,
    gesture: GestureKind,
) {
    // Resize frame para tamanho de display
    let resized = imageops::resize(frame, w as u32, h as u32, imageops::FilterType::Nearest);

    // Espelha horizontalmente (efeito "espelho")
    let mirrored = imageops::flip_horizontal(&resized);

    // Converte pixels RGB → u32 XRGB
    let band_start = h.saturating_sub(70);
    for (idx, p) in mirrored.pixels().enumerate() {
        let y = idx / w;
        if y >= band_start {
            // Rodapé: cor sólida baseada no gesto
            buf[idx] = gesture_band_color(gesture);
        } else {
            buf[idx] = ((p[0] as u32) << 16) | ((p[1] as u32) << 8) | (p[2] as u32);
        }
    }

    // Borda interna na faixa do overlay (linha separadora branca)
    for x in 0..w {
        let sep = band_start * w + x;
        if sep < buf.len() {
            buf[sep] = 0xFFFFFF;
        }
    }
}

/// Cor da banda de overlay por gesto.
fn gesture_band_color(g: GestureKind) -> u32 {
    match g {
        GestureKind::Neutral => 0x222222, // cinza escuro
        GestureKind::Next    => 0x1A6FFF, // azul → próximo
        GestureKind::Prev    => 0xFF8C00, // laranja → anterior
        GestureKind::Home    => 0x22CC55, // verde → início
        GestureKind::End     => 0xFF3333, // vermelho → fim
    }
}

/// Label para o terminal (com emoji + descrição).
fn gesture_terminal_label(g: GestureKind) -> String {
    match g {
        GestureKind::Neutral => "✊ Neutro / aguardando...              ".to_string(),
        GestureKind::Next    => "👆 1 dedo  → Próximo slide             ".to_string(),
        GestureKind::Prev    => "✌️  2 dedos → Slide anterior            ".to_string(),
        GestureKind::Home    => "🤟 3 dedos → Início da apresentação    ".to_string(),
        GestureKind::End     => "🖐️  4 dedos → Fim da apresentação       ".to_string(),
    }
}

fn print_gestures() {
    println!("📋 Gestos:");
    println!("   👆 1 dedo  → Próximo slide");
    println!("   ✌️  2 dedos → Slide anterior");
    println!("   🤟 3 dedos → Início da apresentação");
    println!("   🖐️  4 dedos → Fim da apresentação");
    println!("   ✊ Fechada  → Neutro\n");
    println!("💡 Mantenha a mão visível na câmera!");
    println!("🛑 Ctrl+C ou feche a janela para parar\n");
}
