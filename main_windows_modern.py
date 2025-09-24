#!/usr/bin/env python3
import cv2
import time
import mediapipe as mp
import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QPushButton, QSlider, QCheckBox,
                               QGroupBox, QGridLayout, QMessageBox, QFrame)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QSize
from PySide6.QtGui import QImage, QPixmap, QFont, QPalette, QColor
import threading
from pynput.keyboard import Key
from pynput import keyboard

# ===== Configurações =====
MIN_DET = 0.6
MIN_TRK = 0.6
CALIBRATION_S = 2.0     # tempo inicial para estabilizar câmera
DRAW = True             # mostrar janela com landmarks
CAM_INDEX = 0           # índice da webcam

# ===== Configurações de Zoom =====
DEFAULT_ZOOM = 1.0      # zoom padrão (sem zoom)
MIN_ZOOM = 1.0          # zoom mínimo
MAX_ZOOM = 4.0          # zoom máximo

# ===== Filtro Temporal =====
GESTURE_WINDOW_SIZE = 8  # número de frames para confirmar gesto
CONSISTENCY_THRESHOLD = 0.75  # 75% das amostras devem ser iguais

# ===== Dispositivo virtual (pynput para Windows) =====
kb_controller = keyboard.Controller()

# ===== MediaPipe =====
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
hands = mp_hands.Hands(
    max_num_hands=1,
    model_complexity=0,
    min_detection_confidence=MIN_DET,
    min_tracking_confidence=MIN_TRK,
)

# ===== Utilidades de dedos =====
TIP = { "thumb": 4, "index": 8, "middle": 12, "ring": 16, "pinky": 20 }
PIP = { "thumb": 3, "index": 6, "middle": 10, "ring": 14, "pinky": 18 }

def finger_extended(lm, tip_idx, pip_idx, handed_label):
    tip = lm[tip_idx]
    pip = lm[pip_idx]
    if tip_idx == TIP["thumb"]:
        if handed_label == "Right":
            return tip.x < pip.x - 0.05
        else:
            return tip.x > pip.x + 0.05
    return tip.y < pip.y - 0.05

def count_extended(lm, handed_label):
    cnt = 0
    for name in ["thumb","index","middle","ring","pinky"]:
        if finger_extended(lm, TIP[name], PIP[name], handed_label):
            cnt += 1
    return cnt

# ===== Histórico de Gestos =====
gesture_history = []

def add_gesture_to_history(gesture):
    gesture_history.append(gesture)
    if len(gesture_history) > GESTURE_WINDOW_SIZE:
        gesture_history.pop(0)

def get_stable_gesture():
    if len(gesture_history) < GESTURE_WINDOW_SIZE:
        return "neutral"
    
    gesture_counts = {}
    for gesture in gesture_history:
        gesture_counts[gesture] = gesture_counts.get(gesture, 0) + 1
    
    most_common_gesture = max(gesture_counts, key=gesture_counts.get)
    most_common_count = gesture_counts[most_common_gesture]
    
    consistency_ratio = most_common_count / len(gesture_history)
    
    if consistency_ratio >= CONSISTENCY_THRESHOLD and most_common_gesture != "neutral":
        return most_common_gesture
    
    return "neutral"

# ===== Gesto -> Ação =====
def classify_gesture(lm, handed_label):
    n = count_extended(lm, handed_label)
    if n == 1: return "next"      # um dedo levantado
    if n == 2: return "prev"      # dois dedos levantados
    if n == 3: return "home"      # três dedos levantados
    if n == 4: return "end"       # quatro dedos levantados
    return "neutral"

def press_next():
    kb_controller.press(Key.right)
    kb_controller.release(Key.right)

def press_prev():
    kb_controller.press(Key.left)
    kb_controller.release(Key.left)

def press_home():
    kb_controller.press(Key.home)
    kb_controller.release(Key.home)

def press_end():
    kb_controller.press(Key.end)
    kb_controller.release(Key.end)

def apply_digital_zoom(frame, zoom_level):
    if zoom_level <= 1.0:
        return frame
    
    height, width = frame.shape[:2]
    crop_width = int(width / zoom_level)
    crop_height = int(height / zoom_level)
    
    start_x = (width - crop_width) // 2
    start_y = (height - crop_height) // 2
    end_x = start_x + crop_width
    end_y = start_y + crop_height
    
    cropped = frame[start_y:end_y, start_x:end_x]
    zoomed = cv2.resize(cropped, (width, height), interpolation=cv2.INTER_LINEAR)
    
    return zoomed

# ===== Thread de Processamento de Vídeo =====
class VideoThread(QThread):
    frame_ready = Signal(QImage)
    status_update = Signal(str, str)  # status_text, color
    gesture_update = Signal(str)
    filter_update = Signal(str)
    
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.is_running = False
        self.cap = None
        self.start_ts = None
        self.action_executed = False
        self.last_action = "neutral"
    
    def start_capture(self):
        global gesture_history
        gesture_history.clear()
        
        self.cap = cv2.VideoCapture(CAM_INDEX)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 800)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 600)
        
        if not self.cap.isOpened():
            return False
        
        self.is_running = True
        self.start_ts = time.time()
        self.start()
        return True
    
    def stop_capture(self):
        self.is_running = False
        if self.cap:
            self.cap.release()
        self.wait()
    
    def run(self):
        while self.is_running and self.cap and self.cap.isOpened():
            ok, frame = self.cap.read()
            if not ok:
                break
            
            frame = cv2.flip(frame, 1)
            frame = apply_digital_zoom(frame, self.parent.zoom_slider.value() / 10.0)
            
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = hands.process(rgb)
            
            raw_action = "neutral"
            handed = "Right"
            
            if res.multi_hand_landmarks:
                lm = res.multi_hand_landmarks[0]
                if res.multi_handedness and len(res.multi_handedness) > 0:
                    handed = res.multi_handedness[0].classification[0].label
                raw_action = classify_gesture(lm.landmark, handed)
            
            add_gesture_to_history(raw_action)
            action = get_stable_gesture()
            
            # Desenha landmarks se habilitado
            if res.multi_hand_landmarks and self.parent.landmarks_check.isChecked():
                lm = res.multi_hand_landmarks[0]
                mp_drawing.draw_landmarks(
                    frame, lm, mp_hands.HAND_CONNECTIONS,
                    mp_drawing.DrawingSpec(color=(0,255,0), thickness=2, circle_radius=2),
                    mp_drawing.DrawingSpec(color=(255,0,0), thickness=2)
                )
            
            now = time.time()
            
            # Informações na tela
            zoom_level = self.parent.zoom_slider.value() / 10.0
            if zoom_level > 1.0:
                zoom_text = f"Zoom: {zoom_level:.1f}x"
                cv2.putText(frame, zoom_text, (20, frame.shape[0] - 20), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)
            
            # Calibração
            if now - self.start_ts < CALIBRATION_S:
                cv2.putText(frame, "Calibrando...", (20,40), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
                self.status_update.emit("Calibrando...", "#ff8c00")
            else:
                # Executa ações
                if action == "neutral":
                    if self.action_executed:
                        self.action_executed = False
                        self.status_update.emit("Sistema ativo", "#107c10")
                elif action != "neutral" and not self.action_executed:
                    if action == "next":
                        press_next()
                        self.status_update.emit("Próximo →", "#0078d4")
                    elif action == "prev":
                        press_prev()
                        self.status_update.emit("← Anterior", "#0078d4")
                    elif action == "home":
                        press_home()
                        self.status_update.emit("⏮ Início", "#0078d4")
                    elif action == "end":
                        press_end()
                        self.status_update.emit("⏭ Fim", "#0078d4")
                    self.action_executed = True
                    self.last_action = action
                elif action != "neutral" and self.action_executed:
                    self.status_update.emit("Aguardando...", "#ff8c00")
            
            # Atualiza indicadores
            self.gesture_update.emit(action)
            self.filter_update.emit(f"{len(gesture_history)}/{GESTURE_WINDOW_SIZE}")
            
            # Converte frame para QImage
            height, width, channel = frame.shape
            bytes_per_line = 3 * width
            q_image = QImage(rgb.data, width, height, bytes_per_line, QImage.Format_RGB888)
            
            self.frame_ready.emit(q_image)
            
            time.sleep(0.03)  # ~30 FPS

# ===== Interface Principal PySide6 =====
class WaveControlWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WaveControl - Windows Modern")
        self.setGeometry(100, 100, 1200, 700)
        self.setMinimumSize(800, 600)
        
        # Aplicar tema moderno
        self.setup_style()
        
        # Thread de vídeo
        self.video_thread = VideoThread(self)
        self.video_thread.frame_ready.connect(self.update_frame)
        self.video_thread.status_update.connect(self.update_status)
        self.video_thread.gesture_update.connect(self.update_gesture)
        self.video_thread.filter_update.connect(self.update_filter)
        
        # Interface
        self.setup_ui()
        
        # Auto-start
        QTimer.singleShot(100, self.start_detection)
    
    def setup_style(self):
        """Aplica estilo moderno do Windows"""
        app = QApplication.instance()
        
        # Paleta de cores moderna
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(240, 240, 240))
        palette.setColor(QPalette.WindowText, QColor(0, 0, 0))
        palette.setColor(QPalette.Base, QColor(255, 255, 255))
        palette.setColor(QPalette.AlternateBase, QColor(245, 245, 245))
        palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 220))
        palette.setColor(QPalette.ToolTipText, QColor(0, 0, 0))
        palette.setColor(QPalette.Text, QColor(0, 0, 0))
        palette.setColor(QPalette.Button, QColor(240, 240, 240))
        palette.setColor(QPalette.ButtonText, QColor(0, 0, 0))
        palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
        palette.setColor(QPalette.Link, QColor(0, 120, 212))
        palette.setColor(QPalette.Highlight, QColor(0, 120, 212))
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        
        app.setPalette(palette)
        
        # Estilo CSS moderno
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            
            QGroupBox {
                font-weight: bold;
                font-size: 11px;
                border: 2px solid #d1d1d1;
                border-radius: 8px;
                margin-top: 1ex;
                padding-top: 10px;
                background-color: white;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #0078d4;
            }
            
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 11px;
            }
            
            QPushButton:hover {
                background-color: #106ebe;
            }
            
            QPushButton:pressed {
                background-color: #005a9e;
            }
            
            QPushButton#stopButton {
                background-color: #d13438;
            }
            
            QPushButton#stopButton:hover {
                background-color: #b71c1c;
            }
            
            QSlider::groove:horizontal {
                border: 1px solid #999999;
                height: 8px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #B1B1B1, stop:1 #c4c4c4);
                margin: 2px 0;
                border-radius: 4px;
            }
            
            QSlider::handle:horizontal {
                background: #0078d4;
                border: 1px solid #5c5c5c;
                width: 18px;
                margin: -2px 0;
                border-radius: 9px;
            }
            
            QSlider::handle:horizontal:hover {
                background: #106ebe;
            }
            
            QLabel#titleLabel {
                font-size: 18px;
                font-weight: bold;
                color: #0078d4;
            }
            
            QLabel#statusLabel {
                font-size: 12px;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
                background-color: #ff8c00;
                color: white;
            }
            
            QLabel#gestureLabel, QLabel#filterLabel {
                font-size: 10px;
                font-weight: bold;
                padding: 2px 6px;
                border-radius: 3px;
                background-color: #107c10;
                color: white;
            }
            
            QCheckBox {
                font-size: 10px;
            }
            
            QFrame#videoFrame {
                border: 2px solid #d1d1d1;
                border-radius: 8px;
                background-color: white;
            }
        """)
    
    def setup_ui(self):
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        # ===== HEADER =====
        header_layout = QHBoxLayout()
        
        # Título e status
        header_left = QVBoxLayout()
        title_label = QLabel("WaveControl - Windows Modern")
        title_label.setObjectName("titleLabel")
        
        self.status_label = QLabel("Sistema parado")
        self.status_label.setObjectName("statusLabel")
        
        header_left.addWidget(title_label)
        header_left.addWidget(self.status_label)
        header_left.addStretch()
        
        # Botão de controle
        self.start_button = QPushButton("▶ Iniciar")
        self.start_button.setMinimumSize(120, 40)
        self.start_button.clicked.connect(self.toggle_detection)
        
        header_layout.addLayout(header_left)
        header_layout.addStretch()
        header_layout.addWidget(self.start_button)
        
        main_layout.addLayout(header_layout)
        
        # ===== CONTEÚDO PRINCIPAL =====
        content_layout = QHBoxLayout()
        
        # ===== SIDEBAR =====
        sidebar_layout = QVBoxLayout()
        sidebar_layout.setSpacing(10)
        
        # Card de Gestos
        gestures_group = QGroupBox("Gestos")
        gestures_layout = QVBoxLayout(gestures_group)
        
        gestures = [
            "👆 1 dedo → Próximo (→)",
            "✌️ 2 dedos → Anterior (←)",
            "🤟 3 dedos → Início (Home)",
            "🖖 4 dedos → Fim (End)",
            "✊ 0 dedos → Neutro"
        ]
        
        for gesture in gestures:
            label = QLabel(gesture)
            label.setFont(QFont("Arial", 9))
            gestures_layout.addWidget(label)
        
        # Card de Zoom
        zoom_group = QGroupBox("Zoom Digital")
        zoom_layout = QVBoxLayout(zoom_group)
        
        self.zoom_value_label = QLabel(f"{DEFAULT_ZOOM:.1f}x")
        self.zoom_value_label.setFont(QFont("Arial", 11, QFont.Bold))
        
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(int(MIN_ZOOM * 10), int(MAX_ZOOM * 10))
        self.zoom_slider.setValue(int(DEFAULT_ZOOM * 10))
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
        
        # Botões de zoom
        zoom_buttons_layout = QHBoxLayout()
        for zoom in [1.0, 2.0, 3.0, 4.0]:
            btn = QPushButton(f"{zoom:.0f}x")
            btn.setMaximumWidth(50)
            btn.clicked.connect(lambda checked, z=zoom: self.set_zoom(z))
            zoom_buttons_layout.addWidget(btn)
        
        zoom_layout.addWidget(self.zoom_value_label)
        zoom_layout.addWidget(self.zoom_slider)
        zoom_layout.addLayout(zoom_buttons_layout)
        
        # Card de Status
        status_group = QGroupBox("Status do Sistema")
        status_layout = QGridLayout(status_group)
        
        status_layout.addWidget(QLabel("Gesto:"), 0, 0)
        self.gesture_label = QLabel("neutral")
        self.gesture_label.setObjectName("gestureLabel")
        status_layout.addWidget(self.gesture_label, 0, 1)
        
        status_layout.addWidget(QLabel("Filtro:"), 1, 0)
        self.filter_label = QLabel("0/8")
        self.filter_label.setObjectName("filterLabel")
        status_layout.addWidget(self.filter_label, 1, 1)
        
        # Card de Configurações
        config_group = QGroupBox("Configurações")
        config_layout = QVBoxLayout(config_group)
        
        self.landmarks_check = QCheckBox("Mostrar landmarks")
        self.landmarks_check.setChecked(DRAW)
        config_layout.addWidget(self.landmarks_check)
        
        # Adicionar todos os cards à sidebar
        sidebar_layout.addWidget(gestures_group)
        sidebar_layout.addWidget(zoom_group)
        sidebar_layout.addWidget(status_group)
        sidebar_layout.addWidget(config_group)
        sidebar_layout.addStretch()
        
        # ===== ÁREA DE VÍDEO =====
        video_frame = QFrame()
        video_frame.setObjectName("videoFrame")
        video_frame.setMinimumSize(400, 300)
        
        video_layout = QVBoxLayout(video_frame)
        
        self.video_label = QLabel("📷\n\nCâmera não ativada\n\nClique em 'Iniciar' para começar")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setFont(QFont("Arial", 14))
        self.video_label.setStyleSheet("color: #666; background: transparent; border: none;")
        
        video_layout.addWidget(self.video_label)
        
        # Adicionar sidebar e vídeo ao layout
        content_layout.addLayout(sidebar_layout, 0)
        content_layout.addWidget(video_frame, 1)
        
        main_layout.addLayout(content_layout)
        
        # ===== RODAPÉ =====
        footer_label = QLabel("WaveControl Windows Modern - Controle por gestos | Criado por Karan Luciano")
        footer_label.setAlignment(Qt.AlignCenter)
        footer_label.setFont(QFont("Arial", 9))
        footer_label.setStyleSheet("color: #666;")
        
        main_layout.addWidget(footer_label)
    
    def on_zoom_changed(self, value):
        zoom_val = value / 10.0
        self.zoom_value_label.setText(f"{zoom_val:.1f}x")
    
    def set_zoom(self, zoom_value):
        self.zoom_slider.setValue(int(zoom_value * 10))
        self.zoom_value_label.setText(f"{zoom_value:.1f}x")
    
    def toggle_detection(self):
        if not self.video_thread.is_running:
            self.start_detection()
        else:
            self.stop_detection()
    
    def start_detection(self):
        if self.video_thread.start_capture():
            self.start_button.setText("⏹ Parar")
            self.start_button.setObjectName("stopButton")
            self.start_button.setStyle(self.start_button.style())  # Reaplica estilo
            self.status_label.setText("Calibrando...")
            self.status_label.setStyleSheet("background-color: #ff8c00; color: white;")
        else:
            QMessageBox.critical(self, "Erro", "Não foi possível acessar a câmera.\nVerifique se está conectada e disponível.")
    
    def stop_detection(self):
        self.video_thread.stop_capture()
        self.start_button.setText("▶ Iniciar")
        self.start_button.setObjectName("")
        self.start_button.setStyle(self.start_button.style())  # Reaplica estilo
        self.status_label.setText("Sistema parado")
        self.status_label.setStyleSheet("background-color: #ff8c00; color: white;")
        
        # Reset vídeo
        self.video_label.setText("📷\n\nCâmera não ativada\n\nClique em 'Iniciar' para começar")
        self.video_label.setPixmap(QPixmap())
        
        # Reset indicadores
        self.gesture_label.setText("neutral")
        self.filter_label.setText("0/8")
    
    def update_frame(self, q_image):
        # Redimensiona mantendo proporção
        label_size = self.video_label.size()
        scaled_pixmap = QPixmap.fromImage(q_image).scaled(
            label_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        self.video_label.setPixmap(scaled_pixmap)
        self.video_label.setText("")  # Remove texto placeholder
    
    def update_status(self, text, color):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"background-color: {color}; color: white;")
    
    def update_gesture(self, gesture):
        self.gesture_label.setText(gesture)
    
    def update_filter(self, filter_text):
        self.filter_label.setText(filter_text)
    
    def closeEvent(self, event):
        self.stop_detection()
        if hands:
            hands.close()
        event.accept()

# ===== Execução Principal =====
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("WaveControl Windows Modern")
    app.setApplicationVersion("1.0")
    
    # Define estilo nativo do Windows
    app.setStyle('windowsvista')
    
    window = WaveControlWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
