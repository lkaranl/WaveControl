#!/usr/bin/env python3
import cv2
import time
import mediapipe as mp
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import threading
from pynput.keyboard import Key
from pynput import keyboard
from functools import lru_cache
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import queue
from analytics import get_analytics

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

# Cache de instância do MediaPipe
@lru_cache(maxsize=1)
def get_mediapipe_hands():
    """Retorna instância cacheada do MediaPipe Hands"""
    return mp_hands.Hands(
        max_num_hands=1,
        model_complexity=0,
        min_detection_confidence=MIN_DET,
        min_tracking_confidence=MIN_TRK,
    )

hands = get_mediapipe_hands()

# ===== Utilidades de dedos =====
TIP = { "thumb": 4, "index": 8, "middle": 12, "ring": 16, "pinky": 20 }
PIP = { "thumb": 3, "index": 6, "middle": 10, "ring": 14, "pinky": 18 }

# Cache para thresholds adaptativos
_THUMB_THRESHOLD = 0.05
_FINGER_THRESHOLD = 0.05

# MCP indices (base dos dedos) para melhor detecção
MCP = { "index": 5, "middle": 9, "ring": 13, "pinky": 17 }

def finger_extended(lm, tip_idx, pip_idx, handed_label):
    """
    Detecção melhorada de dedo estendido
    Usa múltiplos pontos para maior precisão
    """
    tip = lm[tip_idx]
    pip = lm[pip_idx]
    
    if tip_idx == TIP["thumb"]:
        # Polegar: usa IP (joint 3) e MCP (joint 2) para melhor precisão
        ip_joint = lm[3]
        mcp_joint = lm[2]
        
        if handed_label == "Right":
            # Verifica se tip está mais à esquerda que IP E MCP
            return tip.x < ip_joint.x - _THUMB_THRESHOLD and tip.x < mcp_joint.x
        else:
            # Verifica se tip está mais à direita que IP E MCP
            return tip.x > ip_joint.x + _THUMB_THRESHOLD and tip.x > mcp_joint.x
    else:
        # Outros dedos: usa PIP e MCP para verificação dupla
        # Encontra nome do dedo
        finger_name = None
        for name, idx in TIP.items():
            if idx == tip_idx:
                finger_name = name
                break
        
        if finger_name and finger_name in MCP:
            mcp = lm[MCP[finger_name]]
            
            # Verifica se:
            # 1. TIP está acima do PIP
            # 2. TIP está acima ou próximo do MCP
            # 3. A diferença é significativa
            tip_above_pip = tip.y < pip.y - _FINGER_THRESHOLD
            tip_above_mcp = tip.y < mcp.y + 0.02  # Mais tolerante com MCP
            
            return tip_above_pip and tip_above_mcp
        
        # Fallback para método antigo
        return tip.y < pip.y - _FINGER_THRESHOLD

# Cache para ordem de dedos
_FINGER_NAMES = ("thumb", "index", "middle", "ring", "pinky")

def count_extended(lm, handed_label):
    cnt = 0
    for name in _FINGER_NAMES:
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
    """
    Retorna gesto estável baseado no histórico - otimizado com Counter
    Agora com confiança adaptativa
    """
    if len(gesture_history) < GESTURE_WINDOW_SIZE:
        return "neutral"  # aguarda janela completa
    
    # Usa Counter para contar eficientemente
    gesture_counts = Counter(gesture_history)
    
    # Encontra o gesto mais frequente
    most_common_gesture, most_common_count = gesture_counts.most_common(1)[0]
    
    # Verifica se atende o threshold de consistência
    consistency_ratio = most_common_count / GESTURE_WINDOW_SIZE
    
    # Threshold adaptativo: se é neutral, requer menos consistência
    # Se é um gesto de ação, requer mais consistência
    threshold = CONSISTENCY_THRESHOLD
    if most_common_gesture == "neutral":
        threshold = 0.5  # Mais fácil voltar para neutral
    
    if consistency_ratio >= threshold and most_common_gesture != "neutral":
        return most_common_gesture
    
    return "neutral"

def get_gesture_confidence():
    """Retorna a confiança do gesto atual (0-100%)"""
    if len(gesture_history) < GESTURE_WINDOW_SIZE:
        return 0.0
    
    gesture_counts = Counter(gesture_history)
    most_common_gesture, most_common_count = gesture_counts.most_common(1)[0]
    
    confidence = (most_common_count / GESTURE_WINDOW_SIZE) * 100
    return confidence

# ===== Gesto -> Ação =====
# Cache de mapeamento (dict lookup mais rápido)
_GESTURE_MAP = {
    1: "next",
    2: "prev",
    3: "home",
    4: "end",
}

def classify_gesture(lm, handed_label):
    n = count_extended(lm, handed_label)
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

def calculate_hand_size(landmarks):
    """
    Calcula o tamanho da mão baseado nos landmarks
    Retorna a distância entre o pulso e o dedo médio
    """
    wrist = landmarks[0]
    middle_tip = landmarks[12]
    
    # Calcula distância euclidiana
    dx = middle_tip.x - wrist.x
    dy = middle_tip.y - wrist.y
    distance = (dx * dx + dy * dy) ** 0.5
    
    return distance

def calculate_hand_center(landmarks):
    """Calcula o centro da mão baseado nos landmarks"""
    # Usa média de landmarks chave
    x_coords = [lm.x for lm in landmarks]
    y_coords = [lm.y for lm in landmarks]
    
    center_x = sum(x_coords) / len(x_coords)
    center_y = sum(y_coords) / len(y_coords)
    
    return center_x, center_y

def apply_smart_zoom(frame, landmarks=None, manual_zoom=1.0, enable_auto=True):
    """
    Aplica zoom digital inteligente
    
    Args:
        frame: Frame original
        landmarks: Landmarks da mão (opcional, para auto-zoom)
        manual_zoom: Nível de zoom manual
        enable_auto: Habilita auto-zoom baseado na distância da mão
    
    Returns:
        Frame com zoom aplicado
    """
    height, width = frame.shape[:2]
    zoom_level = manual_zoom
    center_x, center_y = 0.5, 0.5  # Centro padrão
    
    # Auto-zoom: ajusta baseado no tamanho da mão
    if enable_auto and landmarks is not None:
        hand_size = calculate_hand_size(landmarks)
        center_x, center_y = calculate_hand_center(landmarks)
        
        # Ajusta zoom baseado no tamanho da mão
        # Mão pequena (longe) = mais zoom
        # Mão grande (perto) = menos zoom
        if hand_size < 0.15:  # Muito longe
            auto_zoom = 2.0
        elif hand_size < 0.25:  # Longe
            auto_zoom = 1.5
        elif hand_size < 0.35:  # Distância média
            auto_zoom = 1.2
        else:  # Perto
            auto_zoom = 1.0
        
        # Combina zoom manual e automático
        zoom_level = max(manual_zoom, auto_zoom)
    
    if zoom_level <= 1.0:
        return frame, 1.0
    
    # Calcula região a ser extraída (ROI centrado na mão)
    crop_width = int(width / zoom_level)
    crop_height = int(height / zoom_level)
    
    # Centraliza no centro da mão (com limites)
    center_x = max(0.0, min(1.0, center_x))
    center_y = max(0.0, min(1.0, center_y))
    
    start_x = int(center_x * width - crop_width / 2)
    start_y = int(center_y * height - crop_height / 2)
    
    # Garante que está dentro dos limites
    start_x = max(0, min(width - crop_width, start_x))
    start_y = max(0, min(height - crop_height, start_y))
    
    end_x = start_x + crop_width
    end_y = start_y + crop_height
    
    # Extrai a região
    cropped = frame[start_y:end_y, start_x:end_x]
    
    # Redimensiona
    zoomed = cv2.resize(cropped, (width, height), interpolation=cv2.INTER_LINEAR)
    
    return zoomed, zoom_level

def apply_digital_zoom(frame, zoom_level):
    """Compatibilidade: aplica zoom digital simples"""
    zoomed, _ = apply_smart_zoom(frame, landmarks=None, manual_zoom=zoom_level, enable_auto=False)
    return zoomed

# ===== Interface Tkinter para Windows =====
class WaveControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("WaveControl - Windows Edition")
        self.root.geometry("1200x700")
        self.root.minsize(800, 600)
        
        # Configurar estilo Windows nativo
        self.setup_style()
        
        # Variáveis de controle
        self.is_running = False
        self.cap = None
        self.start_ts = None
        self.last_action = "neutral"
        self.action_executed = False
        self.zoom_level = tk.DoubleVar(value=DEFAULT_ZOOM)
        self.show_landmarks = tk.BooleanVar(value=DRAW)
        self.auto_zoom_enabled = tk.BooleanVar(value=True)  # Auto-zoom inteligente
        self.current_auto_zoom = 1.0
        
        # Frame pooling para reduzir alocações
        self._frame_buffer = None
        self._rgb_buffer = None
        
        # Thread pool para processamento assíncrono
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="wavecontrol")
        self._frame_queue = queue.Queue(maxsize=2)
        self._result_queue = queue.Queue(maxsize=2)
        self._processing_active = False
        
        # Analytics
        self.analytics = get_analytics()
        
        # Interface
        self.setup_ui()
        
        # Eventos
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Auto-start
        self.root.after(100, self.start_detection)
    
    def setup_style(self):
        """Configura estilo nativo do Windows"""
        style = ttk.Style()
        
        # Tenta usar tema nativo do Windows
        available_themes = style.theme_names()
        if 'winnative' in available_themes:
            style.theme_use('winnative')
        elif 'vista' in available_themes:
            style.theme_use('vista')
        elif 'xpnative' in available_themes:
            style.theme_use('xpnative')
        else:
            style.theme_use('default')
        
        # Cores modernas do Windows
        self.colors = {
            'bg': '#f0f0f0',
            'fg': '#000000', 
            'accent': '#0078d4',
            'hover': '#106ebe',
            'success': '#107c10',
            'warning': '#ff8c00',
            'error': '#d13438',
            'card_bg': '#ffffff',
            'border': '#d1d1d1'
        }
        
        # Configurar estilos customizados
        style.configure('Card.TFrame', background=self.colors['card_bg'], relief='solid', borderwidth=1)
        style.configure('Header.TFrame', background=self.colors['bg'])
        style.configure('Accent.TButton', foreground='white', background=self.colors['accent'])
        style.configure('Success.TLabel', foreground=self.colors['success'], font=('Arial', 9, 'bold'))
        style.configure('Warning.TLabel', foreground=self.colors['warning'], font=('Arial', 9, 'bold'))
        style.configure('Title.TLabel', font=('Arial', 16, 'bold'))
        style.configure('Subtitle.TLabel', font=('Arial', 10, 'bold'))
        
    def setup_ui(self):
        # Container principal
        main_container = ttk.Frame(self.root)
        main_container.pack(fill='both', expand=True, padx=10, pady=10)
        
        # ===== HEADER =====
        header_frame = ttk.Frame(main_container, style='Header.TFrame')
        header_frame.pack(fill='x', pady=(0, 10))
        
        # Título e status
        header_left = ttk.Frame(header_frame)
        header_left.pack(side='left', fill='y')
        
        title_label = ttk.Label(header_left, text="WaveControl - Windows", style='Title.TLabel')
        title_label.pack(anchor='w')
        
        self.status_label = ttk.Label(header_left, text="Sistema parado", foreground=self.colors['warning'])
        self.status_label.pack(anchor='w', pady=(5, 0))
        
        # Controles
        header_right = ttk.Frame(header_frame)
        header_right.pack(side='right', fill='y')
        
        self.start_button = ttk.Button(header_right, text="▶ Iniciar", style='Accent.TButton',
                                      command=self.toggle_detection)
        self.start_button.pack(pady=5)
        
        # ===== LAYOUT PRINCIPAL =====
        content_frame = ttk.Frame(main_container)
        content_frame.pack(fill='both', expand=True)
        
        # ===== SIDEBAR =====
        sidebar = ttk.Frame(content_frame, style='Card.TFrame', width=300)
        sidebar.pack(side='left', fill='y', padx=(0, 10))
        sidebar.pack_propagate(False)
        
        # Card de Gestos
        self.create_gestures_card(sidebar)
        
        # Card de Zoom  
        self.create_zoom_card(sidebar)
        
        # Card de Status
        self.create_status_card(sidebar)
        
        # Card de Configurações
        self.create_config_card(sidebar)
        
        # Card de Métricas
        self.create_metrics_card(sidebar)
        
        # ===== ÁREA DE VÍDEO =====
        video_frame = ttk.Frame(content_frame, style='Card.TFrame')
        video_frame.pack(side='right', fill='both', expand=True)
        
        # Container do vídeo
        self.video_container = ttk.Frame(video_frame)
        self.video_container.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Label do vídeo
        self.video_label = ttk.Label(self.video_container, text="📷\n\nCâmera não ativada\n\nClique em 'Iniciar' para começar",
                                    justify='center', font=('Arial', 14))
        self.video_label.pack(expand=True)
        
        # ===== RODAPÉ =====
        footer = ttk.Frame(main_container)
        footer.pack(fill='x', pady=(10, 0))
        
        footer_label = ttk.Label(footer, text="WaveControl Windows - Controle por gestos | Criado por Karan Luciano",
                                font=('Arial', 9), foreground='gray')
        footer_label.pack(anchor='center')
    
    def create_gestures_card(self, parent):
        card = ttk.LabelFrame(parent, text="Gestos", padding=15)
        card.pack(fill='x', pady=(0, 10))
        
        gestures = [
            "👆 1 dedo → Próximo (→)",
            "✌️ 2 dedos → Anterior (←)", 
            "🤟 3 dedos → Início (Home)",
            "🖖 4 dedos → Fim (End)",
            "✊ 0 dedos → Neutro"
        ]
        
        for gesture in gestures:
            label = ttk.Label(card, text=gesture, font=('Arial', 9))
            label.pack(anchor='w', pady=2)
    
    def create_zoom_card(self, parent):
        card = ttk.LabelFrame(parent, text="Zoom Digital", padding=15)
        card.pack(fill='x', pady=(0, 10))
        
        # Valor atual
        self.zoom_value_label = ttk.Label(card, text=f"{DEFAULT_ZOOM:.1f}x", style='Subtitle.TLabel')
        self.zoom_value_label.pack(anchor='w')
        
        # Slider
        zoom_scale = ttk.Scale(card, from_=MIN_ZOOM, to=MAX_ZOOM, orient='horizontal',
                              variable=self.zoom_level, command=self.on_zoom_changed)
        zoom_scale.pack(fill='x', pady=(10, 10))
        
        # Botões rápidos
        buttons_frame = ttk.Frame(card)
        buttons_frame.pack(fill='x')
        
        for i, zoom in enumerate([1.0, 2.0, 3.0, 4.0]):
            btn = ttk.Button(buttons_frame, text=f"{zoom:.0f}x", width=6,
                           command=lambda z=zoom: self.set_zoom(z))
            btn.grid(row=0, column=i, padx=2, sticky='ew')
            buttons_frame.grid_columnconfigure(i, weight=1)
    
    def create_status_card(self, parent):
        card = ttk.LabelFrame(parent, text="Status do Sistema", padding=15)
        card.pack(fill='x', pady=(0, 10))
        
        # Status principal
        self.main_status = ttk.Label(card, text="Sistema parado", font=('Arial', 9))
        self.main_status.pack(anchor='w', pady=(0, 10))
        
        # Gesto atual
        gesture_frame = ttk.Frame(card)
        gesture_frame.pack(fill='x', pady=(0, 5))
        
        ttk.Label(gesture_frame, text="Gesto:", font=('Arial', 9)).pack(side='left')
        self.gesture_status = ttk.Label(gesture_frame, text="neutral", style='Success.TLabel')
        self.gesture_status.pack(side='right')
        
        # Filtro temporal
        filter_frame = ttk.Frame(card)
        filter_frame.pack(fill='x')
        
        ttk.Label(filter_frame, text="Filtro:", font=('Arial', 9)).pack(side='left')
        self.filter_status = ttk.Label(filter_frame, text="0/8", style='Warning.TLabel')
        self.filter_status.pack(side='right')
        
        # Confiança do gesto
        confidence_frame = ttk.Frame(card)
        confidence_frame.pack(fill='x', pady=(0, 5))
        
        ttk.Label(confidence_frame, text="Confiança:", font=('Arial', 9)).pack(side='left')
        self.confidence_status = ttk.Label(confidence_frame, text="0%", style='Success.TLabel')
        self.confidence_status.pack(side='right')
        
        # FPS
        fps_frame = ttk.Frame(card)
        fps_frame.pack(fill='x')
        
        ttk.Label(fps_frame, text="FPS:", font=('Arial', 9)).pack(side='left')
        self.fps_status = ttk.Label(fps_frame, text="0.0", style='Success.TLabel')
        self.fps_status.pack(side='right')
    
    def create_config_card(self, parent):
        card = ttk.LabelFrame(parent, text="Configurações", padding=15)
        card.pack(fill='x', pady=(0, 10))
        
        landmarks_check = ttk.Checkbutton(card, text="Mostrar landmarks",
                                         variable=self.show_landmarks)
        landmarks_check.pack(anchor='w')
        
        # Auto-zoom
        auto_zoom_check = ttk.Checkbutton(card, text="Auto-zoom inteligente",
                                         variable=self.auto_zoom_enabled)
        auto_zoom_check.pack(anchor='w', pady=(5, 0))
    
    def create_metrics_card(self, parent):
        card = ttk.LabelFrame(parent, text="Métricas", padding=15)
        card.pack(fill='x', pady=(0, 10))
        
        # Total de gestos
        gestures_frame = ttk.Frame(card)
        gestures_frame.pack(fill='x', pady=(0, 5))
        
        ttk.Label(gestures_frame, text="Gestos:", font=('Arial', 9)).pack(side='left')
        self.total_gestures_status = ttk.Label(gestures_frame, text="0", style='Success.TLabel')
        self.total_gestures_status.pack(side='right')
        
        # Frames processados
        frames_frame = ttk.Frame(card)
        frames_frame.pack(fill='x')
        
        ttk.Label(frames_frame, text="Frames:", font=('Arial', 9)).pack(side='left')
        self.total_frames_status = ttk.Label(frames_frame, text="0", style='Success.TLabel')
        self.total_frames_status.pack(side='right')
    
    def on_zoom_changed(self, value):
        zoom_val = float(value)
        self.zoom_value_label.config(text=f"{zoom_val:.1f}x")
    
    def set_zoom(self, zoom_value):
        self.zoom_level.set(zoom_value)
        self.zoom_value_label.config(text=f"{zoom_value:.1f}x")
    
    def toggle_detection(self):
        if not self.is_running:
            self.start_detection()
        else:
            self.stop_detection()
    
    def start_detection(self):
        global gesture_history
        gesture_history.clear()
        
        self.cap = cv2.VideoCapture(CAM_INDEX)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 800)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 600)
        
        if not self.cap.isOpened():
            messagebox.showerror("Erro", "Não foi possível acessar a câmera.\nVerifique se está conectada e disponível.")
            return
        
        self.is_running = True
        self.start_ts = time.time()
        
        # Inicia sessão de analytics
        self.analytics.start_session()
        self.analytics.set_calibration_time(CALIBRATION_S)
        
        # Atualiza interface
        self.start_button.config(text="⏹ Parar")
        self.status_label.config(text="Calibrando...", foreground=self.colors['warning'])
        self.main_status.config(text="Sistema calibrando...")
        
        # Remove placeholder
        self.video_label.pack_forget()
        
        # Inicia thread de processamento
        self.processing_thread = threading.Thread(target=self.process_video)
        self.processing_thread.daemon = True
        self.processing_thread.start()
    
    def stop_detection(self):
        self.is_running = False
        
        # Finaliza sessão de analytics
        self.analytics.end_session()
        
        if self.cap:
            self.cap.release()
        
        # Atualiza interface
        self.start_button.config(text="▶ Iniciar")
        self.status_label.config(text="Sistema parado", foreground=self.colors['warning'])
        self.main_status.config(text="Sistema parado")
        
        # Mostra estatísticas no terminal
        print("\n" + "="*50)
        self.analytics.print_stats()
        print("="*50 + "\n")
        
        # Limpa vídeo e mostra placeholder
        if hasattr(self, 'video_display'):
            self.video_display.destroy()
        
        self.video_label.config(text="📷\n\nCâmera não ativada\n\nClique em 'Iniciar' para começar")
        self.video_label.pack(expand=True)
        
        # Reset status
        self.gesture_status.config(text="neutral")
        self.filter_status.config(text="0/8")
        self.confidence_status.config(text="0%")
        self.fps_status.config(text="0.0")
        
        # Reset métricas
        stats = self.analytics.get_stats_summary()
        self.total_gestures_status.config(text=str(stats['usage']['total_gestures']))
        self.total_frames_status.config(text=str(stats['performance']['total_frames']))
    
    def _process_frame_async(self, frame_data):
        """Processa frame em thread separada"""
        start_time = time.perf_counter()
        
        frame, zoom_level, show_landmarks = frame_data
        
        # Frame pooling: reutiliza buffers pré-alocados
        frame = cv2.flip(frame, 1)
        
        # Primeiro processa para detectar mão (antes do zoom)
        temp_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        temp_res = hands.process(temp_rgb)
        
        # Pega landmarks se disponível
        hand_landmarks = None
        if temp_res.multi_hand_landmarks:
            hand_landmarks = temp_res.multi_hand_landmarks[0].landmark
        
        # Aplica zoom inteligente (auto + manual)
        frame, actual_zoom = apply_smart_zoom(
            frame,
            landmarks=hand_landmarks,
            manual_zoom=zoom_level,
            enable_auto=self.auto_zoom_enabled.get()
        )
        
        # Reutiliza buffers quando possível
        if self._rgb_buffer is None or self._rgb_buffer.shape != frame.shape:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self._rgb_buffer = rgb
        else:
            cv2.cvtColor(frame, cv2.COLOR_BGR2RGB, dst=self._rgb_buffer)
            rgb = self._rgb_buffer
        
        res = hands.process(rgb)
        
        # Métrica de tempo de processamento
        processing_time = (time.perf_counter() - start_time) * 1000
        self.analytics.record_frame(processing_time)
        
        raw_action = "neutral"
        handed = "Right"
        
        if res.multi_hand_landmarks:
            lm = res.multi_hand_landmarks[0]
            if res.multi_handedness and len(res.multi_handedness) > 0:
                handed = res.multi_handedness[0].classification[0].label
            raw_action = classify_gesture(lm.landmark, handed)
            
            # Desenha landmarks se habilitado
            if show_landmarks:
                mp_drawing.draw_landmarks(
                    frame, lm, mp_hands.HAND_CONNECTIONS,
                    mp_drawing.DrawingSpec(color=(0,255,0), thickness=2, circle_radius=2),
                    mp_drawing.DrawingSpec(color=(255,0,0), thickness=2)
                )
        
        return raw_action, frame, res, actual_zoom
    
    def _gesture_processor_thread(self):
        """Thread dedicada para processar gestos de forma assíncrona"""
        while self._processing_active:
            try:
                frame_data = self._frame_queue.get(timeout=0.1)
                result = self._process_frame_async(frame_data)
                
                try:
                    self._result_queue.put(result, block=False)
                except queue.Full:
                    try:
                        self._result_queue.get_nowait()
                    except queue.Empty:
                        pass
                    self._result_queue.put(result, block=False)
                    
            except queue.Empty:
                continue
            except Exception as e:
                continue
    
    def process_video(self):
        # Cria label para o vídeo
        if not hasattr(self, 'video_display'):
            self.video_display = ttk.Label(self.video_container)
            self.video_display.pack(expand=True)
        
        # Inicia thread de processamento assíncrono
        self._processing_active = True
        processor_thread = threading.Thread(target=self._gesture_processor_thread, daemon=True)
        processor_thread.start()
        
        try:
            while self.is_running and self.cap and self.cap.isOpened():
                ok, frame = self.cap.read()
                if not ok:
                    break
                
                # Envia frame para processamento assíncrono
                try:
                    frame_data = (frame.copy(), self.zoom_level.get(), self.show_landmarks.get())
                    self._frame_queue.put(frame_data, block=False)
                except queue.Full:
                    self.analytics.record_dropped_frame()
                    pass
                
                # Atualiza tamanho da fila
                self.analytics.set_queue_size(self._frame_queue.qsize())
                
                # Tenta pegar resultado processado
                raw_action = "neutral"
                processed_frame = None
                res = None
                actual_zoom = 1.0
                
                try:
                    raw_action, processed_frame, res, actual_zoom = self._result_queue.get_nowait()
                except queue.Empty:
                    continue
                
                if processed_frame is None:
                    continue
                
                # Adiciona gesto ao histórico e obtém gesto estável
                add_gesture_to_history(raw_action)
                action = get_stable_gesture()
                gesture_confidence = get_gesture_confidence()
                
                frame = processed_frame
                self.current_auto_zoom = actual_zoom
            
                now = time.time()
            
                # Informações visuais na tela
                if hasattr(self, 'current_auto_zoom') and self.current_auto_zoom > 1.0:
                    zoom_text = f"Zoom: {self.current_auto_zoom:.1f}x"
                    if self.auto_zoom_enabled.get():
                        zoom_text += " (Auto)"
                    cv2.putText(frame, zoom_text, (20, frame.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)
                
                # Calibração inicial
                if now - self.start_ts < CALIBRATION_S:
                    cv2.putText(frame, "Calibrando...", (20,40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
                    self.root.after(0, lambda: self.status_label.config(text="Calibrando...", foreground=self.colors['warning']))
                    self.root.after(0, lambda: self.main_status.config(text="Sistema calibrando..."))
                else:
                    # Lógica de execução de ações
                    if action == "neutral":
                        if self.action_executed:
                            self.action_executed = False
                            self.root.after(0, lambda: self.status_label.config(text="Sistema ativo", foreground=self.colors['success']))
                            self.root.after(0, lambda: self.main_status.config(text="Sistema ativo - Pronto"))
                    elif action != "neutral" and not self.action_executed:
                        if action == "next":
                            press_next()
                            self.analytics.record_gesture("next")
                            self.root.after(0, lambda: self.status_label.config(text="Próximo →", foreground=self.colors['accent']))
                            self.root.after(0, lambda: self.main_status.config(text="Próximo slide executado"))
                        elif action == "prev":
                            press_prev()
                            self.analytics.record_gesture("prev")
                            self.root.after(0, lambda: self.status_label.config(text="← Anterior", foreground=self.colors['accent']))
                            self.root.after(0, lambda: self.main_status.config(text="Slide anterior executado"))
                        elif action == "home":
                            press_home()
                            self.analytics.record_gesture("home")
                            self.root.after(0, lambda: self.status_label.config(text="⏮ Início", foreground=self.colors['accent']))
                            self.root.after(0, lambda: self.main_status.config(text="Indo para o início"))
                        elif action == "end":
                            press_end()
                            self.analytics.record_gesture("end")
                            self.root.after(0, lambda: self.status_label.config(text="⏭ Fim", foreground=self.colors['accent']))
                            self.root.after(0, lambda: self.main_status.config(text="Indo para o fim"))
                        self.action_executed = True
                        self.last_action = action
                    elif action != "neutral" and self.action_executed:
                        self.root.after(0, lambda: self.status_label.config(text="Aguardando...", foreground=self.colors['warning']))
                        self.root.after(0, lambda: self.main_status.config(text="Aguardando posição neutra"))
                
                # Atualiza indicadores de status
                self.root.after(0, lambda: self.gesture_status.config(text=action))
                self.root.after(0, lambda: self.filter_status.config(text=f"{len(gesture_history)}/{GESTURE_WINDOW_SIZE}"))
                self.root.after(0, lambda: self.confidence_status.config(text=f"{gesture_confidence:.0f}%"))
                
                # Atualiza FPS e métricas
                stats = self.analytics.get_stats_summary()
                fps_value = stats['performance']['fps']
                total_gestures = stats['usage']['total_gestures']
                total_frames = stats['performance']['total_frames']
                
                self.root.after(0, lambda: self.fps_status.config(text=f"{fps_value:.1f}"))
                self.root.after(0, lambda: self.total_gestures_status.config(text=str(total_gestures)))
                self.root.after(0, lambda: self.total_frames_status.config(text=str(total_frames)))
                
                # Converte frame para exibição na GUI
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(rgb)
                
                # Redimensiona mantendo proporção
                container_width = self.video_container.winfo_width()
                container_height = self.video_container.winfo_height()
                
                if container_width > 1 and container_height > 1:
                    # Calcula tamanho mantendo proporção
                    img_ratio = image.width / image.height
                    container_ratio = container_width / container_height
                    
                    if img_ratio > container_ratio:
                        # Imagem mais larga
                        new_width = min(container_width - 40, 640)
                        new_height = int(new_width / img_ratio)
                    else:
                        # Imagem mais alta
                        new_height = min(container_height - 40, 480)
                        new_width = int(new_height * img_ratio)
                    
                    image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                photo = ImageTk.PhotoImage(image)
                self.root.after(0, lambda: self.update_video_display(photo))
                
                time.sleep(0.01)  # ~100 FPS captura, processamento assíncrono
        finally:
            # Para thread de processamento
            self._processing_active = False
            processor_thread.join(timeout=1.0)
    
    def update_video_display(self, photo):
        if hasattr(self, 'video_display') and self.video_display.winfo_exists():
            self.video_display.config(image=photo)
            self.video_display.image = photo  # Manter referência
    
    def on_closing(self):
        self.stop_detection()
        self._processing_active = False
        
        # Limpa filas
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                break
        while not self._result_queue.empty():
            try:
                self._result_queue.get_nowait()
            except queue.Empty:
                break
        
        # Finaliza executor
        self._executor.shutdown(wait=False)
        
        if hands:
            hands.close()
        self.root.destroy()

# ===== Execução Principal =====
def main():
    root = tk.Tk()
    
    # Ícone da janela (opcional)
    try:
        # Se você tiver um arquivo .ico
        # root.iconbitmap('icon.ico')
        pass
    except:
        pass
    
    app = WaveControlApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
