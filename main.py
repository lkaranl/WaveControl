#!/usr/bin/env python3
import cv2
import time
import uinput
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

# ===== Configurações de Zoom =====
DEFAULT_ZOOM = 1.0      # zoom padrão (sem zoom)
MIN_ZOOM = 1.0          # zoom mínimo
MAX_ZOOM = 4.0          # zoom máximo

# ===== Filtro Temporal =====
GESTURE_WINDOW_SIZE = 8  # número de frames para confirmar gesto
CONSISTENCY_THRESHOLD = 0.75  # 75% das amostras devem ser iguais

# ===== Dispositivo virtual (uinput) =====
kb = uinput.Device([uinput.KEY_RIGHT, uinput.KEY_LEFT, uinput.KEY_HOME, uinput.KEY_END])

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

# Cache para thresholds
_THUMB_THRESHOLD = 0.05
_FINGER_THRESHOLD = 0.05

def finger_extended(lm, tip_idx, pip_idx, handed_label):
    tip = lm[tip_idx]
    pip = lm[pip_idx]
    if tip_idx == TIP["thumb"]:
        # polegar: eixo X depende da mão (mais rigoroso)
        if handed_label == "Right":
            return tip.x < pip.x - _THUMB_THRESHOLD
        else:
            return tip.x > pip.x + _THUMB_THRESHOLD
    # demais dedos: eixo Y (origem no topo) - mais rigoroso
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
    """Adiciona gesto ao histórico e mantém tamanho da janela"""
    gesture_history.append(gesture)
    if len(gesture_history) > GESTURE_WINDOW_SIZE:
        gesture_history.pop(0)

def get_stable_gesture():
    """Retorna gesto estável baseado no histórico - otimizado com Counter"""
    if len(gesture_history) < GESTURE_WINDOW_SIZE:
        return "neutral"  # aguarda janela completa
    
    # Usa Counter para contar eficientemente
    gesture_counts = Counter(gesture_history)
    
    # Encontra o gesto mais frequente
    most_common_gesture, most_common_count = gesture_counts.most_common(1)[0]
    
    # Verifica se atende o threshold de consistência
    consistency_ratio = most_common_count / GESTURE_WINDOW_SIZE
    
    if consistency_ratio >= CONSISTENCY_THRESHOLD and most_common_gesture != "neutral":
        return most_common_gesture
    
    return "neutral"

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
    kb.emit_click(uinput.KEY_RIGHT)

def press_prev():
    kb.emit_click(uinput.KEY_LEFT)

def press_home():
    kb.emit_click(uinput.KEY_HOME)

def press_end():
    kb.emit_click(uinput.KEY_END)

def apply_digital_zoom(frame, zoom_level):
    """Aplica zoom digital no frame"""
    if zoom_level <= 1.0:
        return frame
    
    height, width = frame.shape[:2]
    
    # Calcula o tamanho da região central a ser extraída
    crop_width = int(width / zoom_level)
    crop_height = int(height / zoom_level)
    
    # Calcula as coordenadas centrais para o crop
    start_x = (width - crop_width) // 2
    start_y = (height - crop_height) // 2
    end_x = start_x + crop_width
    end_y = start_y + crop_height
    
    # Extrai a região central
    cropped = frame[start_y:end_y, start_x:end_x]
    
    # Redimensiona de volta ao tamanho original
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
            margin-right: 24px;
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
            border-radius: 12px;
            background: @theme_base_color;
            box-shadow: 0 2px 8px alpha(black, 0.1);
        }
        
        .video-container {
            background: black;
            border-radius: 12px;
            min-height: 400px;
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
        
        /* Controles de zoom harmonioso */
        .zoom-inline {
            background: alpha(@theme_bg_color, 0.3);
            border-radius: 8px;
            padding: 12px;
            border: 1px solid alpha(@borders, 0.15);
        }
        
        .zoom-value {
            font-size: 14px;
            font-weight: 600;
            margin-bottom: 8px;
            color: @theme_selected_bg_color;
        }
        
        .zoom-buttons-row {
            margin-top: 8px;
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
            padding: 4px 0;
            color: alpha(@theme_fg_color, 0.9);
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
        
        # Seção esquerda do header - título e informações
        header_left = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        
        # Título da aplicação
        title_label = Gtk.Label(label="WaveControl")
        title_label.get_style_context().add_class("app-title")
        title_label.set_halign(Gtk.Align.START)
        
        # Status principal no header (versão compacta)
        self.header_status = Gtk.Label(label="Parado")
        self.header_status.get_style_context().add_class("status-indicator")
        self.header_status.set_size_request(117, -1)  # Largura mínima para "Ativo"
        
        header_left.pack_start(title_label, False, False, 0)
        header_left.pack_start(self.header_status, False, False, 0)
        
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
        
        gestures = [
            "👆 1 → Próximo",
            "✌️ 2 → Anterior",
            "🤟 3 → Início", 
            "🖖 4 → Fim",
            "✊ 0 → Neutro"
        ]
        
        for gesture in gestures:
            gesture_item = Gtk.Label(label=gesture)
            gesture_item.get_style_context().add_class("gesture-compact")
            gesture_item.set_halign(Gtk.Align.START)
            gestures_compact.pack_start(gesture_item, False, False, 0)
        
        gestures_card.pack_start(gestures_title, False, False, 0)
        gestures_card.pack_start(gestures_compact, False, False, 0)
        sidebar.pack_start(gestures_card, False, False, 0)
        
        # Card de Zoom Compacto
        zoom_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        zoom_card.get_style_context().add_class("compact-card")
        
        zoom_title = Gtk.Label(label="Zoom Digital")
        zoom_title.get_style_context().add_class("card-title")
        zoom_title.set_halign(Gtk.Align.START)
        
        # Controles de zoom inline
        zoom_inline = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        zoom_inline.get_style_context().add_class("zoom-inline")
        
        # Label do zoom atual
        self.zoom_value_label = Gtk.Label(label=f"{DEFAULT_ZOOM:.1f}x")
        self.zoom_value_label.get_style_context().add_class("zoom-value")
        
        # Slider compacto
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
        self.zoom_scale.set_size_request(200, -1)
        self.zoom_scale.connect("value-changed", self.on_zoom_changed)
        
        # Botões de zoom em linha
        zoom_buttons_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        zoom_buttons_row.get_style_context().add_class("zoom-buttons-row")
        zoom_buttons_row.set_homogeneous(True)
        
        self.zoom_1x_btn = Gtk.Button.new_with_label("1x")
        self.zoom_1x_btn.get_style_context().add_class("secondary-button")
        self.zoom_1x_btn.connect("clicked", lambda btn: self.set_zoom(1.0))
        self.zoom_1x_btn.set_tooltip_text("Sem zoom (padrão)")
        
        self.zoom_2x_btn = Gtk.Button.new_with_label("2x")
        self.zoom_2x_btn.get_style_context().add_class("secondary-button")
        self.zoom_2x_btn.connect("clicked", lambda btn: self.set_zoom(2.0))
        self.zoom_2x_btn.set_tooltip_text("Zoom 2x - aproxima a imagem")
        
        self.zoom_3x_btn = Gtk.Button.new_with_label("3x")
        self.zoom_3x_btn.get_style_context().add_class("secondary-button")
        self.zoom_3x_btn.connect("clicked", lambda btn: self.set_zoom(3.0))
        self.zoom_3x_btn.set_tooltip_text("Zoom 3x - aproxima mais")
        
        self.zoom_4x_btn = Gtk.Button.new_with_label("4x")
        self.zoom_4x_btn.get_style_context().add_class("secondary-button")
        self.zoom_4x_btn.connect("clicked", lambda btn: self.set_zoom(4.0))
        self.zoom_4x_btn.set_tooltip_text("Zoom 4x - máximo aproximação")
        
        zoom_buttons_row.pack_start(self.zoom_1x_btn, True, True, 0)
        zoom_buttons_row.pack_start(self.zoom_2x_btn, True, True, 0)
        zoom_buttons_row.pack_start(self.zoom_3x_btn, True, True, 0)
        zoom_buttons_row.pack_start(self.zoom_4x_btn, True, True, 0)
        
        zoom_inline.pack_start(self.zoom_value_label, False, False, 0)
        zoom_inline.pack_start(self.zoom_scale, False, False, 0)
        zoom_inline.pack_start(zoom_buttons_row, False, False, 0)
        
        zoom_card.pack_start(zoom_title, False, False, 0)
        zoom_card.pack_start(zoom_inline, False, False, 0)
        sidebar.pack_start(zoom_card, False, False, 0)
        
        # Card de Status Compacto
        status_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        status_card.get_style_context().add_class("compact-card")
        
        status_title = Gtk.Label(label="Status do Sistema")
        status_title.get_style_context().add_class("card-title")
        status_title.set_halign(Gtk.Align.START)
        
        # Grid de status
        status_grid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        status_grid.get_style_context().add_class("status-grid")
        
        # Status principal
        self.status_label = Gtk.Label(label="Sistema parado")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.get_style_context().add_class("status-label")
        
        # Status da ação atual
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
        
        # Filtro temporal
        filter_item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        filter_item.get_style_context().add_class("status-item")
        
        filter_label = Gtk.Label(label="Filtro:")
        filter_label.get_style_context().add_class("status-label")
        
        self.filter_label = Gtk.Label(label="0/8")
        self.filter_label.get_style_context().add_class("status-indicator")
        self.filter_label.set_tooltip_text("Filtro temporal de gestos (frames consistentes/total)")
        
        filter_item.pack_start(filter_label, False, False, 0)
        filter_item.pack_end(self.filter_label, False, False, 0)
        
        # FPS
        fps_item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        fps_item.get_style_context().add_class("status-item")
        
        fps_label = Gtk.Label(label="FPS:")
        fps_label.get_style_context().add_class("status-label")
        
        self.fps_label = Gtk.Label(label="0.0")
        self.fps_label.get_style_context().add_class("status-indicator")
        self.fps_label.set_tooltip_text("Taxa de quadros por segundo (FPS) - performance do sistema")
        
        fps_item.pack_start(fps_label, False, False, 0)
        fps_item.pack_end(self.fps_label, False, False, 0)
        
        status_grid.pack_start(self.status_label, False, False, 0)
        status_grid.pack_start(action_item, False, False, 0)
        status_grid.pack_start(filter_item, False, False, 0)
        status_grid.pack_start(fps_item, False, False, 0)
        
        status_card.pack_start(status_title, False, False, 0)
        status_card.pack_start(status_grid, False, False, 0)
        sidebar.pack_start(status_card, False, False, 0)
        
        # Card de Configurações (ÚLTIMO)
        config_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        config_card.get_style_context().add_class("compact-card")
        
        config_title = Gtk.Label(label="Configurações")
        config_title.get_style_context().add_class("card-title")
        config_title.set_halign(Gtk.Align.START)
        
        # Checkbox compacto
        self.show_landmarks_check = Gtk.CheckButton.new_with_label("Mostrar landmarks")
        self.show_landmarks_check.set_active(DRAW)
        self.show_landmarks_check.set_tooltip_text("Mostra pontos de rastreamento da mão no vídeo")
        
        config_card.pack_start(config_title, False, False, 0)
        config_card.pack_start(self.show_landmarks_check, False, False, 0)
        sidebar.pack_start(config_card, False, False, 0)
        
        # Card de Métricas (Analytics)
        metrics_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        metrics_card.get_style_context().add_class("compact-card")
        
        metrics_title = Gtk.Label(label="Métricas")
        metrics_title.get_style_context().add_class("card-title")
        metrics_title.set_halign(Gtk.Align.START)
        
        # Grid de métricas
        metrics_grid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        metrics_grid.get_style_context().add_class("status-grid")
        
        # Total de gestos
        gestures_item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        gestures_item.get_style_context().add_class("status-item")
        
        gestures_label = Gtk.Label(label="Gestos:")
        gestures_label.get_style_context().add_class("status-label")
        
        self.total_gestures_label = Gtk.Label(label="0")
        self.total_gestures_label.get_style_context().add_class("status-indicator")
        self.total_gestures_label.set_tooltip_text("Total de gestos executados nesta sessão")
        
        gestures_item.pack_start(gestures_label, False, False, 0)
        gestures_item.pack_end(self.total_gestures_label, False, False, 0)
        
        # Frames processados
        frames_item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        frames_item.get_style_context().add_class("status-item")
        
        frames_label = Gtk.Label(label="Frames:")
        frames_label.get_style_context().add_class("status-label")
        
        self.total_frames_label = Gtk.Label(label="0")
        self.total_frames_label.get_style_context().add_class("status-indicator")
        self.total_frames_label.set_tooltip_text("Total de frames processados pelo sistema")
        
        frames_item.pack_start(frames_label, False, False, 0)
        frames_item.pack_end(self.total_frames_label, False, False, 0)
        
        metrics_grid.pack_start(gestures_item, False, False, 0)
        metrics_grid.pack_start(frames_item, False, False, 0)
        
        metrics_card.pack_start(metrics_title, False, False, 0)
        metrics_card.pack_start(metrics_grid, False, False, 0)
        sidebar.pack_start(metrics_card, False, False, 0)
        
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
        video_wrapper.set_margin_left(8)
        video_wrapper.set_margin_right(8)
        
        # Container do vídeo responsivo
        video_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        video_container.get_style_context().add_class("video-container")
        
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
        
        video_wrapper.pack_start(video_container, True, True, 0)
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
        
        footer.pack_start(footer_info, True, True, 0)
        main_container.pack_end(footer, False, False, 0)
        
    def on_zoom_changed(self, scale):
        self.zoom_level = scale.get_value()
        self.zoom_value_label.set_text(f"{self.zoom_level:.1f}x")
    
    def set_zoom(self, zoom_value):
        self.zoom_level = zoom_value
        self.zoom_scale.set_value(zoom_value)
        self.zoom_value_label.set_text(f"{zoom_value:.1f}x")
    
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
        self.header_status.set_text("Calibrando...")
        self.status_label.set_text("Sistema calibrando...")
        
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
        self.header_status.set_text("Parado")
        self.status_label.set_text("Sistema parado")
        
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
        self.filter_label.set_text("0/8")
        self.fps_label.set_text("0.0")
        
        # Reset métricas
        stats = self.analytics.get_stats_summary()
        self.total_gestures_label.set_text(str(stats['usage']['total_gestures']))
        self.total_frames_label.set_text(str(stats['performance']['total_frames']))
        
    def _process_frame_async(self, frame_data):
        """Processa frame em thread separada"""
        start_time = time.perf_counter()
        
        frame, zoom_level, show_landmarks = frame_data
        
        # Frame pooling: reutiliza buffers pré-alocados
        frame = cv2.flip(frame, 1)
        
        # Aplica zoom digital se necessário
        frame = apply_digital_zoom(frame, zoom_level)
        
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
        
        try:
            while self.is_running and self.cap and self.cap.isOpened():
                ok, frame = self.cap.read()
                if not ok:
                    break
                
                # Envia frame para processamento assíncrono
                try:
                    frame_data = (frame.copy(), self.zoom_level, self.show_landmarks_check.get_active())
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
                
                frame = processed_frame
            
                now = time.time()
            
                # Informações visuais na tela
                if self.zoom_level > 1.0:
                    zoom_text = f"Zoom: {self.zoom_level:.1f}x"
                    cv2.putText(frame, zoom_text, (20, frame.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)
                
                # Calibração inicial
                if now - self.start_ts < CALIBRATION_S:
                    cv2.putText(frame, "Calibrando...", (20,40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
                    GLib.idle_add(self.header_status.set_text, "Calibrando...")
                    GLib.idle_add(self.status_label.set_text, "Sistema calibrando...")
                else:
                    # Lógica de execução de ações
                    if action == "neutral":
                        if self.action_executed:
                            self.action_executed = False
                            GLib.idle_add(self.header_status.set_text, "Ativo")
                            GLib.idle_add(self.status_label.set_text, "Sistema ativo - Pronto")
                    elif action != "neutral" and not self.action_executed:
                        if action == "next":
                            press_next()
                            self.analytics.record_gesture("next")
                            GLib.idle_add(self.header_status.set_text, "Próximo →")
                            GLib.idle_add(self.status_label.set_text, "Próximo slide executado")
                        elif action == "prev":
                            press_prev()
                            self.analytics.record_gesture("prev")
                            GLib.idle_add(self.header_status.set_text, "← Anterior")
                            GLib.idle_add(self.status_label.set_text, "Slide anterior executado")
                        elif action == "home":
                            press_home()
                            self.analytics.record_gesture("home")
                            GLib.idle_add(self.header_status.set_text, "⏮ Início")
                            GLib.idle_add(self.status_label.set_text, "Indo para o início")
                        elif action == "end":
                            press_end()
                            self.analytics.record_gesture("end")
                            GLib.idle_add(self.header_status.set_text, "⏭ Fim")
                            GLib.idle_add(self.status_label.set_text, "Indo para o fim")
                        self.action_executed = True
                        self.last_action = action
                    elif action != "neutral" and self.action_executed:
                        GLib.idle_add(self.header_status.set_text, "Aguardando...")
                        GLib.idle_add(self.status_label.set_text, "Aguardando posição neutra")
                
                # Atualiza indicadores de status com feedback visual
                def update_gesture_indicator(gesture):
                    # Remove classes antigas
                    ctx = self.action_indicator.get_style_context()
                    for cls in ["gesture-next", "gesture-prev", "gesture-home", "gesture-end", "gesture-neutral"]:
                        ctx.remove_class(cls)
                    
                    # Adiciona classe específica do gesto
                    ctx.add_class(f"gesture-{gesture}")
                    self.action_indicator.set_text(gesture)
                
                GLib.idle_add(update_gesture_indicator, action)
                GLib.idle_add(self.filter_label.set_text, f"{len(gesture_history)}/{GESTURE_WINDOW_SIZE}")
                
                # Atualiza FPS e métricas
                stats = self.analytics.get_stats_summary()
                fps_value = stats['performance']['fps']
                total_gestures = stats['usage']['total_gestures']
                total_frames = stats['performance']['total_frames']
                
                GLib.idle_add(self.fps_label.set_text, f"{fps_value:.1f}")
                GLib.idle_add(self.total_gestures_label.set_text, str(total_gestures))
                GLib.idle_add(self.total_frames_label.set_text, str(total_frames))
                
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
