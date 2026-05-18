/// Módulo de inferência — pipeline ONNX de dois estágios para hand tracking.
///
/// Modelos OpenCV/MediaPipe (formato NHWC, tf2onnx):
///   palm_detection_lite.onnx
///     IN:  input_1  [1, 192, 192, 3]
///     OUT: Identity [1, 2016, 18]   → regressors (cx, cy, w, h, kp…)
///          Identity_1 [1, 2016, 1]  → classificators (score logit)
///
///   hand_landmark_lite.onnx
///     IN:  input_1  [1, 224, 224, 3]
///     OUT: Identity   [1, 63]  → landmarks (21 × 3: x, y, z em pixels)
///          Identity_1 [1, 1]   → handedness score
///          Identity_2 [1, 1]   → presence score
///          Identity_3 [1, 63]  → landmarks em coordenadas mundiais
use anyhow::{anyhow, Result};
use image::{imageops, RgbImage};
use ndarray::{Array4};
use ort::{inputs, session::Session, value::Tensor};

use crate::gesture::Landmark;

// ===== Constantes =====
const PALM_MODEL_PATH: &str = "assets/models/palm_detection_lite.onnx";
const LANDMARK_MODEL_PATH: &str = "assets/models/hand_landmark_lite.onnx";

const PALM_INPUT_SIZE: u32 = 192;
const LANDMARK_INPUT_SIZE: u32 = 224;  // OpenCV model usa 224, não 256
const PALM_SCORE_THRESHOLD: f32 = 0.5;
const NUM_LANDMARKS: usize = 21;

// BlazePalm: 18 valores por âncora, strides=[8,16,16,16], anchors_per_loc=[2,2,2,2]
const PALM_STRIDES: [u32; 4] = [8, 16, 16, 16];
const PALM_ANCHORS_PER_LOC: [u32; 4] = [2, 2, 2, 2];
const REG_STRIDE: usize = 18;

// ===== Tipos =====

#[derive(Debug, Clone)]
struct Detection {
    bbox: [f32; 4], // [x_min, y_min, x_max, y_max] normalizados [0,1]
    score: f32,
}

pub struct HandLandmarkResult {
    pub landmarks: Vec<Landmark>,
    pub is_right_hand: bool,
}

// ===== Sessão =====

pub struct InferenceSession {
    palm_session: Session,
    landmark_session: Session,
    anchors: Vec<[f32; 2]>,
}

impl InferenceSession {
    pub fn new() -> Result<Self> {
        let palm_session = Session::builder()
            .map_err(|e| anyhow!("Falha ao criar builder ONNX: {e}"))?
            .commit_from_file(PALM_MODEL_PATH)
            .map_err(|e| anyhow!("Falha ao carregar palm model: {e}\nExecute: bash scripts/download_models.sh"))?;

        let landmark_session = Session::builder()
            .map_err(|e| anyhow!("Falha ao criar builder ONNX: {e}"))?
            .commit_from_file(LANDMARK_MODEL_PATH)
            .map_err(|e| anyhow!("Falha ao carregar landmark model: {e}\nExecute: bash scripts/download_models.sh"))?;

        let anchors = generate_palm_anchors();
        Ok(Self { palm_session, landmark_session, anchors })
    }

    pub fn detect(&mut self, frame: &RgbImage) -> Result<Option<HandLandmarkResult>> {
        let det = match self.detect_palm(frame)? {
            Some(d) => d,
            None => return Ok(None),
        };
        Ok(Some(self.detect_landmarks(frame, &det)?))
    }

    // ===== Estágio 1: Palm Detection =====

    fn detect_palm(&mut self, frame: &RgbImage) -> Result<Option<Detection>> {
        // Pré-processamento: resize para 192×192, formato NHWC [1,192,192,3]
        let resized = imageops::resize(frame, PALM_INPUT_SIZE, PALM_INPUT_SIZE, imageops::FilterType::Nearest);
        let input = rgb_to_nhwc(&resized, PALM_INPUT_SIZE);
        let tensor = Tensor::from_array(input)
            .map_err(|e| anyhow!("Tensor palm: {e}"))?;

        let outputs = self.palm_session
            .run(inputs!["input_1" => tensor])
            .map_err(|e| anyhow!("Inferência palm: {e}"))?;

        // Regressors: Identity [1, 2016, 18]
        let reg_val = outputs.iter()
            .find(|(name, _)| *name == "Identity")
            .ok_or_else(|| anyhow!("Palm: output 'Identity' não encontrado"))?;
        let (_, reg_data) = reg_val.1.try_extract_tensor::<f32>()
            .map_err(|e| anyhow!("Extração regressors: {e}"))?;
        let reg_vec: Vec<f32> = reg_data.to_vec();

        // Classificators: Identity_1 [1, 2016, 1]
        let cls_val = outputs.iter()
            .find(|(name, _)| *name == "Identity_1")
            .ok_or_else(|| anyhow!("Palm: output 'Identity_1' não encontrado"))?;
        let (_, cls_data) = cls_val.1.try_extract_tensor::<f32>()
            .map_err(|e| anyhow!("Extração classificators: {e}"))?;
        let cls_vec: Vec<f32> = cls_data.to_vec();

        drop(outputs);

        let mut detections = self.decode_detections(&reg_vec, &cls_vec);
        if detections.is_empty() {
            return Ok(None);
        }
        detections.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap());
        Ok(Some(detections.remove(0)))
    }

    fn decode_detections(&self, reg: &[f32], cls: &[f32]) -> Vec<Detection> {
        let size = PALM_INPUT_SIZE as f32;
        let mut out = Vec::new();

        for i in 0..self.anchors.len() {
            let score = sigmoid(cls[i]);
            if score < PALM_SCORE_THRESHOLD {
                continue;
            }
            let [acx, acy] = self.anchors[i];
            let base = i * REG_STRIDE;
            let cx = reg[base] / size + acx;
            let cy = reg[base + 1] / size + acy;
            let w  = reg[base + 2] / size;
            let h  = reg[base + 3] / size;

            out.push(Detection {
                bbox: [
                    (cx - w * 0.5).max(0.0),
                    (cy - h * 0.5).max(0.0),
                    (cx + w * 0.5).min(1.0),
                    (cy + h * 0.5).min(1.0),
                ],
                score,
            });
        }
        out
    }

    // ===== Estágio 2: Hand Landmark =====

    fn detect_landmarks(&mut self, frame: &RgbImage, det: &Detection) -> Result<HandLandmarkResult> {
        let (fw, fh) = frame.dimensions();
        let [x0, y0, x1, y1] = det.bbox;

        // Margem de 25%
        let mx = (x1 - x0) * 0.25;
        let my = (y1 - y0) * 0.25;
        let px0 = ((x0 - mx) * fw as f32).max(0.0) as u32;
        let py0 = ((y0 - my) * fh as f32).max(0.0) as u32;
        let px1 = ((x1 + mx) * fw as f32).min(fw as f32) as u32;
        let py1 = ((y1 + my) * fh as f32).min(fh as f32) as u32;

        let cropped = imageops::crop_imm(frame, px0, py0, (px1 - px0).max(1), (py1 - py0).max(1)).to_image();
        // Resize para 224×224 (formato NHWC)
        let resized = imageops::resize(&cropped, LANDMARK_INPUT_SIZE, LANDMARK_INPUT_SIZE, imageops::FilterType::Triangle);

        let input = rgb_to_nhwc(&resized, LANDMARK_INPUT_SIZE);
        let tensor = Tensor::from_array(input)
            .map_err(|e| anyhow!("Tensor landmark: {e}"))?;

        let outputs = self.landmark_session
            .run(inputs!["input_1" => tensor])
            .map_err(|e| anyhow!("Inferência landmark: {e}"))?;

        // Landmarks: Identity [1, 63] → 21 × (x, y, z) em pixels [0, 224]
        let lm_val = outputs.iter()
            .find(|(name, _)| *name == "Identity")
            .ok_or_else(|| anyhow!("Landmark: output 'Identity' não encontrado"))?;
        let (_, lm_raw) = lm_val.1.try_extract_tensor::<f32>()
            .map_err(|e| anyhow!("Extração landmarks: {e}"))?;
        let lm_data: Vec<f32> = lm_raw.to_vec();

        // Handedness: Identity_1 [1, 1] → score > 0.5 = mão direita
        let is_right_hand = outputs.iter()
            .find(|(name, _)| *name == "Identity_1")
            .and_then(|(_, v)| {
                v.try_extract_tensor::<f32>()
                    .ok()
                    .map(|(_, d)| d.first().copied().unwrap_or(1.0) > 0.5)
            })
            .unwrap_or(true);

        drop(outputs);

        // Normaliza: coordenadas em pixels → [0.0, 1.0]
        let scale = LANDMARK_INPUT_SIZE as f32;
        let landmarks: Vec<Landmark> = (0..NUM_LANDMARKS)
            .map(|i| {
                let b = i * 3;
                Landmark {
                    x: lm_data[b] / scale,
                    y: lm_data[b + 1] / scale,
                    z: lm_data[b + 2] / scale,
                }
            })
            .collect();

        Ok(HandLandmarkResult { landmarks, is_right_hand })
    }
}

// ===== Helpers =====

fn sigmoid(x: f32) -> f32 {
    1.0 / (1.0 + (-x).exp())
}

/// Converte RgbImage → tensor NHWC [1, H, W, 3] normalizado [0.0, 1.0].
/// (Os modelos OpenCV/tf2onnx usam NHWC, diferente do padrão PyTorch NCHW)
fn rgb_to_nhwc(img: &RgbImage, size: u32) -> Array4<f32> {
    let s = size as usize;
    let mut t = Array4::<f32>::zeros((1, s, s, 3));
    for y in 0..s {
        for x in 0..s {
            let p = img.get_pixel(x as u32, y as u32);
            t[[0, y, x, 0]] = p[0] as f32 / 255.0; // R
            t[[0, y, x, 1]] = p[1] as f32 / 255.0; // G
            t[[0, y, x, 2]] = p[2] as f32 / 255.0; // B
        }
    }
    t
}

/// Gera âncoras SSD do BlazePalm (192×192, 2016 âncoras).
fn generate_palm_anchors() -> Vec<[f32; 2]> {
    let mut anchors = Vec::with_capacity(2016);
    let input_size = PALM_INPUT_SIZE as f32;
    for (idx, &stride) in PALM_STRIDES.iter().enumerate() {
        let fm = (input_size / stride as f32).ceil() as u32;
        for y in 0..fm {
            for x in 0..fm {
                for _ in 0..PALM_ANCHORS_PER_LOC[idx] {
                    anchors.push([
                        (x as f32 + 0.5) / fm as f32,
                        (y as f32 + 0.5) / fm as f32,
                    ]);
                }
            }
        }
    }
    anchors
}
