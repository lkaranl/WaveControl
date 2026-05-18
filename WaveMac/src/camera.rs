/// Módulo de câmera — captura frames via nokhwa (backend AVFoundation no macOS).
///
/// Substitui `cv2.VideoCapture` do Python com suporte nativo macOS.
use anyhow::{anyhow, Result};
use image::RgbImage;
use nokhwa::{
    pixel_format::RgbFormat,
    utils::{CameraIndex, RequestedFormat, RequestedFormatType},
    Camera,
};

pub struct CameraCapture {
    camera: Camera,
    index: u32,
}

impl CameraCapture {
    /// Procura e abre a primeira câmera disponível (índices 0-9).
    /// Port de `find_camera()` do Python com cache de índice.
    pub fn find_and_open() -> Result<Self> {
        println!("🔍 Procurando câmeras disponíveis...");

        for i in 0..10u32 {
            let index = CameraIndex::Index(i);
            let format =
                RequestedFormat::new::<RgbFormat>(RequestedFormatType::AbsoluteHighestResolution);

            match Camera::new(index, format) {
                Ok(mut camera) => {
                    if camera.open_stream().is_ok() {
                        println!("✅ Câmera encontrada no índice {}", i);
                        return Ok(Self { camera, index: i });
                    }
                }
                Err(_) => continue,
            }
        }

        Err(anyhow!(
            "Nenhuma câmera disponível encontrada.\n\
             Possíveis soluções:\n\
             • Conecte uma webcam USB\n\
             • Verifique se a câmera não está em uso por outro app\n\
             • Reinicie o sistema se necessário"
        ))
    }

    /// Captura um único frame e retorna como RgbImage.
    pub fn capture_frame(&mut self) -> Result<RgbImage> {
        let buffer = self
            .camera
            .frame()
            .map_err(|e| anyhow!("Falha ao capturar frame (câmera {}): {}", self.index, e))?;

        let image = buffer
            .decode_image::<RgbFormat>()
            .map_err(|e| anyhow!("Falha ao decodificar frame: {}", e))?;

        Ok(image)
    }

    pub fn camera_index(&self) -> u32 {
        self.index
    }
}

impl Drop for CameraCapture {
    fn drop(&mut self) {
        let _ = self.camera.stop_stream();
        println!("📷 Câmera {} desconectada", self.index);
    }
}

/// Lista todas as câmeras disponíveis no sistema.
/// Port de `list_cameras()` do Python.
pub fn list_cameras() {
    println!("🔍 Listando câmeras disponíveis...");
    let mut found = false;

    for i in 0..10u32 {
        let index = CameraIndex::Index(i);
        let format =
            RequestedFormat::new::<RgbFormat>(RequestedFormatType::AbsoluteHighestResolution);

        if let Ok(mut camera) = Camera::new(index, format) {
            if camera.open_stream().is_ok() {
                println!("   📷 Câmera {}: Disponível", i);
                let _ = camera.stop_stream();
                found = true;
            }
        }
    }

    if !found {
        println!("   ❌ Nenhuma câmera encontrada");
    }
    println!();
}
