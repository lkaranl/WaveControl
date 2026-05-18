/// Módulo de gestos — port direto da lógica Python do WaveControl.
///
/// Índices dos landmarks MediaPipe (mão com 21 pontos):
///   TIP = ponta do dedo, PIP = articulação proximal, MCP = base
use std::collections::{HashMap, VecDeque};

// ===== Constantes (espelho das constantes Python) =====
pub const GESTURE_WINDOW_SIZE: usize = 8;
pub const CONSISTENCY_THRESHOLD: f32 = 0.75;
pub const CALIBRATION_SECS: f32 = 2.0;

const THUMB_THRESHOLD: f32 = 0.05;
const FINGER_THRESHOLD: f32 = 0.05;

/// Índices das pontas dos dedos (thumb, index, middle, ring, pinky)
const TIP: [usize; 5] = [4, 8, 12, 16, 20];
/// Índices das articulações PIP / IP do polegar
const PIP: [usize; 5] = [3, 6, 10, 14, 18];

// ===== Tipos =====

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum GestureKind {
    Next,    // 1 dedo → seta direita
    Prev,    // 2 dedos → seta esquerda
    Home,    // 3 dedos → Home
    End,     // 4 dedos → End
    Neutral, // 0 ou 5 dedos / mão fechada
}

/// Um ponto 3D normalizado retornado pelo modelo de landmark.
#[derive(Debug, Clone, Copy, Default)]
pub struct Landmark {
    pub x: f32,
    pub y: f32,
    pub z: f32,
}

// ===== Lógica de dedos =====

/// Detecta se o dedo está estendido (port de `finger_extended` do Python).
///
/// Para o polegar usa o eixo X (depende da lateralidade da mão).
/// Para os demais usa eixo Y (origem no topo da imagem).
pub fn finger_extended(
    landmarks: &[Landmark],
    tip_idx: usize,
    pip_idx: usize,
    is_right_hand: bool,
) -> bool {
    let tip = landmarks[tip_idx];
    let pip = landmarks[pip_idx];

    if tip_idx == TIP[0] {
        // Polegar: eixo X
        if is_right_hand {
            tip.x < pip.x - THUMB_THRESHOLD
        } else {
            tip.x > pip.x + THUMB_THRESHOLD
        }
    } else {
        // Demais dedos: eixo Y (origem no topo → y menor = mais alto)
        tip.y < pip.y - FINGER_THRESHOLD
    }
}

/// Conta quantos dedos estão estendidos.
pub fn count_extended(landmarks: &[Landmark], is_right_hand: bool) -> usize {
    (0..5)
        .filter(|&i| finger_extended(landmarks, TIP[i], PIP[i], is_right_hand))
        .count()
}

/// Classifica o gesto atual com base nos dedos estendidos.
pub fn classify_gesture(landmarks: &[Landmark], is_right_hand: bool) -> GestureKind {
    match count_extended(landmarks, is_right_hand) {
        1 => GestureKind::Next,
        2 => GestureKind::Prev,
        3 => GestureKind::Home,
        4 => GestureKind::End,
        _ => GestureKind::Neutral,
    }
}

// ===== Filtro temporal (janela deslizante) =====

/// Histórico de gestos com janela de tamanho fixo.
/// Port de `gesture_history` + `get_stable_gesture` do Python.
pub struct GestureHistory {
    history: VecDeque<GestureKind>,
    window_size: usize,
    threshold: f32,
}

impl GestureHistory {
    pub fn new() -> Self {
        Self {
            history: VecDeque::with_capacity(GESTURE_WINDOW_SIZE),
            window_size: GESTURE_WINDOW_SIZE,
            threshold: CONSISTENCY_THRESHOLD,
        }
    }

    pub fn add(&mut self, gesture: GestureKind) {
        if self.history.len() >= self.window_size {
            self.history.pop_front();
        }
        self.history.push_back(gesture);
    }

    pub fn clear(&mut self) {
        self.history.clear();
    }

    /// Retorna o gesto estável se atingiu o threshold de consistência.
    /// Port de `get_stable_gesture` do Python.
    pub fn get_stable(&self) -> GestureKind {
        if self.history.len() < self.window_size {
            return GestureKind::Neutral;
        }

        // Conta ocorrências de cada gesto
        let mut counts: HashMap<GestureKind, usize> = HashMap::new();
        for &g in &self.history {
            *counts.entry(g).or_insert(0) += 1;
        }

        // Gesto mais frequente
        let (&most_common, &most_count) = counts
            .iter()
            .max_by_key(|(_, &c)| c)
            .expect("histórico não vazio");

        let ratio = most_count as f32 / self.window_size as f32;

        if ratio >= self.threshold && most_common != GestureKind::Neutral {
            most_common
        } else {
            GestureKind::Neutral
        }
    }
}

impl Default for GestureHistory {
    fn default() -> Self {
        Self::new()
    }
}
