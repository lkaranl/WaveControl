#!/usr/bin/env python3
import cv2
import time
import sys
import mediapipe as mp
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import threading
from pynput.keyboard import Key
from pynput import keyboard
from functools import lru_cache
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
import queue
from analytics import get_analytics
from datetime import datetime

# ===== Sistema de Logs Melhorado =====
class Logger:
    """Sistema de logs colorido e organizado"""
    
    @staticmethod
    def banner():
        """Exibe banner de inicialização"""
        print("\n" + "="*60)
        print("  🌊 WaveControl - Windows Edition")
        print("  Versão: 1.0.0")
        print("  Por: Karan Luciano")
        print("="*60)
        
    @staticmethod
    def info(message, component="SISTEMA"):
        """Log informativo"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] ℹ️  [{component}] {message}")
    
    @staticmethod
    def success(message, component="SISTEMA"):
        """Log de sucesso"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] ✅ [{component}] {message}")
    
    @staticmethod
    def warning(message, component="SISTEMA"):
        """Log de aviso"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] ⚠️  [{component}] {message}")
    
    @staticmethod
    def error(message, component="SISTEMA"):
        """Log de erro"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] ❌ [{component}] {message}")
    
    @staticmethod
    def section(title):
        """Inicia uma nova seção"""
        print(f"\n{'─'*60}")
        print(f"  {title}")
        print(f"{'─'*60}")

log = Logger()

# ===== Configurações =====
MIN_DET = 0.6
MIN_TRK = 0.6
CALIBRATION_S = 2.0     # tempo inicial para estabilizar câmera
DRAW = True             # mostrar janela com landmarks
CAM_INDEX = 0           # índice da webcam
TARGET_FPS = 30         # FPS alvo (limita uso de CPU)

# ===== Cooldown entre comandos =====
ACTION_COOLDOWN_S = 0.8  # Tempo mínimo entre ações (evita comandos fantasma durante transições)

# ===== Configurações de Zoom =====
DEFAULT_ZOOM = 1.0      # zoom padrão (sem zoom)
MIN_ZOOM = 1.0          # zoom mínimo
MAX_ZOOM = 4.0          # zoom máximo

# ===== Filtro Temporal =====
GESTURE_WINDOW_SIZE = 9  # número de frames para confirmar gesto (balanceado: precisão + responsividade)
CONSISTENCY_THRESHOLD = 0.78  # 78% das amostras devem ser iguais (7 de 9 frames)

# ===== Dispositivo virtual (pynput para Windows) =====
log.section("Inicializando Backend de Teclado")
log.info("Usando pynput para emulação de teclado (Windows)", "BACKEND")
kb_controller = keyboard.Controller()
log.success("pynput inicializado com sucesso", "BACKEND")

# ===== MediaPipe =====
log.section("Inicializando MediaPipe")
log.info("Carregando modelo de detecção de mãos...", "MEDIAPIPE")

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
log.success(f"MediaPipe inicializado (complexidade: 0, min_det: {MIN_DET}, min_trk: {MIN_TRK})", "MEDIAPIPE")

# Pre-allocated DrawingSpecs para melhor performance (evita criar toda vez)
_LANDMARK_DRAWING_SPEC = mp_drawing.DrawingSpec(color=(0,255,0), thickness=2, circle_radius=2)
_CONNECTION_DRAWING_SPEC = mp_drawing.DrawingSpec(color=(255,0,0), thickness=2)

# ===== Utilidades de dedos =====
TIP = { "thumb": 4, "index": 8, "middle": 12, "ring": 16, "pinky": 20 }
PIP = { "thumb": 3, "index": 6, "middle": 10, "ring": 14, "pinky": 18 }

# Cache para thresholds adaptativos
_THUMB_THRESHOLD = 0.05
_FINGER_THRESHOLD = 0.06  # Threshold para dedos normais (mais restritivo)
_INDEX_THRESHOLD = 0.03   # Threshold bem mais sensível para dedo indicador

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
        
        # Threshold específico para cada dedo
        threshold = _INDEX_THRESHOLD if finger_name == "index" else _FINGER_THRESHOLD
        
        if finger_name and finger_name in MCP:
            mcp = lm[MCP[finger_name]]
            
            # Verifica se:
            # 1. TIP está acima do PIP
            # 2. TIP está acima ou próximo do MCP
            # 3. A diferença é significativa
            tip_above_pip = tip.y < pip.y - threshold
            
            # Para indicador, mais tolerância no MCP
            mcp_tolerance = 0.05 if finger_name == "index" else 0.03
            tip_above_mcp = tip.y < mcp.y + mcp_tolerance
            
            return tip_above_pip and tip_above_mcp
        
        # Fallback para método antigo
        return tip.y < pip.y - threshold

# Cache para ordem de dedos
_FINGER_NAMES = ("thumb", "index", "middle", "ring", "pinky")

def get_extended_fingers(lm, handed_label):
    """
    Retorna lista de dedos estendidos para análise detalhada
    """
    extended = []
    for name in _FINGER_NAMES:
        if finger_extended(lm, TIP[name], PIP[name], handed_label):
            extended.append(name)
    return extended

def count_extended(lm, handed_label):
    cnt = 0
    for name in _FINGER_NAMES:
        if finger_extended(lm, TIP[name], PIP[name], handed_label):
            cnt += 1
    return cnt

# ===== Histórico de Gestos =====
# Usa deque para O(1) append e popleft (muito mais rápido que list)
gesture_history = deque(maxlen=GESTURE_WINDOW_SIZE)

# Cache do último Counter calculado para evitar recálculos
_last_gesture_counts = None
_last_history_snapshot = None

def _get_gesture_counts():
    """Cache para Counter - evita recalcular quando histórico não mudou"""
    global _last_gesture_counts, _last_history_snapshot
    
    # Snapshot do histórico atual
    current_snapshot = tuple(gesture_history)
    
    # Se é o mesmo histórico, retorna cache
    if current_snapshot == _last_history_snapshot and _last_gesture_counts is not None:
        return _last_gesture_counts
    
    # Recalcula e atualiza cache
    _last_gesture_counts = Counter(gesture_history)
    _last_history_snapshot = current_snapshot
    
    return _last_gesture_counts

def add_gesture_to_history(gesture):
    gesture_history.append(gesture)

def get_stable_gesture():
    """
    Retorna gesto estável baseado no histórico - OTIMIZADO
    Usa cache para evitar recalcular Counter toda vez
    """
    if len(gesture_history) < 4:  # Reduzido para responder mais rápido
        return "neutral"
    
    # Usa Counter cacheado
    gesture_counts = _get_gesture_counts()
    
    # Encontra o gesto mais frequente
    most_common_gesture, most_common_count = gesture_counts.most_common(1)[0]
    
    # Verifica se atende o threshold de consistência
    consistency_ratio = most_common_count / len(gesture_history)
    
    # Threshold adaptativo: gestos diferentes requerem consistência diferente
    threshold = CONSISTENCY_THRESHOLD
    if most_common_gesture == "neutral":
        threshold = 0.5  # Mais fácil voltar para neutral (5 de 9 frames)
    elif most_common_gesture == "next":  # Gesto número 1
        threshold = 0.67  # Mesma sensibilidade dos outros gestos (6 de 9 frames)
    
    if consistency_ratio >= threshold and most_common_gesture != "neutral":
        return most_common_gesture
    
    return "neutral"


def get_gesture_confidence():
    """Retorna a confiança do gesto atual (0-100%) - OTIMIZADO"""
    if len(gesture_history) < GESTURE_WINDOW_SIZE:
        return 0.0
    
    # Usa Counter cacheado
    gesture_counts = _get_gesture_counts()
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
    """
    Classifica gesto com lógica melhorada para número 1
    Prioriza indicador levantado sozinho com verificação dupla
    """
    extended_fingers = get_extended_fingers(lm, handed_label)
    
    # Detecção especial para gesto número 1
    # Verifica: indicador levantado E outros dedos (middle, ring, pinky) fechados
    index_extended = "index" in extended_fingers
    middle_closed = "middle" not in extended_fingers
    ring_closed = "ring" not in extended_fingers
    pinky_closed = "pinky" not in extended_fingers
    
    # Se indicador levantado e os 3 últimos dedos fechados = gesto número 1
    # (ignora polegar completamente)
    if index_extended and middle_closed and ring_closed and pinky_closed:
        return "next"  # Gesto número 1
    
    # Para outros gestos, conta todos os dedos
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
    """
    Aplica zoom digital simples e centralizado
    """
    if zoom_level <= 1.0:
        return frame
    
    height, width = frame.shape[:2]
    
    # Calcula região a ser extraída (ROI centralizado)
    crop_width = int(width / zoom_level)
    crop_height = int(height / zoom_level)
    
    # Centro da imagem
    start_x = (width - crop_width) // 2
    start_y = (height - crop_height) // 2
    
    end_x = start_x + crop_width
    end_y = start_y + crop_height
    
    # Extrai a região
    cropped = frame[start_y:end_y, start_x:end_x]
    
    # Redimensiona
    zoomed = cv2.resize(cropped, (width, height), interpolation=cv2.INTER_LINEAR)
    
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
        
        # Cor de fundo da janela principal (tema escuro)
        self.root.configure(bg=self.colors['bg_primary'])
        
        # Variáveis de controle
        self.is_running = False
        self.cap = None
        self.start_ts = None
        self.last_action = "neutral"
        self.action_executed = False
        self.last_action_time = 0  # Timestamp da última ação (para cooldown)
        self.zoom_level = tk.DoubleVar(value=DEFAULT_ZOOM)
        self.show_landmarks = tk.BooleanVar(value=DRAW)
        
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
        
        # Paleta moderna com alto contraste (WCAG AAA)
        self.colors = {
            # Backgrounds
            'bg_primary': '#1e1e1e',      # Fundo escuro principal
            'bg_secondary': '#252526',    # Fundo secundário (cards)
            'bg_tertiary': '#2d2d30',     # Fundo terciário (hover)
            'bg_sidebar': '#252526',      # Sidebar
            'bg_header': '#2d2d30',       # Header
            
            # Texto
            'text_primary': '#cccccc',    # Texto principal (alto contraste)
            'text_secondary': '#969696',  # Texto secundário
            'text_tertiary': '#6e6e6e',   # Texto terciário
            'text_on_accent': '#ffffff',  # Texto em accent
            
            # Accent colors
            'accent': '#007acc',          # Azul VS Code
            'accent_hover': '#1c97ea',    # Hover
            'accent_light': '#094771',    # Background accent
            
            # Borders
            'border_default': '#3e3e42',  # Borda padrão
            'border_focus': '#007acc',    # Borda focus
            'border_subtle': '#2d2d30',   # Borda sutil
            
            # Status colors (vibrantes para destacar)
            'success': '#4ec9b0',         # Cyan-verde
            'warning': '#dcdcaa',         # Amarelo suave
            'error': '#f48771',           # Vermelho suave
            'info': '#9cdcfe',            # Azul claro
            
            # Gesture colors (palette completa e harmoniosa)
            'gesture_next': '#4ec9b0',    # Cyan (next/forward)
            'gesture_prev': '#569cd6',    # Azul (prev/back)
            'gesture_home': '#c586c0',    # Roxo (home)
            'gesture_end': '#ce9178',     # Laranja (end)
            'gesture_neutral': '#6e6e6e', # Cinza neutro
            
            # Video area
            'video_bg': '#1a1a1a',        # Fundo do vídeo
            'video_border': '#007acc',    # Borda quando ativo
        }
        
        # Configurar estilos customizados com tema escuro
        style.configure('TFrame', background=self.colors['bg_primary'])
        style.configure('Card.TFrame', background=self.colors['bg_secondary'], relief='flat')
        style.configure('Header.TFrame', background=self.colors['bg_header'])
        
        # Botão accent
        style.configure('Accent.TButton', 
                       foreground=self.colors['text_on_accent'], 
                       background=self.colors['accent'],
                       font=('Segoe UI', 10, 'bold'), 
                       borderwidth=1,
                       relief='flat')
        style.map('Accent.TButton',
                 background=[('active', self.colors['accent_hover'])])
        
        # Labels
        style.configure('TLabel', 
                       background=self.colors['bg_primary'], 
                       foreground=self.colors['text_primary'],
                       font=('Segoe UI', 10))
        style.configure('Title.TLabel', 
                       font=('Segoe UI', 18, 'bold'), 
                       foreground=self.colors['text_primary'],
                       background=self.colors['bg_header'])
        style.configure('Subtitle.TLabel', 
                       font=('Segoe UI', 11, 'bold'), 
                       foreground=self.colors['accent'])
        style.configure('Secondary.TLabel', 
                       font=('Segoe UI', 9), 
                       foreground=self.colors['text_secondary'])
        
        # LabelFrame
        style.configure('TLabelframe', 
                       background=self.colors['bg_secondary'],
                       foreground=self.colors['text_primary'],
                       bordercolor=self.colors['border_default'],
                       relief='solid',
                       borderwidth=1)
        style.configure('TLabelframe.Label', 
                       background=self.colors['bg_secondary'],
                       foreground=self.colors['accent'],
                       font=('Segoe UI', 10, 'bold'))
        
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
        
        title_label = ttk.Label(header_left, text="WaveControl", style='Title.TLabel')
        title_label.pack(anchor='w')
        
        # Separador visual
        separator_label = tk.Label(header_left, text="|", font=('Segoe UI', 18), 
                                   foreground=self.colors['border_default'],
                                   bg=self.colors['bg_header'])
        separator_label.pack(side='left', padx=12)
        
        # Gesto atual no header
        self.header_gesture = tk.Label(header_left, text="✊ neutral", 
                                       font=('Segoe UI', 14, 'bold'),
                                       foreground=self.colors['gesture_neutral'],
                                       bg=self.colors['bg_header'])
        self.header_gesture.pack(side='left')
        
        self.status_label = tk.Label(header_left, text="Sistema parado", 
                                     font=('Segoe UI', 9), 
                                     foreground=self.colors['text_secondary'],
                                     bg=self.colors['bg_header'])
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
        sidebar = tk.Frame(content_frame, bg=self.colors['bg_sidebar'], width=300,
                          relief='flat', borderwidth=0,
                          highlightbackground=self.colors['border_default'],
                          highlightthickness=1)
        sidebar.pack(side='left', fill='y', padx=(0, 10))
        sidebar.pack_propagate(False)
        
        # Card de Gestos
        self.create_gestures_card(sidebar)
        
        # Card de Zoom  
        self.create_zoom_card(sidebar)
        
        # Card de Status
        self.create_status_card(sidebar)
        
        # ===== ÁREA DE VÍDEO =====
        video_frame = tk.Frame(content_frame, bg=self.colors['bg_secondary'], 
                              relief='flat', borderwidth=0, 
                              highlightbackground=self.colors['border_default'],
                              highlightthickness=1)
        video_frame.pack(side='right', fill='both', expand=True)
        
        # Container do vídeo
        self.video_container = tk.Frame(video_frame, bg=self.colors['bg_secondary'])
        self.video_container.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Label do vídeo (placeholder)
        placeholder_frame = tk.Frame(self.video_container, 
                                    bg=self.colors['video_bg'],
                                    relief='solid',
                                    borderwidth=2,
                                    highlightbackground=self.colors['border_default'],
                                    highlightthickness=0)
        placeholder_frame.pack(expand=True, fill='both')
        
        self.video_label = tk.Label(placeholder_frame, 
                                    text="📷\n\nCâmera não ativada\n\nClique em 'Iniciar' para começar",
                                    justify='center', font=('Segoe UI', 14),
                                    bg=self.colors['video_bg'], 
                                    fg=self.colors['text_secondary'])
        self.video_label.pack(expand=True)
        
        # ===== RODAPÉ =====
        footer = tk.Frame(main_container, bg=self.colors['bg_secondary'],
                         highlightbackground=self.colors['border_default'],
                         highlightthickness=1)
        footer.pack(fill='x', pady=(10, 0))
        
        footer_label = tk.Label(footer, 
                               text="WaveControl - Controle por gestos | Criado por Karan Luciano",
                               font=('Segoe UI', 9), 
                               foreground=self.colors['text_tertiary'],
                               bg=self.colors['bg_secondary'])
        footer_label.pack(side='left', anchor='w', padx=10, pady=8)
        
        # Label do backend
        backend_label = tk.Label(footer, text="🖥️ Windows (pynput)",
                                font=('Segoe UI', 9), 
                                foreground=self.colors['text_tertiary'],
                                bg=self.colors['bg_secondary'])
        backend_label.pack(side='right', anchor='e', padx=10, pady=8)
    
    def create_gestures_card(self, parent):
        card = ttk.LabelFrame(parent, text="Gestos", padding=15)
        card.pack(fill='x', pady=(10, 10), padx=10)
        
        gestures_data = [
            ("next", "👆 1 → Próximo", self.colors['gesture_next']),
            ("prev", "✌️ 2 → Anterior", self.colors['gesture_prev']),
            ("home", "🤟 3 → Início", self.colors['gesture_home']),
            ("end", "🖖 4 → Fim", self.colors['gesture_end']),
            ("neutral", "✊ 0 → Neutro", self.colors['gesture_neutral'])
        ]
        
        # Dicionário para acessar labels dos gestos
        self.gesture_labels = {}
        
        for gesture_id, gesture_text, color in gestures_data:
            frame = tk.Frame(card, bg=self.colors['bg_secondary'])
            frame.pack(fill='x', pady=3)
            
            label = tk.Label(frame, text=gesture_text, 
                           font=('Segoe UI', 10),
                           bg=self.colors['bg_secondary'],
                           fg=self.colors['text_primary'],
                           anchor='w')
            label.pack(side='left', fill='x', expand=True)
            self.gesture_labels[gesture_id] = label
    
    def create_zoom_card(self, parent):
        card = ttk.LabelFrame(parent, text="Zoom Digital", padding=15)
        card.pack(fill='x', pady=(0, 10), padx=10)
        
        # Valor atual
        self.zoom_value_label = tk.Label(card, text=f"{DEFAULT_ZOOM:.1f}x", 
                                         font=('Segoe UI', 12, 'bold'),
                                         foreground=self.colors['accent'],
                                         bg=self.colors['bg_secondary'])
        self.zoom_value_label.pack(anchor='w', pady=(0, 5))
        
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
        card.pack(fill='x', pady=(0, 10), padx=10)
        
        # Container com fundo
        status_container = tk.Frame(card, bg=self.colors['bg_tertiary'], relief='flat')
        status_container.pack(fill='x', padx=5, pady=5)
        
        # Gesto atual (badge colorido)
        gesture_frame = tk.Frame(status_container, bg=self.colors['bg_tertiary'])
        gesture_frame.pack(fill='x', pady=5, padx=8)
        
        tk.Label(gesture_frame, text="Gesto:", 
                font=('Segoe UI', 9), 
                foreground=self.colors['text_secondary'],
                bg=self.colors['bg_tertiary']).pack(side='left')
        
        self.gesture_status = tk.Label(gesture_frame, text="neutral", 
                                      font=('Segoe UI', 9, 'bold'),
                                      bg=self.colors['gesture_neutral'], 
                                      fg=self.colors['text_on_accent'],
                                      padx=10, pady=4, relief='flat')
        self.gesture_status.pack(side='right')
        
        # FPS
        fps_frame = tk.Frame(status_container, bg=self.colors['bg_tertiary'])
        fps_frame.pack(fill='x', pady=5, padx=8)
        
        tk.Label(fps_frame, text="FPS:", 
                font=('Segoe UI', 9),
                foreground=self.colors['text_secondary'],
                bg=self.colors['bg_tertiary']).pack(side='left')
        self.fps_status = tk.Label(fps_frame, text="0.0", 
                                  font=('Segoe UI', 10, 'bold'),
                                  foreground=self.colors['info'],
                                  bg=self.colors['bg_tertiary'])
        self.fps_status.pack(side='right')
        
        # Zoom
        zoom_frame = tk.Frame(status_container, bg=self.colors['bg_tertiary'])
        zoom_frame.pack(fill='x', pady=5, padx=8)
        
        tk.Label(zoom_frame, text="Zoom:", 
                font=('Segoe UI', 9),
                foreground=self.colors['text_secondary'],
                bg=self.colors['bg_tertiary']).pack(side='left')
        self.zoom_status = tk.Label(zoom_frame, text="1.0x", 
                                   font=('Segoe UI', 10, 'bold'),
                                   foreground=self.colors['info'],
                                   bg=self.colors['bg_tertiary'])
        self.zoom_status.pack(side='right')
    
    def on_zoom_changed(self, value):
        zoom_val = float(value)
        self.zoom_value_label.config(text=f"{zoom_val:.1f}x")
        self.zoom_status.config(text=f"{zoom_val:.1f}x")
    
    def set_zoom(self, zoom_value):
        self.zoom_level.set(zoom_value)
        self.zoom_value_label.config(text=f"{zoom_value:.1f}x")
        self.zoom_status.config(text=f"{zoom_value:.1f}x")
    
    def toggle_detection(self):
        if not self.is_running:
            self.start_detection()
        else:
            self.stop_detection()
    
    def start_detection(self):
        global gesture_history
        gesture_history.clear()
        
        log.section("Iniciando Detecção de Gestos")
        log.info(f"Abrindo câmera (índice: {CAM_INDEX}, resolução: 800x600)...", "CAMERA")
        
        self.cap = cv2.VideoCapture(CAM_INDEX)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 800)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 600)
        
        if not self.cap.isOpened():
            log.error("Falha ao acessar a câmera", "CAMERA")
            messagebox.showerror("Erro", "Não foi possível acessar a câmera.\nVerifique se está conectada e disponível.")
            return
        
        log.success("Câmera aberta com sucesso", "CAMERA")
        self.is_running = True
        self.start_ts = time.time()
        
        # Inicia sessão de analytics
        self.analytics.start_session()
        self.analytics.set_calibration_time(CALIBRATION_S)
        log.info(f"Período de calibração: {CALIBRATION_S}s", "DETECÇÃO")
        
        # Atualiza interface
        self.start_button.config(text="⏹ Parar")
        self.status_label.config(text="Calibrando...", foreground=self.colors['warning'])
        
        # Remove placeholder
        self.video_label.pack_forget()
        
        # Inicia thread de processamento
        self.processing_thread = threading.Thread(target=self.process_video)
        self.processing_thread.daemon = True
        self.processing_thread.start()
    
    def stop_detection(self):
        log.section("Parando Detecção de Gestos")
        self.is_running = False
        
        # Finaliza sessão de analytics
        self.analytics.end_session()
        
        if self.cap:
            self.cap.release()
            log.info("Câmera liberada", "CAMERA")
        
        # Atualiza interface
        self.start_button.config(text="▶ Iniciar")
        self.status_label.config(text="Sistema parado", foreground=self.colors['warning'])
        
        # Mostra estatísticas no terminal
        log.section("Estatísticas da Sessão")
        self.analytics.print_stats()
        log.info("Detecção finalizada", "DETECÇÃO")
        
        # Limpa vídeo e mostra placeholder
        if hasattr(self, 'video_display'):
            self.video_display.destroy()
        
        # Recria placeholder
        placeholder_frame = tk.Frame(self.video_container, 
                                    bg=self.colors['video_bg'],
                                    relief='solid',
                                    borderwidth=2,
                                    highlightbackground=self.colors['border_default'])
        placeholder_frame.pack(expand=True, fill='both')
        
        self.video_label = tk.Label(placeholder_frame,
                                    text="📷\n\nCâmera não ativada\n\nClique em 'Iniciar' para começar",
                                    justify='center', font=('Segoe UI', 14),
                                    bg=self.colors['video_bg'], 
                                    fg=self.colors['text_secondary'])
        self.video_label.pack(expand=True)
        
        # Reset status
        self.gesture_status.config(text="neutral")
        self.fps_status.config(text="0.0")
    
    def _process_frame_async(self, frame_data):
        """Processa frame em thread separada - OTIMIZADO"""
        start_time = time.perf_counter()
        
        frame, zoom_level, show_landmarks = frame_data
        
        # Frame pooling: reutiliza buffers pré-alocados
        frame = cv2.flip(frame, 1)
        
        # Reutiliza buffers quando possível
        if self._rgb_buffer is None or self._rgb_buffer.shape != frame.shape:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self._rgb_buffer = rgb
        else:
            cv2.cvtColor(frame, cv2.COLOR_BGR2RGB, dst=self._rgb_buffer)
            rgb = self._rgb_buffer
        
        # OTIMIZAÇÃO: Processa MediaPipe apenas 1x por frame
        res = hands.process(rgb)
        
        # Aplica zoom manual após processamento
        if zoom_level > 1.0:
            frame = apply_manual_zoom(frame, zoom_level)
        
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
            
            # Desenha landmarks se habilitado (usa pre-allocated specs)
            if show_landmarks:
                mp_drawing.draw_landmarks(
                    frame, lm, mp_hands.HAND_CONNECTIONS,
                    _LANDMARK_DRAWING_SPEC,
                    _CONNECTION_DRAWING_SPEC
                )
        
        return raw_action, frame, res
    
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
        
        frame_start_time = time.time()
        
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
                
                try:
                    raw_action, processed_frame, res = self._result_queue.get_nowait()
                except queue.Empty:
                    # OTIMIZAÇÃO: Limitação de FPS
                    elapsed = time.time() - frame_start_time
                    sleep_time = max(0, (1.0 / TARGET_FPS) - elapsed)
                    time.sleep(sleep_time)
                    frame_start_time = time.time()
                    continue
                
                if processed_frame is None:
                    continue
                
                # Adiciona gesto ao histórico e obtém gesto estável
                add_gesture_to_history(raw_action)
                action = get_stable_gesture()
                gesture_confidence = get_gesture_confidence()
                
                frame = processed_frame
            
                now = time.time()
            
                # Calibração inicial
                if now - self.start_ts < CALIBRATION_S:
                    cv2.putText(frame, "Calibrando...", (20,40), cv2.FONT_HERSHEY_SIMPLEX, 1, (220,220,170), 2)
                    self.root.after(0, lambda: self.status_label.config(text="Calibrando...", foreground=self.colors['warning']))
                else:
                    # Lógica de execução de ações com cooldown
                    time_since_last_action = now - self.last_action_time
                    
                    if action == "neutral":
                        # Neutral sempre reseta o flag de ação executada
                        if self.action_executed:
                            self.action_executed = False
                            self.root.after(0, lambda: self.status_label.config(text="✓ Sistema ativo", foreground=self.colors['success']))
                    elif action != "neutral" and not self.action_executed:
                        # Verifica cooldown: só executa se passou tempo suficiente desde última ação
                        if time_since_last_action >= ACTION_COOLDOWN_S:
                            # Mapeamento de ações para log
                            action_map = {
                                "next": ("Próximo", "→"),
                                "prev": ("Anterior", "←"),
                                "home": ("Início", "⇤"),
                                "end": ("Fim", "⇥")
                            }
                            
                            if action == "next":
                                press_next()
                                self.analytics.record_gesture("next")
                                self.root.after(0, lambda: self.status_label.config(text="→ Próximo", foreground=self.colors['gesture_next']))
                            elif action == "prev":
                                press_prev()
                                self.analytics.record_gesture("prev")
                                self.root.after(0, lambda: self.status_label.config(text="← Anterior", foreground=self.colors['gesture_prev']))
                            elif action == "home":
                                press_home()
                                self.analytics.record_gesture("home")
                                self.root.after(0, lambda: self.status_label.config(text="⇤ Início", foreground=self.colors['gesture_home']))
                            elif action == "end":
                                press_end()
                                self.analytics.record_gesture("end")
                                self.root.after(0, lambda: self.status_label.config(text="⇥ Fim", foreground=self.colors['gesture_end']))
                            
                            if action in action_map:
                                action_name, symbol = action_map[action]
                                log.success(f"Comando executado: {action_name} {symbol} (confiança: {gesture_confidence:.0f}%)", "GESTO")
                            
                            self.action_executed = True
                            self.last_action = action
                            self.last_action_time = now  # Registra timestamp da ação
                    elif action != "neutral" and self.action_executed:
                        self.root.after(0, lambda: self.status_label.config(text="Aguardando...", foreground=self.colors['warning']))
                
                # Atualiza indicadores de status com cores
                def update_gesture_ui(gesture, flash_active):
                    # Mapeamento de emojis e cores
                    gesture_config = {
                        "next": ("👆", self.colors['gesture_next']),
                        "prev": ("✌️", self.colors['gesture_prev']),
                        "home": ("🤟", self.colors['gesture_home']),
                        "end": ("🖖", self.colors['gesture_end']),
                        "neutral": ("✊", self.colors['gesture_neutral'])
                    }
                    
                    emoji, color = gesture_config.get(gesture, ("✊", self.colors['gesture_neutral']))
                    
                    # Atualiza header com animação sutil
                    self.header_gesture.config(text=f"{emoji} {gesture}", foreground=color)
                    
                    # Atualiza badge de status
                    self.gesture_status.config(text=gesture, bg=color, 
                                             fg=self.colors['text_on_accent'])
                    
                    # Destaca gesto ativo na lista com efeito visual
                    for gesture_id, label in self.gesture_labels.items():
                        if gesture_id == gesture:
                            # Gesto ativo: negrito + cor + background
                            label.config(font=('Segoe UI', 10, 'bold'), 
                                       foreground=color,
                                       bg=self.colors['bg_tertiary'])
                            
                            # Efeito flash quando executa ação
                            if flash_active and gesture != "neutral":
                                label.config(bg=color, fg=self.colors['text_on_accent'])
                                # Remove flash após 300ms
                                self.root.after(300, lambda l=label: 
                                              l.config(bg=self.colors['bg_tertiary'], 
                                                      fg=color))
                        else:
                            # Gesto inativo: normal
                            label.config(font=('Segoe UI', 10), 
                                       foreground=self.colors['text_primary'],
                                       bg=self.colors['bg_secondary'])
                
                self.root.after(0, lambda: update_gesture_ui(action, self.action_executed and action != "neutral"))
                
                # Atualiza FPS
                stats = self.analytics.get_stats_summary()
                fps_value = stats['performance']['fps']
                
                self.root.after(0, lambda: self.fps_status.config(text=f"{fps_value:.1f}"))
                
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
                
                # OTIMIZAÇÃO: Limitação de FPS
                elapsed = time.time() - frame_start_time
                sleep_time = max(0, (1.0 / TARGET_FPS) - elapsed)
                time.sleep(sleep_time)
                frame_start_time = time.time()
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
        
        log.section("Encerrando WaveControl")
        log.info("Até logo! 👋", "SISTEMA")
        
        self.root.destroy()

# ===== Execução Principal =====
def main():
    # Banner de inicialização
    log.banner()
    
    # Informações do sistema
    log.section("Informações do Sistema")
    log.info(f"Sistema Operacional: {sys.platform}", "SISTEMA")
    log.info(f"Python: {sys.version.split()[0]}", "SISTEMA")
    log.info(f"OpenCV: {cv2.__version__}", "SISTEMA")
    log.info(f"MediaPipe: {mp.__version__}", "SISTEMA")
    
    # Configurações
    log.section("Configurações")
    log.info(f"FPS alvo: {TARGET_FPS}", "CONFIG")
    log.info(f"Cooldown entre ações: {ACTION_COOLDOWN_S}s", "CONFIG")
    log.info(f"Janela de gestos: {GESTURE_WINDOW_SIZE} frames", "CONFIG")
    log.info(f"Calibração inicial: {CALIBRATION_S}s", "CONFIG")
    
    # Inicialização da interface
    log.section("Iniciando Interface Gráfica")
    log.info("Carregando componentes Tkinter...", "GUI")
    
    root = tk.Tk()
    
    # Ícone da janela (opcional)
    try:
        # Se você tiver um arquivo .ico
        # root.iconbitmap('icon.ico')
        pass
    except:
        pass
    
    try:
        app = WaveControlApp(root)
        log.success("Interface carregada com sucesso", "GUI")
        log.info("Pronto para uso!", "GUI")
        
        root.mainloop()
    except KeyboardInterrupt:
        log.warning("Interrompido pelo usuário (Ctrl+C)", "SISTEMA")
    except Exception as e:
        log.error(f"Erro fatal: {e}", "SISTEMA")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
