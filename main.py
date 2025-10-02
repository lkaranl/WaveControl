#!/usr/bin/env python3
import cv2
import time
import os
import sys
import subprocess
import mediapipe as mp
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, GdkPixbuf, Gdk
import threading
from functools import lru_cache
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import queue
from analytics import get_analytics

# ===== Configurações =====
MIN_DET = 0.6
MIN_TRK = 0.6
# Sistema baseado em estado neutral (sem cooldown de tempo)
CALIBRATION_S = 2.0     # tempo inicial para estabilizar câmera
DRAW = True             # mostrar janela com landmarks
CAM_INDEX = 0           # índice da webcam
TARGET_FPS = 30         # FPS alvo (limita uso de CPU)

# ===== Configurações de Zoom =====
DEFAULT_ZOOM = 1.0      # zoom padrão (sem zoom)
MIN_ZOOM = 1.0          # zoom mínimo
MAX_ZOOM = 4.0          # zoom máximo

# ===== Filtro Temporal =====
GESTURE_WINDOW_SIZE = 6  # número de frames para confirmar gesto (reduzido para resposta mais rápida)
CONSISTENCY_THRESHOLD = 0.67  # 67% das amostras devem ser iguais (4 de 6 frames)

# ===== Detecção de ambiente =====
def is_wayland():
    """Detecta se está rodando no Wayland"""
    return os.environ.get('WAYLAND_DISPLAY') is not None or \
           os.environ.get('XDG_SESSION_TYPE') == 'wayland'

# ===== Abstração para entrada de teclado =====
class KeyboardEmulator:
    """Abstração que funciona em X11 e Wayland"""
    
    def __init__(self):
        self.is_wayland = is_wayland()
        self.backend = None
        
        if self.is_wayland:
            print("🌊 Wayland detectado - usando evdev")
            self._init_wayland()
        else:
            print("🪟 X11 detectado - usando uinput")
            self._init_x11()
    
    def _init_x11(self):
        """Inicializa uinput para X11"""
        try:
            import uinput
            self.backend = uinput.Device([
                uinput.KEY_RIGHT, 
                uinput.KEY_LEFT, 
                uinput.KEY_HOME, 
                uinput.KEY_END
            ])
            self.backend_type = 'uinput'
        except Exception as e:
            print(f"❌ Erro ao inicializar uinput: {e}")
            print("💡 Execute: sudo modprobe uinput")
            print("💡 Adicione seu usuário ao grupo input:")
            print(f"   sudo usermod -aG input {os.getenv('USER')}")
            sys.exit(1)
    
    def _init_wayland(self):
        """Inicializa evdev para Wayland"""
        try:
            import evdev
            from evdev import UInput, ecodes as e
            
            # Criar dispositivo virtual com as teclas necessárias
            capabilities = {
                e.EV_KEY: [
                    e.KEY_RIGHT,
                    e.KEY_LEFT,
                    e.KEY_HOME,
                    e.KEY_END
                ]
            }
            
            self.backend = UInput(capabilities, name='WaveControl-Virtual-Keyboard')
            self.ecodes = e
            self.backend_type = 'evdev'
            print("✅ evdev inicializado com sucesso (Wayland)")
            
        except ImportError:
            print("❌ evdev não está instalado!")
            print("")
            print("Instale com:")
            print("  pip install evdev")
            print("")
            sys.exit(1)
        except PermissionError:
            print("❌ Sem permissão para criar dispositivo virtual!")
            print("")
            print("Execute com sudo ou configure uinput:")
            print("  sudo modprobe uinput")
            print("  sudo usermod -aG input $USER")
            print("")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Erro ao inicializar evdev: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    def emit_key(self, key_name):
        """Emite um pressionar de tecla"""
        if self.backend_type == 'uinput':
            import uinput
            key_map = {
                'right': uinput.KEY_RIGHT,
                'left': uinput.KEY_LEFT,
                'home': uinput.KEY_HOME,
                'end': uinput.KEY_END
            }
            self.backend.emit_click(key_map[key_name])
            
        elif self.backend_type == 'evdev':
            # Mapeamento de teclas para evdev
            key_map = {
                'right': self.ecodes.KEY_RIGHT,
                'left': self.ecodes.KEY_LEFT,
                'home': self.ecodes.KEY_HOME,
                'end': self.ecodes.KEY_END
            }
            
            try:
                key = key_map[key_name]
                # Pressionar tecla
                self.backend.write(self.ecodes.EV_KEY, key, 1)
                self.backend.syn()
                # Soltar tecla
                self.backend.write(self.ecodes.EV_KEY, key, 0)
                self.backend.syn()
            except KeyError:
                print(f"❌ Tecla '{key_name}' não mapeada!")
            except Exception as e:
                print(f"⚠️  Erro ao emitir tecla {key_name}: {e}")
                import traceback
                traceback.print_exc()

# Inicializar emulador de teclado
kb = KeyboardEmulator()

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

def count_extended(lm, handed_label):
    cnt = 0
    for name in _FINGER_NAMES:
        if finger_extended(lm, TIP[name], PIP[name], handed_label):
            cnt += 1
    return cnt

def get_extended_fingers(lm, handed_label):
    """Retorna lista de dedos estendidos para análise detalhada"""
    extended = []
    for name in _FINGER_NAMES:
        if finger_extended(lm, TIP[name], PIP[name], handed_label):
            extended.append(name)
    return extended

# ===== Histórico de Gestos =====
gesture_history = []

def add_gesture_to_history(gesture):
    """Adiciona gesto ao histórico e mantém tamanho da janela"""
    gesture_history.append(gesture)
    if len(gesture_history) > GESTURE_WINDOW_SIZE:
        gesture_history.pop(0)

def get_stable_gesture():
    """
    Retorna gesto estável baseado no histórico - otimizado com Counter
    Agora com confiança adaptativa e mais sensível
    """
    if len(gesture_history) < 4:  # Reduzido para responder mais rápido
        return "neutral"
    
    # Usa Counter para contar eficientemente
    gesture_counts = Counter(gesture_history)
    
    # Encontra o gesto mais frequente
    most_common_gesture, most_common_count = gesture_counts.most_common(1)[0]
    
    # Verifica se atende o threshold de consistência
    consistency_ratio = most_common_count / len(gesture_history)
    
    # Threshold adaptativo: gestos diferentes requerem consistência diferente
    threshold = CONSISTENCY_THRESHOLD
    if most_common_gesture == "neutral":
        threshold = 0.4  # Mais fácil voltar para neutral
    elif most_common_gesture == "next":  # Gesto número 1
        threshold = 0.5  # Bem mais sensível para gesto 1 (50% = 3 de 6 frames)
    
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
    kb.emit_key('right')

def press_prev():
    kb.emit_key('left')

def press_home():
    kb.emit_key('home')

def press_end():
    kb.emit_key('end')

def apply_manual_zoom(frame, zoom_level=1.0):
    """
    Aplica zoom digital manual centralizado
    
    Args:
        frame: Frame original
        zoom_level: Nível de zoom (1.0 = sem zoom, 2.0 = 2x, etc.)
    
    Returns:
        Frame com zoom aplicado
    """
    if zoom_level <= 1.0:
        return frame
    
    height, width = frame.shape[:2]
    
    # Calcula dimensões do ROI (região de interesse)
    crop_width = int(width / zoom_level)
    crop_height = int(height / zoom_level)
    
    # Centraliza o ROI
    start_x = (width - crop_width) // 2
    start_y = (height - crop_height) // 2
    end_x = start_x + crop_width
    end_y = start_y + crop_height
    
    # Extrai ROI e redimensiona para tamanho original
    cropped = frame[start_y:end_y, start_x:end_x]
    zoomed = cv2.resize(cropped, (width, height), interpolation=cv2.INTER_LINEAR)
    
    return zoomed

# ===== Interface Gráfica GTK =====
class WaveControlGUI(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self)
        # Configuração inicial da janela
        self.set_default_size(1000, 600)
        self.set_position(Gtk.WindowPosition.CENTER)
        
        # Permite maximizar e redimensionar
        self.set_resizable(True)
        
        # Aplicar CSS moderno
        self.apply_modern_styling()
        
        # Variáveis de controle
        self.is_running = False
        self.cap = None
        self.start_ts = None
        self.last_action = "neutral"
        self.action_executed = False
        self.zoom_level = DEFAULT_ZOOM
        
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
        
        # Setup da interface
        self.setup_ui()
        
        # Conecta eventos
        self.connect("destroy", self.on_window_destroy)
        self.connect("key-press-event", self.on_key_press)
        
        # Inicia automaticamente
        GLib.idle_add(self.start_detection)
    
    def apply_modern_styling(self):
        """Aplica estilo harmonioso respeitando o tema GTK"""
        css_provider = Gtk.CssProvider()
        css = """
        /* Layout harmonioso com cores do sistema GTK */
        
        /* Container principal */
        .main-container {
            background: @theme_bg_color;
        }
        
        /* Header moderno com gradiente sutil */
        .header-toolbar {
            padding: 16px 24px;
            background: linear-gradient(to bottom, @theme_bg_color, alpha(@theme_bg_color, 0.98));
            border-bottom: 1px solid alpha(@borders, 0.3);
            box-shadow: 0 2px 4px alpha(black, 0.08);
            min-height: 52px;
        }
        
        .app-title {
            font-size: 20px;
            font-weight: 600;
            color: @theme_fg_color;
        }
        
        .header-separator {
            font-size: 20px;
            color: alpha(@theme_fg_color, 0.3);
        }
        
        .header-gesture {
            font-size: 18px;
            font-weight: 700;
            color: @theme_selected_bg_color;
            padding: 6px 16px;
            background: alpha(@theme_selected_bg_color, 0.1);
            border-radius: 8px;
            border: 2px solid alpha(@theme_selected_bg_color, 0.3);
            transition: all 300ms cubic-bezier(0.4, 0.0, 0.2, 1);
        }
        
        /* Sidebar elegante */
        .sidebar {
            padding: 0 16px;
            background: alpha(@theme_bg_color, 0.95);
            border-right: 1px solid alpha(@borders, 0.2);
            box-shadow: 1px 0 3px alpha(black, 0.05);
        }
        
        /* Área principal responsiva */
        .main-content {
            padding: 20px;
            background: @theme_base_color;
            margin-right: 20px;
        }
        
        /* Container de vídeo aprimorado */
        .video-area {
            border-radius: 20px;
            background: @theme_base_color;
            box-shadow: 0 8px 24px alpha(black, 0.15);
        }
        
        .video-container {
            background: black;
            border-radius: 20px;
            min-height: 400px;
            border: 3px solid alpha(@borders, 0.3);
            transition: border-color 300ms ease;
        }
        
        /* Estados de detecção de mão */
        .hand-detected {
            border-color: #4CAF50;
            box-shadow: 0 0 20px alpha(#4CAF50, 0.3);
        }
        
        .hand-partial {
            border-color: #FFC107;
            box-shadow: 0 0 20px alpha(#FFC107, 0.3);
        }
        
        .hand-none {
            border-color: alpha(@borders, 0.3);
        }
        
        .video-placeholder {
            font-size: 16px;
            color: alpha(@theme_fg_color, 0.7);
        }
        
        /* Cards harmonioso com micro-interações */
        .compact-card {
            background: @theme_base_color;
            border: 1px solid alpha(@borders, 0.2);
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 0;
            box-shadow: 0 1px 3px alpha(black, 0.05);
            transition: all 250ms cubic-bezier(0.4, 0.0, 0.2, 1);
        }
        
        .compact-card:hover {
            box-shadow: 0 4px 12px alpha(black, 0.12);
            border-color: alpha(@theme_selected_bg_color, 0.3);
        }
        
        .card-title {
            font-size: 15px;
            font-weight: 600;
            margin-bottom: 12px;
            color: @theme_fg_color;
            border-bottom: 2px solid @theme_selected_bg_color;
            padding-bottom: 6px;
        }
        
        /* Botões modernos com feedback visual */
        .primary-button {
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: 600;
            min-height: 40px;
            min-width: 100px;
            transition: all 200ms cubic-bezier(0.4, 0.0, 0.2, 1);
            box-shadow: 0 1px 3px alpha(black, 0.1);
        }
        
        .primary-button:hover {
            box-shadow: 0 4px 8px alpha(black, 0.2);
        }
        
        .primary-button:active {
            box-shadow: 0 1px 2px alpha(black, 0.15);
        }
        
        .secondary-button {
            padding: 8px 14px;
            border-radius: 6px;
            font-size: 14px;
            margin: 5px;
            transition: all 150ms ease;
        }
        
        .secondary-button:hover {
            background: alpha(@theme_selected_bg_color, 0.1);
        }
        
        /* Indicadores de status aprimorados */
        .status-indicator {
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 600;
            background: @theme_selected_bg_color;
            color: @theme_selected_fg_color;
            box-shadow: 0 1px 2px alpha(black, 0.1);
            transition: all 300ms cubic-bezier(0.4, 0.0, 0.2, 1);
        }
        
        .status-indicator-subtle {
            padding: 4px 10px;
            border-radius: 5px;
            font-size: 13px;
            font-weight: 500;
            background: alpha(@theme_fg_color, 0.08);
            color: alpha(@theme_fg_color, 0.7);
        }
        
        /* Indicadores de gestos específicos com cores */
        .gesture-next {
            background: #4CAF50;
            color: white;
        }
        
        .gesture-prev {
            background: #2196F3;
            color: white;
        }
        
        .gesture-home {
            background: #FF9800;
            color: white;
        }
        
        .gesture-end {
            background: #F44336;
            color: white;
        }
        
        .gesture-neutral {
            background: alpha(@theme_fg_color, 0.2);
            color: @theme_fg_color;
        }
        
        .status-grid {
            background: alpha(@theme_bg_color, 0.5);
            border-radius: 8px;
            padding: 12px;
            border: 1px solid alpha(@borders, 0.15);
        }
        
        .status-item {
            margin: 4px 0;
            padding: 10px 0;
        }
        
        .status-label {
            font-size: 14px;
            color: alpha(@theme_fg_color, 0.8);
        }
        
        /* Zoom minimalista inline */
        .zoom-inline-minimal {
            padding: 6px 0;
            border-top: 1px solid alpha(@borders, 0.15);
        }
        
        .zoom-value-minimal {
            font-size: 13px;
            font-weight: 600;
            color: @theme_selected_bg_color;
            min-width: 36px;
        }
        
        .zoom-slider-minimal scale {
            min-height: 20px;
        }
        
        .zoom-slider-minimal scale trough {
            min-height: 4px;
            background: alpha(@borders, 0.2);
            border-radius: 2px;
        }
        
        .zoom-slider-minimal scale highlight {
            background: @theme_selected_bg_color;
            border-radius: 2px;
        }
        
        .zoom-slider-minimal scale slider {
            min-width: 14px;
            min-height: 14px;
            margin: -5px;
            background: @theme_selected_bg_color;
            border: 2px solid @theme_base_color;
            border-radius: 50%;
            box-shadow: 0 1px 3px alpha(black, 0.15);
        }
        
        .zoom-slider-minimal scale slider:hover {
            box-shadow: 0 2px 6px alpha(black, 0.25);
        }
        
        /* Área de gestos */
        .gestures-compact {
            background: alpha(@theme_bg_color, 0.3);
            border-radius: 8px;
            padding: 12px;
            border: 1px solid alpha(@borders, 0.15);
        }
        
        .gesture-compact {
            font-size: 14px;
            padding: 8px 12px;
            margin: 2px 0;
            border-radius: 6px;
            color: alpha(@theme_fg_color, 0.9);
            transition: all 300ms cubic-bezier(0.4, 0.0, 0.2, 1);
            background: transparent;
        }
        
        /* Gesto ativo - pulsação suave */
        .gesture-active {
            background: alpha(@theme_selected_bg_color, 0.15);
            font-weight: 600;
            box-shadow: 0 0 0 2px alpha(@theme_selected_bg_color, 0.3);
        }
        
        /* Efeito flash quando executa ação */
        .gesture-flash {
            background: @theme_selected_bg_color;
            color: @theme_selected_fg_color;
            box-shadow: 0 0 12px alpha(@theme_selected_bg_color, 0.8);
        }
        
        /* Calibração */
        .calibration-container {
            background: alpha(@theme_selected_bg_color, 0.05);
            border-radius: 8px;
            padding: 12px;
        }
        
        .calibration-label {
            font-size: 13px;
            font-weight: 600;
            color: @theme_selected_bg_color;
            margin-bottom: 4px;
        }
        
        .calibration-progress {
            min-height: 6px;
        }
        
        .calibration-progress progress {
            background: alpha(@borders, 0.2);
            border-radius: 3px;
        }
        
        .calibration-progress trough {
            min-height: 6px;
            background: alpha(@borders, 0.2);
            border-radius: 3px;
        }
        
        .calibration-progress progress {
            background: @theme_selected_bg_color;
            border-radius: 3px;
        }
        
        /* Indicador de status da mão */
        .hand-status-label {
            font-size: 12px;
            font-weight: 600;
            padding: 6px 12px;
            border-radius: 6px;
            background: alpha(@theme_bg_color, 0.8);
        }
        
        /* Rodapé minimalista */
        .footer {
            background: alpha(@theme_bg_color, 0.8);
            border-top: 1px solid alpha(@borders, 0.2);
            padding: 8px 24px;
        }
        
        /* Barra de rolagem personalizada */
        scrolledwindow {
            background: transparent;
        }
        
        scrollbar {
            background: alpha(@theme_bg_color, 0.1);
            border-radius: 6px;
        }
        
        scrollbar slider {
            background: alpha(@theme_fg_color, 0.3);
            border-radius: 6px;
            min-height: 20px;
            min-width: 6px;
        }
        
        scrollbar slider:hover {
            background: alpha(@theme_fg_color, 0.5);
        }
        """
        css_provider.load_from_data(css.encode('utf-8'))
        screen = Gdk.Screen.get_default()
        style_context = Gtk.StyleContext()
        style_context.add_provider_for_screen(screen, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        
    def setup_ui(self):
        # Container principal
        main_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main_container.get_style_context().add_class("main-container")
        self.add(main_container)
        
        # Header toolbar elegante
        header_toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        header_toolbar.get_style_context().add_class("header-toolbar")
        
        # Seção esquerda do header - título e gesto atual
        header_left = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        
        # Título da aplicação
        title_label = Gtk.Label(label="WaveControl")
        title_label.get_style_context().add_class("app-title")
        title_label.set_halign(Gtk.Align.START)
        
        # Separador visual
        separator = Gtk.Label(label="|")
        separator.get_style_context().add_class("header-separator")
        separator.set_opacity(0.3)
        
        # Gesto atual no header (grande e visual)
        self.header_gesture = Gtk.Label(label="✊ neutral")
        self.header_gesture.get_style_context().add_class("header-gesture")
        self.header_gesture.set_halign(Gtk.Align.START)
        
        header_left.pack_start(title_label, False, False, 0)
        header_left.pack_start(separator, False, False, 0)
        header_left.pack_start(self.header_gesture, False, False, 0)
        
        # Seção direita do header - controles
        header_right = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        
        # Botão principal no header
        self.header_start_button = Gtk.Button.new_with_label("▶ Iniciar")
        self.header_start_button.get_style_context().add_class("primary-button")
        self.header_start_button.connect("clicked", self.on_start_clicked)
        self.header_start_button.set_tooltip_text("Inicia ou para a detecção de gestos")
        
        header_right.pack_start(self.header_start_button, False, False, 0)
        
        header_toolbar.pack_start(header_left, False, False, 0)
        header_toolbar.pack_end(header_right, False, False, 0)
        main_container.pack_start(header_toolbar, False, False, 0)
        
        # Layout principal fluido
        main_layout = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        main_layout.get_style_context().add_class("main-layout")
        main_container.pack_start(main_layout, True, True, 0)
        
        # === SIDEBAR ELEGANTE ===
        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_min_content_width(280)
        sidebar_scroll.set_max_content_width(320)
        
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        sidebar.get_style_context().add_class("sidebar")
        sidebar_scroll.add(sidebar)
        main_layout.pack_start(sidebar_scroll, False, False, 0)
        
        # Card de Gestos Compacto (PRIMEIRO)
        gestures_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        gestures_card.get_style_context().add_class("compact-card")
        
        gestures_title = Gtk.Label(label="Gestos")
        gestures_title.get_style_context().add_class("card-title")
        gestures_title.set_halign(Gtk.Align.START)
        
        # Grid de gestos compacto
        gestures_compact = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        gestures_compact.get_style_context().add_class("gestures-compact")
        
        # Mapeia gestos para labels (para animação)
        gestures_data = [
            ("next", "👆 1 → Próximo"),
            ("prev", "✌️ 2 → Anterior"),
            ("home", "🤟 3 → Início"), 
            ("end", "🖖 4 → Fim"),
            ("neutral", "✊ 0 → Neutro")
        ]
        
        # Dicionário para acessar labels dos gestos
        self.gesture_labels = {}
        
        for gesture_id, gesture_text in gestures_data:
            gesture_item = Gtk.Label(label=gesture_text)
            gesture_item.get_style_context().add_class("gesture-compact")
            gesture_item.set_halign(Gtk.Align.START)
            gestures_compact.pack_start(gesture_item, False, False, 0)
            self.gesture_labels[gesture_id] = gesture_item
        
        gestures_card.pack_start(gestures_title, False, False, 0)
        gestures_card.pack_start(gestures_compact, False, False, 0)
        sidebar.pack_start(gestures_card, False, False, 0)
        
        # Card de Status Compacto
        status_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        status_card.get_style_context().add_class("compact-card")
        
        status_title = Gtk.Label(label="Status do Sistema")
        status_title.get_style_context().add_class("card-title")
        status_title.set_halign(Gtk.Align.START)
        
        # Grid de status enxuto
        status_grid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        status_grid.get_style_context().add_class("status-grid")
        
        # Gesto Atual (grande e destacado)
        action_item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        action_item.get_style_context().add_class("status-item")
        
        action_label = Gtk.Label(label="Gesto:")
        action_label.get_style_context().add_class("status-label")
        
        self.action_indicator = Gtk.Label(label="neutral")
        self.action_indicator.get_style_context().add_class("status-indicator")
        self.action_indicator.get_style_context().add_class("gesture-neutral")
        self.action_indicator.set_tooltip_text("Gesto detectado atualmente")
        
        action_item.pack_start(action_label, False, False, 0)
        action_item.pack_end(self.action_indicator, False, False, 0)
        
        # FPS
        fps_item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        fps_item.get_style_context().add_class("status-item")
        
        fps_label = Gtk.Label(label="FPS:")
        fps_label.get_style_context().add_class("status-label")
        
        self.fps_label = Gtk.Label(label="0.0")
        self.fps_label.get_style_context().add_class("status-indicator-subtle")
        self.fps_label.set_tooltip_text("Taxa de quadros por segundo")
        
        fps_item.pack_start(fps_label, False, False, 0)
        fps_item.pack_end(self.fps_label, False, False, 0)
        
        # Slider de Zoom Minimalista Inline
        zoom_inline_item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        zoom_inline_item.get_style_context().add_class("zoom-inline-minimal")
        zoom_inline_item.set_margin_top(8)
        
        zoom_inline_label = Gtk.Label(label="Zoom:")
        zoom_inline_label.get_style_context().add_class("status-label")
        zoom_inline_label.set_opacity(0.7)
        
        self.zoom_value_label = Gtk.Label(label=f"{DEFAULT_ZOOM:.1f}x")
        self.zoom_value_label.get_style_context().add_class("zoom-value-minimal")
        self.zoom_value_label.set_opacity(0.8)
        
        zoom_adjustment = Gtk.Adjustment(
            value=DEFAULT_ZOOM,
            lower=MIN_ZOOM,
            upper=MAX_ZOOM,
            step_increment=0.1,
            page_increment=0.5,
            page_size=0
        )
        self.zoom_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=zoom_adjustment)
        self.zoom_scale.set_digits(1)
        self.zoom_scale.set_draw_value(False)
        self.zoom_scale.set_size_request(120, -1)
        self.zoom_scale.get_style_context().add_class("zoom-slider-minimal")
        self.zoom_scale.connect("value-changed", self.on_zoom_changed)
        
        zoom_inline_item.pack_start(zoom_inline_label, False, False, 0)
        zoom_inline_item.pack_start(self.zoom_scale, True, True, 0)
        zoom_inline_item.pack_end(self.zoom_value_label, False, False, 0)
        
        status_grid.pack_start(action_item, False, False, 0)
        status_grid.pack_start(fps_item, False, False, 0)
        status_grid.pack_start(zoom_inline_item, False, False, 0)
        
        status_card.pack_start(status_title, False, False, 0)
        status_card.pack_start(status_grid, False, False, 0)
        sidebar.pack_start(status_card, False, False, 0)
        
        # === ÁREA PRINCIPAL MAXIMIZADA ===
        main_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main_content.get_style_context().add_class("main-content")
        main_layout.pack_start(main_content, True, True, 0)
        
        # === ÁREA DE VÍDEO PRINCIPAL ===
        video_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        video_area.get_style_context().add_class("video-area")
        
        # Container do vídeo com padding harmonioso
        video_wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        video_wrapper.set_margin_top(8)
        video_wrapper.set_margin_bottom(8)
        video_wrapper.set_margin_start(8)
        video_wrapper.set_margin_end(8)
        
        # Container do vídeo responsivo
        video_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        video_container.get_style_context().add_class("video-container")
        
        # EventBox para capturar cliques e ativar modo teatro
        self.video_event_box = Gtk.EventBox()
        self.video_event_box.connect("button-press-event", self.on_video_clicked)
        
        # Variável para controlar modo teatro
        self.theater_mode = False
        
        self.video_image = Gtk.Image()
        self.video_image.set_halign(Gtk.Align.CENTER)
        self.video_image.set_valign(Gtk.Align.CENTER)
        
        # Placeholder elegante
        placeholder_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        placeholder_box.set_halign(Gtk.Align.CENTER)
        placeholder_box.set_valign(Gtk.Align.CENTER)
        
        # Ícone do placeholder
        placeholder_icon = Gtk.Label(label="📷")
        placeholder_icon.set_markup("<span size='48000'>📷</span>")
        
        # Texto do placeholder
        self.placeholder_label = Gtk.Label()
        self.placeholder_label.set_markup("<span size='large'>Câmera não ativada</span>\n\n<span alpha='70%'>Clique em '▶ Iniciar' para começar</span>")
        self.placeholder_label.get_style_context().add_class("video-placeholder")
        self.placeholder_label.set_justify(Gtk.Justification.CENTER)
        
        placeholder_box.pack_start(placeholder_icon, False, False, 0)
        placeholder_box.pack_start(self.placeholder_label, False, False, 0)
        
        video_container.pack_start(self.video_image, True, True, 0)
        video_container.pack_start(placeholder_box, True, True, 0)
        
        # Envolver video_container no EventBox para capturar cliques
        self.video_event_box.add(video_container)
        
        video_wrapper.pack_start(self.video_event_box, True, True, 0)
        
        # === BARRA DE PROGRESSO DE CALIBRAÇÃO ===
        calibration_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        calibration_box.set_margin_top(8)
        calibration_box.set_margin_start(8)
        calibration_box.set_margin_end(8)
        calibration_box.get_style_context().add_class("calibration-container")
        
        # Label de calibração
        self.calibration_label = Gtk.Label(label="")
        self.calibration_label.get_style_context().add_class("calibration-label")
        self.calibration_label.set_halign(Gtk.Align.START)
        
        # Progress bar
        self.calibration_progress = Gtk.ProgressBar()
        self.calibration_progress.get_style_context().add_class("calibration-progress")
        self.calibration_progress.set_show_text(False)
        self.calibration_progress.set_fraction(0.0)
        
        calibration_box.pack_start(self.calibration_label, False, False, 0)
        calibration_box.pack_start(self.calibration_progress, False, False, 0)
        
        # Esconde por padrão
        calibration_box.hide()
        self.calibration_box = calibration_box
        
        video_wrapper.pack_start(calibration_box, False, False, 0)
        
        # Indicador visual de detecção de mão
        self.hand_status_label = Gtk.Label(label="")
        self.hand_status_label.get_style_context().add_class("hand-status-label")
        self.hand_status_label.set_halign(Gtk.Align.CENTER)
        self.hand_status_label.set_margin_top(8)
        self.hand_status_label.hide()
        video_wrapper.pack_start(self.hand_status_label, False, False, 0)
        
        video_area.pack_start(video_wrapper, True, True, 0)
        main_content.pack_start(video_area, True, True, 0)
        
        # === RODAPÉ ELEGANTE ===
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        footer.get_style_context().add_class("footer")
        footer.set_size_request(-1, 32)
        
        # Informações do rodapé
        footer_info = Gtk.Label(label="WaveControl - Controle por gestos | Criado por Karan Luciano")
        footer_info.set_halign(Gtk.Align.START)
        footer_info.get_style_context().add_class("status-label")
        
        # Atalhos de teclado
        shortcuts_label = Gtk.Label(label="⌨️ Espaço: Iniciar/Parar • Z: Zoom • Esc: Sair")
        shortcuts_label.set_halign(Gtk.Align.CENTER)
        shortcuts_label.get_style_context().add_class("status-label")
        shortcuts_label.set_opacity(0.6)
        
        # Label discreta mostrando o backend (X11 ou Wayland)
        backend_name = "Wayland (evdev)" if is_wayland() else "X11 (uinput)"
        backend_label = Gtk.Label(label=f"🖥️ {backend_name}")
        backend_label.set_halign(Gtk.Align.END)
        backend_label.get_style_context().add_class("status-label")
        backend_label.set_opacity(0.7)  # Torna mais discreto
        
        footer.pack_start(footer_info, True, True, 0)
        footer.pack_start(shortcuts_label, False, False, 0)
        footer.pack_end(backend_label, False, False, 0)
        main_container.pack_end(footer, False, False, 0)
        
    def on_zoom_changed(self, scale):
        self.zoom_level = scale.get_value()
        self.zoom_value_label.set_text(f"{self.zoom_level:.1f}x")
    
    def set_zoom(self, zoom_value):
        self.zoom_level = zoom_value
        self.zoom_scale.set_value(zoom_value)
        self.zoom_value_label.set_text(f"{zoom_value:.1f}x")
    
    def on_key_press(self, widget, event):
        """
        Captura eventos de teclado - Atalhos:
        - Espaço: Iniciar/Parar detecção
        - Esc: Sair do modo teatro ou fechar app
        - Z: Ciclar zoom (1x → 2x → 3x → 4x → 1x)
        """
        # Esc: Sair do modo teatro ou fechar app
        if event.keyval == Gdk.KEY_Escape:
            if self.theater_mode:
                self.theater_mode = False
                self.unfullscreen()
                return True
            else:
                # Fecha a aplicação
                self.on_window_destroy(widget)
                return True
        
        # Espaço: Iniciar/Parar
        elif event.keyval == Gdk.KEY_space:
            self.on_start_clicked(None)
            return True
        
        # Z: Ciclar zoom (1x → 2x → 3x → 4x → 1x)
        elif event.keyval == Gdk.KEY_z or event.keyval == Gdk.KEY_Z:
            current_zoom = self.zoom_level
            zoom_levels = [1.0, 2.0, 3.0, 4.0]
            
            # Encontra próximo nível de zoom
            try:
                current_index = zoom_levels.index(current_zoom)
                next_index = (current_index + 1) % len(zoom_levels)
            except ValueError:
                next_index = 0
            
            next_zoom = zoom_levels[next_index]
            self.set_zoom(next_zoom)
            return True
        
        return False
    
    def on_video_clicked(self, widget, event):
        """
        Toggle modo teatro (fullscreen) ao clicar duplo no vídeo
        Clique duplo = fullscreen, Esc para sair
        """
        if not self.is_running:
            return
        
        # Detectar clique duplo (type == 5 é GDK_2BUTTON_PRESS)
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            self.theater_mode = not self.theater_mode
            
            if self.theater_mode:
                self.fullscreen()
            else:
                self.unfullscreen()
    
    def on_start_clicked(self, button):
        if not self.is_running:
            self.start_detection()
        else:
            self.stop_detection()
            
    def start_detection(self):
        global gesture_history
        gesture_history.clear()
        
        self.cap = cv2.VideoCapture(CAM_INDEX)
        # Define resolução da captura
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 800)   # Largura
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 800)  # Altura
        if not self.cap.isOpened():
            dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
    text="Erro ao acessar a câmera"
            )
            dialog.format_secondary_text("Verifique se a câmera está conectada e disponível.")
            dialog.run()
            dialog.destroy()
            return
            
        self.is_running = True
        self.start_ts = time.time()
        
        # Inicia sessão de analytics
        self.analytics.start_session()
        self.analytics.set_calibration_time(CALIBRATION_S)
        
        self.header_start_button.set_label("⏹ Parar")
        
        # Esconde placeholder e mostra vídeo
        self.placeholder_label.get_parent().hide()
        self.video_image.show()
        
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
        self.header_start_button.set_label("▶ Iniciar")
        
        # Mostra estatísticas no terminal
        print("\n" + "="*50)
        self.analytics.print_stats()
        print("="*50 + "\n")
        
        # Mostra placeholder e esconde vídeo
        self.video_image.clear()
        self.video_image.hide()
        self.placeholder_label.get_parent().show()
        
        # Reset dos indicadores
        self.action_indicator.set_text("neutral")
        self.header_gesture.set_text("✊ neutral")
        self.fps_label.set_text("0.0")
        
        # Reset métricas
        # Removido: labels de métricas simplificadas
        
    def _process_frame_async(self, frame_data):
        """Processa frame em thread separada - OTIMIZADO"""
        start_time = time.perf_counter()
        
        frame, zoom_level, show_landmarks = frame_data
        
        # Frame pooling: reutiliza buffers pré-alocados
        frame = cv2.flip(frame, 1)
        
        # Converte para RGB e processa MediaPipe UMA ÚNICA VEZ
        # Reutiliza buffers quando possível
        if self._rgb_buffer is None or self._rgb_buffer.shape != frame.shape:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self._rgb_buffer = rgb
        else:
            cv2.cvtColor(frame, cv2.COLOR_BGR2RGB, dst=self._rgb_buffer)
            rgb = self._rgb_buffer
        
        res = hands.process(rgb)
        
        # Pega landmarks se disponível
        hand_landmarks = None
        if res.multi_hand_landmarks:
            hand_landmarks = res.multi_hand_landmarks[0].landmark
        
        # Aplica zoom manual no frame BGR (após detecção)
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
            
            # Desenha landmarks se habilitado (no frame com zoom aplicado)
            if show_landmarks:
                mp_drawing.draw_landmarks(
                    frame, lm, mp_hands.HAND_CONNECTIONS,
                    mp_drawing.DrawingSpec(color=(0,255,0), thickness=2, circle_radius=2),
                    mp_drawing.DrawingSpec(color=(255,0,0), thickness=2)
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
        # Inicia thread de processamento assíncrono
        self._processing_active = True
        processor_thread = threading.Thread(target=self._gesture_processor_thread, daemon=True)
        processor_thread.start()
        
        # Controle de FPS
        frame_time = 1.0 / TARGET_FPS
        last_frame_time = time.time()
        
        try:
            while self.is_running and self.cap and self.cap.isOpened():
                # Limita FPS para economizar CPU
                current_time = time.time()
                elapsed = current_time - last_frame_time
                if elapsed < frame_time:
                    time.sleep(frame_time - elapsed)
                last_frame_time = time.time()
                
                ok, frame = self.cap.read()
                if not ok:
                    break
                
                # Envia frame para processamento assíncrono
                try:
                    frame_data = (frame.copy(), self.zoom_level, DRAW)  # Usar constante DRAW
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
                    continue
                
                if processed_frame is None:
                    continue
                
                # Adiciona gesto ao histórico e obtém gesto estável
                add_gesture_to_history(raw_action)
                action = get_stable_gesture()
                gesture_confidence = get_gesture_confidence()
                
                frame = processed_frame
            
                now = time.time()
                
                # Atualiza indicador visual de detecção de mão
                def update_hand_detection_visual(has_hand):
                    video_ctx = self.video_event_box.get_children()[0].get_style_context()
                    
                    # Remove todas as classes de estado
                    video_ctx.remove_class("hand-detected")
                    video_ctx.remove_class("hand-partial")
                    video_ctx.remove_class("hand-none")
                    
                    if has_hand:
                        video_ctx.add_class("hand-detected")
                        self.hand_status_label.set_text("🟢 Mão detectada")
                        self.hand_status_label.show()
                    else:
                        video_ctx.add_class("hand-none")
                        self.hand_status_label.set_text("🔴 Nenhuma mão detectada")
                        self.hand_status_label.show()
                
                has_hand = res is not None and res.multi_hand_landmarks is not None and len(res.multi_hand_landmarks) > 0
                GLib.idle_add(update_hand_detection_visual, has_hand)
                
                # Calibração inicial com feedback visual
                elapsed_calibration = now - self.start_ts
                if elapsed_calibration < CALIBRATION_S:
                    cv2.putText(frame, "Calibrando...", (20,40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
                    
                    # Atualiza barra de progresso de calibração
                    progress = min(elapsed_calibration / CALIBRATION_S, 1.0)
                    remaining_time = max(0, CALIBRATION_S - elapsed_calibration)
                    
                    def update_calibration_ui(prog, remaining):
                        self.calibration_box.show()
                        self.calibration_label.set_text(f"Calibrando sistema... {remaining:.1f}s restantes")
                        self.calibration_progress.set_fraction(prog)
                    
                    GLib.idle_add(update_calibration_ui, progress, remaining_time)
                else:
                    # Esconde barra de calibração após finalizar
                    GLib.idle_add(self.calibration_box.hide)
                    # Lógica de execução de ações
                    if action == "neutral":
                        if self.action_executed:
                            self.action_executed = False
                    elif action != "neutral" and not self.action_executed:
                        if action == "next":
                            press_next()
                            self.analytics.record_gesture("next")
                        elif action == "prev":
                            press_prev()
                            self.analytics.record_gesture("prev")
                        elif action == "home":
                            press_home()
                            self.analytics.record_gesture("home")
                        elif action == "end":
                            press_end()
                            self.analytics.record_gesture("end")
                        self.action_executed = True
                        self.last_action = action
                
                # Atualiza indicadores de status com feedback visual
                def update_gesture_indicator(gesture, flash_active):
                    # Mapeamento de emojis por gesto
                    emoji_map = {
                        "next": "👆",
                        "prev": "✌️",
                        "home": "🤟",
                        "end": "🖖",
                        "neutral": "✊"
                    }
                    
                    # Atualiza header com emoji
                    emoji = emoji_map.get(gesture, "✊")
                    self.header_gesture.set_text(f"{emoji} {gesture}")
                    
                    # Atualiza indicador de status (badge colorido)
                    ctx = self.action_indicator.get_style_context()
                    for cls in ["gesture-next", "gesture-prev", "gesture-home", "gesture-end", "gesture-neutral"]:
                        ctx.remove_class(cls)
                    ctx.add_class(f"gesture-{gesture}")
                    self.action_indicator.set_text(gesture)
                    
                    # Atualiza visual dos cards de gestos
                    for gesture_id, label in self.gesture_labels.items():
                        label_ctx = label.get_style_context()
                        label_ctx.remove_class("gesture-active")
                        label_ctx.remove_class("gesture-flash")
                        
                        # Marca o gesto ativo
                        if gesture_id == gesture:
                            label_ctx.add_class("gesture-active")
                            
                            # Flash quando executa ação
                            if flash_active and gesture != "neutral":
                                label_ctx.add_class("gesture-flash")
                                
                                # Remove flash após 400ms
                                def remove_flash():
                                    label_ctx.remove_class("gesture-flash")
                                    return False
                                GLib.timeout_add(400, remove_flash)
                
                GLib.idle_add(update_gesture_indicator, action, self.action_executed and action != "neutral")
                
                # Atualiza FPS e métricas
                stats = self.analytics.get_stats_summary()
                fps_value = stats['performance']['fps']
                total_gestures = stats['usage']['total_gestures']
                total_frames = stats['performance']['total_frames']
                
                GLib.idle_add(self.fps_label.set_text, f"{fps_value:.1f}")
                # Removido: atualização de labels de métricas
                
                # Converte frame para exibição na GUI
                height, width, channels = frame.shape
                pixbuf = GdkPixbuf.Pixbuf.new_from_data(
                    frame.tobytes(),
                    GdkPixbuf.Colorspace.RGB,
                    False,
                    8,
                    width,
                    height,
                    width * channels
                )
                
                # Redimensiona mantendo proporção
                original_width = pixbuf.get_width()
                original_height = pixbuf.get_height()
                
                # Calcula nova dimensão responsiva
                available_height = self.get_allocated_height() - 120
                available_width = self.get_allocated_width() - 320
                
                # Calcula escala baseada no espaço disponível
                scale_height = available_height / original_height
                scale_width = available_width / original_width
                scale_factor = min(scale_height, scale_width, 1)
                
                new_width = int(original_width * scale_factor)
                new_height = int(original_height * scale_factor)
                    
                pixbuf = pixbuf.scale_simple(new_width, new_height, GdkPixbuf.InterpType.BILINEAR)
                GLib.idle_add(self.video_image.set_from_pixbuf, pixbuf)
                
                time.sleep(0.01)  # ~100 FPS captura, processamento assíncrono
        finally:
            # Para thread de processamento
            self._processing_active = False
            processor_thread.join(timeout=1.0)
            
    def on_window_destroy(self, window):
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
        
        hands.close()
        Gtk.main_quit()

# ===== Execução Principal =====
def main():
    app = WaveControlGUI()
    app.show_all()
    Gtk.main()

if __name__ == "__main__":
    main()
