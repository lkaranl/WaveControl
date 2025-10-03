#!/usr/bin/env python3
import cv2
import time
import sys
import mediapipe as mp
import threading
from functools import lru_cache
from collections import Counter, deque
from datetime import datetime
from pynput.keyboard import Key
from pynput import keyboard
import base64
from io import BytesIO
from PIL import Image as PILImage

# Flet imports
import flet as ft

# Analytics
from analytics import get_analytics

# ===== Sistema de Logs =====
class Logger:
    @staticmethod
    def banner():
        print("\n" + "="*60)
        print("  🌊 WaveControl - Flet Edition")
        print("  Versão: 3.0.0")
        print("  Por: Karan Luciano")
        print("="*60)
        
    @staticmethod
    def info(message, component="SISTEMA"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] ℹ️  [{component}] {message}")
    
    @staticmethod
    def success(message, component="SISTEMA"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] ✅ [{component}] {message}")
    
    @staticmethod
    def warning(message, component="SISTEMA"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] ⚠️  [{component}] {message}")
    
    @staticmethod
    def error(message, component="SISTEMA"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] ❌ [{component}] {message}")
    
    @staticmethod
    def section(title):
        print(f"\n{'─'*60}")
        print(f"  {title}")
        print(f"{'─'*60}")

log = Logger()

# ===== Configurações =====
MIN_DET = 0.6
MIN_TRK = 0.6
CALIBRATION_S = 2.0
DRAW = True
CAM_INDEX = 0
TARGET_FPS = 30
ACTION_COOLDOWN_S = 0.8

# Zoom
DEFAULT_ZOOM = 1.0
MIN_ZOOM = 1.0
MAX_ZOOM = 4.0

# Filtro Temporal
GESTURE_WINDOW_SIZE = 9
CONSISTENCY_THRESHOLD = 0.78

# ===== Backend de Teclado =====
log.section("Inicializando Backend de Teclado")
log.info("Usando pynput para emulação de teclado (Windows)", "BACKEND")
kb_controller = keyboard.Controller()
log.success("pynput inicializado com sucesso", "BACKEND")

# ===== MediaPipe =====
log.section("Inicializando MediaPipe")
log.info("Carregando modelo de detecção de mãos...", "MEDIAPIPE")

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

@lru_cache(maxsize=1)
def get_mediapipe_hands():
    return mp_hands.Hands(
        max_num_hands=1,
        model_complexity=0,
        min_detection_confidence=MIN_DET,
        min_tracking_confidence=MIN_TRK,
    )

hands = get_mediapipe_hands()
log.success(f"MediaPipe inicializado", "MEDIAPIPE")

_LANDMARK_DRAWING_SPEC = mp_drawing.DrawingSpec(color=(0,255,0), thickness=2, circle_radius=2)
_CONNECTION_DRAWING_SPEC = mp_drawing.DrawingSpec(color=(255,0,0), thickness=2)

# ===== Utilidades de dedos =====
TIP = { "thumb": 4, "index": 8, "middle": 12, "ring": 16, "pinky": 20 }
PIP = { "thumb": 3, "index": 6, "middle": 10, "ring": 14, "pinky": 18 }
MCP = { "index": 5, "middle": 9, "ring": 13, "pinky": 17 }

_THUMB_THRESHOLD = 0.05
_FINGER_THRESHOLD = 0.06
_INDEX_THRESHOLD = 0.03

def finger_extended(lm, tip_idx, pip_idx, handed_label):
    tip = lm[tip_idx]
    pip = lm[pip_idx]
    
    if tip_idx == TIP["thumb"]:
        ip_joint = lm[3]
        mcp_joint = lm[2]
        if handed_label == "Right":
            return tip.x < ip_joint.x - _THUMB_THRESHOLD and tip.x < mcp_joint.x
        else:
            return tip.x > ip_joint.x + _THUMB_THRESHOLD and tip.x > mcp_joint.x
    else:
        finger_name = None
        for name, idx in TIP.items():
            if idx == tip_idx:
                finger_name = name
                break
        
        threshold = _INDEX_THRESHOLD if finger_name == "index" else _FINGER_THRESHOLD
        
        if finger_name and finger_name in MCP:
            mcp = lm[MCP[finger_name]]
            tip_above_pip = tip.y < pip.y - threshold
            mcp_tolerance = 0.05 if finger_name == "index" else 0.03
            tip_above_mcp = tip.y < mcp.y + mcp_tolerance
            return tip_above_pip and tip_above_mcp
        
        return tip.y < pip.y - threshold

_FINGER_NAMES = ("thumb", "index", "middle", "ring", "pinky")

def get_extended_fingers(lm, handed_label):
    extended = []
    for name in _FINGER_NAMES:
        if finger_extended(lm, TIP[name], PIP[name], handed_label):
            extended.append(name)
    return extended

# ===== Histórico de Gestos =====
gesture_history = deque(maxlen=GESTURE_WINDOW_SIZE)
_last_gesture_counts = None
_last_history_snapshot = None

def _get_gesture_counts():
    global _last_gesture_counts, _last_history_snapshot
    current_snapshot = tuple(gesture_history)
    if current_snapshot == _last_history_snapshot and _last_gesture_counts is not None:
        return _last_gesture_counts
    _last_gesture_counts = Counter(gesture_history)
    _last_history_snapshot = current_snapshot
    return _last_gesture_counts

def add_gesture_to_history(gesture):
    gesture_history.append(gesture)

def get_stable_gesture():
    if len(gesture_history) < 4:
        return "neutral"
    gesture_counts = _get_gesture_counts()
    most_common_gesture, most_common_count = gesture_counts.most_common(1)[0]
    consistency_ratio = most_common_count / len(gesture_history)
    threshold = CONSISTENCY_THRESHOLD
    if most_common_gesture == "neutral":
        threshold = 0.5
    elif most_common_gesture == "next":
        threshold = 0.67
    if consistency_ratio >= threshold and most_common_gesture != "neutral":
        return most_common_gesture
    return "neutral"

def get_gesture_confidence():
    if len(gesture_history) < GESTURE_WINDOW_SIZE:
        return 0.0
    gesture_counts = _get_gesture_counts()
    most_common_gesture, most_common_count = gesture_counts.most_common(1)[0]
    confidence = (most_common_count / GESTURE_WINDOW_SIZE) * 100
    return confidence

# ===== Gesto -> Ação =====
_GESTURE_MAP = {
    1: "next",
    2: "prev",
    3: "home",
    4: "end",
}

def classify_gesture(lm, handed_label):
    extended_fingers = get_extended_fingers(lm, handed_label)
    index_extended = "index" in extended_fingers
    middle_closed = "middle" not in extended_fingers
    ring_closed = "ring" not in extended_fingers
    pinky_closed = "pinky" not in extended_fingers
    
    if index_extended and middle_closed and ring_closed and pinky_closed:
        return "next"
    
    n = len(extended_fingers)
    return _GESTURE_MAP.get(n, "neutral")

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

def apply_manual_zoom(frame, zoom_level):
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

# ===== Aplicação Flet =====
class WaveControlApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "WaveControl - Flet Edition"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 0
        
        # Cores do tema
        self.colors = {
            'next': "#26A69A",      # Teal 400
            'prev': "#42A5F5",      # Blue 400
            'home': "#AB47BC",      # Purple 400
            'end': "#FFA726",       # Orange 400
            'neutral': "#757575"    # Grey 600
        }
        
        self.gesture_emojis = {
            'next': '👆',
            'prev': '✌️',
            'home': '🤟',
            'end': '🖖',
            'neutral': '✊'
        }
        
        # Estado
        self.is_running = False
        self.cap = None
        self.start_ts = None
        self.last_action = "neutral"
        self.action_executed = False
        self.last_action_time = 0
        self.zoom_level = DEFAULT_ZOOM
        self.current_gesture = "neutral"
        self.fps = 0.0
        
        self._rgb_buffer = None
        self.analytics = get_analytics()
        
        # UI Components
        self.video_image = ft.Image(
            src_base64="",
            width=800,
            height=600,
            fit=ft.ImageFit.CONTAIN,
            border_radius=ft.border_radius.all(16),
            visible=False  # Esconde até ter conteúdo
        )
        
        self.gesture_label = ft.Text(
            f"{self.gesture_emojis['neutral']} neutral",
            size=48,
            weight=ft.FontWeight.BOLD,
            color=self.colors['neutral']
        )
        
        self.status_text = ft.Text(
            "Sistema parado",
            size=14,
            color="#FFA726"  # Orange 400
        )
        
        self.fps_text = ft.Text("0.0", size=20, weight=ft.FontWeight.BOLD, color="#42A5F5")  # Blue 400
        
        self.zoom_slider = ft.Slider(
            min=MIN_ZOOM,
            max=MAX_ZOOM,
            value=DEFAULT_ZOOM,
            divisions=30,
            label="{value}x",
            on_change=self.on_zoom_change
        )
        
        self.zoom_value_text = ft.Text(f"{DEFAULT_ZOOM:.1f}x", size=16, weight=ft.FontWeight.BOLD)
        
        self.start_button = ft.ElevatedButton(
            "Iniciar",
            icon="play_arrow",
            on_click=self.toggle_detection,
            style=ft.ButtonStyle(
                color="#FFFFFF",  # White
                bgcolor="#1976D2"  # Blue 700
            )
        )
        
        # Build UI
        self.build_ui()
        
        # Auto-start após carregar
        self.page.on_route_change = None  # Placeholder para garantir que page está pronta
        # Agenda auto-start para depois da UI carregar
        import time as timer_module
        def auto_start():
            timer_module.sleep(0.5)  # Aguarda 500ms para UI ficar pronta
            if not self.is_running:
                self.start_detection()
        
        threading.Thread(target=auto_start, daemon=True).start()
    
    def build_ui(self):
        # AppBar
        appbar = ft.AppBar(
            title=ft.Text("WaveControl", size=24, weight=ft.FontWeight.BOLD),
            center_title=False,
            bgcolor="#1976D2",  # Blue 700
            actions=[self.start_button]
        )
        
        # Sidebar - Gestos
        gestures_card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Text("Gesto Atual", size=12, color="#9E9E9E"),  # Grey 500
                    self.gesture_label,
                    ft.Divider(height=1, color="#424242"),  # Grey 800
                    ft.Text("Gestos Disponíveis", size=16, weight=ft.FontWeight.BOLD),
                    self.create_gesture_chip("👆 1 dedo → Próximo", "arrow_forward"),
                    self.create_gesture_chip("✌️ 2 dedos → Anterior", "arrow_back"),
                    self.create_gesture_chip("🤟 3 dedos → Início", "home"),
                    self.create_gesture_chip("🖖 4 dedos → Fim", "arrow_downward"),
                    self.create_gesture_chip("✊ 0 dedos → Neutro", "back_hand"),
                ], spacing=10),
                padding=20
            ),
            elevation=2
        )
        
        # Sidebar - Zoom
        zoom_card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Text("Zoom Digital", size=16, weight=ft.FontWeight.BOLD),
                        self.zoom_value_text
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    self.zoom_slider,
                    ft.Row([
                        ft.TextButton("1x", on_click=lambda _: self.set_zoom(1.0)),
                        ft.TextButton("2x", on_click=lambda _: self.set_zoom(2.0)),
                        ft.TextButton("3x", on_click=lambda _: self.set_zoom(3.0)),
                        ft.TextButton("4x", on_click=lambda _: self.set_zoom(4.0)),
                    ], alignment=ft.MainAxisAlignment.SPACE_AROUND)
                ], spacing=10),
                padding=20
            ),
            elevation=2
        )
        
        # Sidebar - Status
        status_card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Text("Status do Sistema", size=16, weight=ft.FontWeight.BOLD),
                    ft.Divider(height=1, color="#424242"),  # Grey 800
                    ft.Row([
                        ft.Text("FPS:", size=14),
                        self.fps_text
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Row([
                        ft.Text("Status:", size=14),
                        self.status_text
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ], spacing=10),
                padding=20
            ),
            elevation=2
        )
        
        # Sidebar completa
        sidebar = ft.Container(
            content=ft.Column([
                gestures_card,
                zoom_card,
                status_card
            ], spacing=15, scroll=ft.ScrollMode.AUTO),
            width=320,
            padding=15
        )
        
        # Área de vídeo
        video_placeholder = ft.Container(
            content=ft.Column([
                ft.Icon(name="videocam_off", size=80, color="#616161"),  # Grey 700
                ft.Text("Câmera não ativada", size=20, color="#9E9E9E"),  # Grey 500
                ft.Text("Clique em 'Iniciar' para começar", size=14, color="#757575")  # Grey 600
            ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            alignment=ft.alignment.center,
            expand=True
        )
        
        self.video_container = ft.Stack([
            video_placeholder,
            self.video_image
        ], expand=True)
        
        video_area = ft.Card(
            content=ft.Container(
                content=self.video_container,
                padding=20,
                expand=True
            ),
            elevation=4,
            expand=True
        )
        
        # Layout principal
        main_content = ft.Row([
            sidebar,
            video_area
        ], expand=True, spacing=15)
        
        # Footer
        footer = ft.Container(
            content=ft.Row([
                ft.Text("WaveControl - Controle por gestos | Criado por Karan Luciano", 
                       size=12, color="#757575"),  # Grey 600
                ft.Text("🖥️ Windows (pynput)", size=12, color="#757575")  # Grey 600
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            padding=ft.padding.only(left=20, right=20, top=10, bottom=10),
            bgcolor="#2C2C2C"  # Surface variant dark
        )
        
        # Adiciona tudo à página
        self.page.appbar = appbar
        self.page.add(
            ft.Container(
                content=ft.Column([
                    main_content,
                    footer
                ], expand=True, spacing=0),
                expand=True
            )
        )
    
    def create_gesture_chip(self, text, icon):
        return ft.Container(
            content=ft.Row([
                ft.Icon(icon, size=20),
                ft.Text(text, size=14)
            ], spacing=10),
            padding=10,
            border_radius=8,
            bgcolor="#2C2C2C"  # Surface variant dark
        )
    
    def on_zoom_change(self, e):
        self.zoom_level = e.control.value
        self.zoom_value_text.value = f"{self.zoom_level:.1f}x"
        self.page.update()
    
    def set_zoom(self, value):
        self.zoom_level = value
        self.zoom_slider.value = value
        self.zoom_value_text.value = f"{value:.1f}x"
        self.page.update()
    
    def toggle_detection(self, e):
        if not self.is_running:
            self.start_detection()
        else:
            self.stop_detection()
    
    def start_detection(self):
        global gesture_history
        gesture_history.clear()
        
        log.section("Iniciando Detecção de Gestos")
        log.info(f"Abrindo câmera (índice: {CAM_INDEX})...", "CAMERA")
        
        self.cap = cv2.VideoCapture(CAM_INDEX)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 800)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 600)
        
        if not self.cap.isOpened():
            log.error("Falha ao acessar a câmera", "CAMERA")
            return
        
        log.success("Câmera aberta com sucesso", "CAMERA")
        self.is_running = True
        self.start_ts = time.time()
        
        self.analytics.start_session()
        self.analytics.set_calibration_time(CALIBRATION_S)
        
        self.start_button.text = "Parar"
        self.start_button.icon = "stop"
        self.start_button.style.bgcolor = "#D32F2F"  # Red 700
        
        # Mostra o vídeo e esconde placeholder
        self.video_image.visible = True
        
        self.page.update()
        
        # Inicia thread de processamento
        self.processing_thread = threading.Thread(target=self.process_video, daemon=True)
        self.processing_thread.start()
    
    def stop_detection(self):
        log.section("Parando Detecção de Gestos")
        self.is_running = False
        
        self.analytics.end_session()
        
        if self.cap:
            self.cap.release()
            log.info("Câmera liberada", "CAMERA")
        
        self.start_button.text = "Iniciar"
        self.start_button.icon = "play_arrow"
        self.start_button.style.bgcolor = "#1976D2"  # Blue 700
        
        self.status_text.value = "Sistema parado"
        self.status_text.color = "#FFA726"  # Orange 400
        
        # Esconde o vídeo
        self.video_image.src_base64 = ""
        self.video_image.visible = False
        
        self.page.update()
        
        log.section("Estatísticas da Sessão")
        self.analytics.print_stats()
    
    def process_video(self):
        frame_time = 1.0 / TARGET_FPS
        last_frame_time = time.time()
        
        while self.is_running and self.cap and self.cap.isOpened():
            current_time = time.time()
            elapsed = current_time - last_frame_time
            if elapsed < frame_time:
                time.sleep(frame_time - elapsed)
            last_frame_time = time.time()
            
            ok, frame = self.cap.read()
            if not ok:
                break
            
            frame = cv2.flip(frame, 1)
            
            if self._rgb_buffer is None or self._rgb_buffer.shape != frame.shape:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self._rgb_buffer = rgb
            else:
                cv2.cvtColor(frame, cv2.COLOR_BGR2RGB, dst=self._rgb_buffer)
                rgb = self._rgb_buffer
            
            res = hands.process(rgb)
            
            if self.zoom_level > 1.0:
                frame = apply_manual_zoom(frame, self.zoom_level)
            
            raw_action = "neutral"
            handed = "Right"
            
            if res.multi_hand_landmarks:
                lm = res.multi_hand_landmarks[0]
                if res.multi_handedness and len(res.multi_handedness) > 0:
                    handed = res.multi_handedness[0].classification[0].label
                raw_action = classify_gesture(lm.landmark, handed)
                
                if DRAW:
                    mp_drawing.draw_landmarks(
                        frame, lm, mp_hands.HAND_CONNECTIONS,
                        _LANDMARK_DRAWING_SPEC,
                        _CONNECTION_DRAWING_SPEC
                    )
            
            add_gesture_to_history(raw_action)
            action = get_stable_gesture()
            gesture_confidence = get_gesture_confidence()
            
            now = time.time()
            
            # Atualiza UI
            self.current_gesture = action
            self.gesture_label.value = f"{self.gesture_emojis[action]} {action}"
            self.gesture_label.color = self.colors[action]
            
            # Calibração
            if now - self.start_ts < CALIBRATION_S:
                cv2.putText(frame, "Calibrando...", (20,40), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (220,220,170), 2)
                self.status_text.value = "Calibrando..."
                self.status_text.color = "#FBC02D"  # Yellow 700
            else:
                time_since_last_action = now - self.last_action_time
                
                if action == "neutral":
                    if self.action_executed:
                        self.action_executed = False
                        self.status_text.value = "✓ Sistema ativo"
                        self.status_text.color = "#66BB6A"  # Green 400
                elif action != "neutral" and not self.action_executed:
                    if time_since_last_action >= ACTION_COOLDOWN_S:
                        if action == "next":
                            press_next()
                            self.analytics.record_gesture("next")
                            self.status_text.value = "→ Próximo"
                            self.status_text.color = self.colors['next']
                        elif action == "prev":
                            press_prev()
                            self.analytics.record_gesture("prev")
                            self.status_text.value = "← Anterior"
                            self.status_text.color = self.colors['prev']
                        elif action == "home":
                            press_home()
                            self.analytics.record_gesture("home")
                            self.status_text.value = "⇤ Início"
                            self.status_text.color = self.colors['home']
                        elif action == "end":
                            press_end()
                            self.analytics.record_gesture("end")
                            self.status_text.value = "⇥ Fim"
                            self.status_text.color = self.colors['end']
                        
                        self.action_executed = True
                        self.last_action = action
                        self.last_action_time = now
                        
                        log.success(f"Comando: {action} ({gesture_confidence:.0f}%)", "GESTO")
            
            # Atualiza FPS
            stats = self.analytics.get_stats_summary()
            self.fps = stats['performance']['fps']
            self.fps_text.value = f"{self.fps:.1f}"
            
            # Converte frame para base64
            _, buffer = cv2.imencode('.jpg', frame)
            img_base64 = base64.b64encode(buffer).decode()
            self.video_image.src_base64 = img_base64
            
            # Atualiza página
            self.page.update()

def main():
    log.banner()
    
    log.section("Informações do Sistema")
    log.info(f"Sistema Operacional: {sys.platform}", "SISTEMA")
    log.info(f"Python: {sys.version.split()[0]}", "SISTEMA")
    log.info(f"OpenCV: {cv2.__version__}", "SISTEMA")
    log.info(f"MediaPipe: {mp.__version__}", "SISTEMA")
    
    log.section("Iniciando Interface Gráfica Flet")
    log.info("Carregando componentes...", "GUI")
    
    try:
        ft.app(target=WaveControlApp)
    except KeyboardInterrupt:
        log.warning("Interrompido pelo usuário", "SISTEMA")
    except Exception as e:
        log.error(f"Erro fatal: {e}", "SISTEMA")
        import traceback
        traceback.print_exc()
    finally:
        log.section("Encerrando WaveControl")
        log.info("Até logo! 👋", "SISTEMA")

if __name__ == "__main__":
    main()

