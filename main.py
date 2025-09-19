#!/usr/bin/env python3
import cv2
import time
import uinput
import mediapipe as mp
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, GdkPixbuf, Gdk
import threading

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
        # polegar: eixo X depende da mão (mais rigoroso)
        if handed_label == "Right":
            return tip.x < pip.x - 0.05
        else:
            return tip.x > pip.x + 0.05
    # demais dedos: eixo Y (origem no topo) - mais rigoroso
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
    """Adiciona gesto ao histórico e mantém tamanho da janela"""
    gesture_history.append(gesture)
    if len(gesture_history) > GESTURE_WINDOW_SIZE:
        gesture_history.pop(0)

def get_stable_gesture():
    """Retorna gesto estável baseado no histórico ou 'neutral' se inconsistente"""
    if len(gesture_history) < GESTURE_WINDOW_SIZE:
        return "neutral"  # aguarda janela completa
    
    # Conta ocorrências de cada gesto
    gesture_counts = {}
    for gesture in gesture_history:
        gesture_counts[gesture] = gesture_counts.get(gesture, 0) + 1
    
    # Encontra o gesto mais frequente
    most_common_gesture = max(gesture_counts, key=gesture_counts.get)
    most_common_count = gesture_counts[most_common_gesture]
    
    # Verifica se atende o threshold de consistência
    consistency_ratio = most_common_count / len(gesture_history)
    
    if consistency_ratio >= CONSISTENCY_THRESHOLD and most_common_gesture != "neutral":
        return most_common_gesture
    
    return "neutral"

# ===== Gesto -> Ação =====
# 1 dedo: próximo; 2 dedos: anterior; 3 dedos: início; 4 dedos: fim; senão: neutro
def classify_gesture(lm, handed_label):
    n = count_extended(lm, handed_label)
    if n == 1: return "next"      # um dedo levantado
    if n == 2: return "prev"      # dois dedos levantados
    if n == 3: return "home"      # três dedos levantados
    if n == 4: return "end"       # quatro dedos levantados
    return "neutral"

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
        self.set_default_size(1200, 700)
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
        
        # Setup da interface
        self.setup_ui()
        
        # Conecta eventos
        self.connect("destroy", self.on_window_destroy)
        
        # Inicia automaticamente
        GLib.idle_add(self.start_detection)
    
    def apply_modern_styling(self):
        """Aplica estilo minimalista respeitando o tema GTK"""
        css_provider = Gtk.CssProvider()
        css = """
        /* Estilos básicos compatíveis com GTK CSS */
        .header-toolbar {
            padding: 12px 20px;
            background: @theme_bg_color;
            border-bottom: 1px solid @borders;
            min-height: 50px;
        }
        
        .app-title {
            font-size: 18px;
            font-weight: bold;
            color: @theme_fg_color;
        }
        
        .sidebar {
            padding: 16px;
            background: @theme_bg_color;
            border-right: 1px solid @borders;
        }
        
        .main-content {
            padding: 16px;
            background: @theme_base_color;
        }
        
        .video-area {
            border-radius: 8px;
            border: 1px solid @borders;
            background: @theme_base_color;
        }
        
        .video-container {
            background: black;
        }
        
        .compact-card {
            background: @theme_base_color;
            border: 1px solid @borders;
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 12px;
        }
        
        .card-title {
            font-size: 14px;
            font-weight: bold;
            margin-bottom: 8px;
            color: @theme_fg_color;
        }
        
        .primary-button {
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
            min-height: 36px;
        }
        
        .secondary-button {
            padding: 6px 12px;
            border-radius: 4px;
            font-size: 12px;
            margin: 2px;
        }
        
        .status-indicator {
            padding: 4px 8px;
            border-radius: 10px;
            font-size: 11px;
            font-weight: bold;
            background: @theme_selected_bg_color;
            color: @theme_selected_fg_color;
        }
        
        .status-grid {
            background: @theme_bg_color;
            border-radius: 4px;
            padding: 8px;
            border: 1px solid @borders;
        }
        
        .zoom-inline {
            background: @theme_bg_color;
            border-radius: 4px;
            padding: 8px;
            border: 1px solid @borders;
        }
        
        .zoom-value {
            font-size: 11px;
            font-weight: bold;
            margin-bottom: 4px;
        }
        
        .gestures-compact {
            background: @theme_bg_color;
            border-radius: 4px;
            padding: 8px;
            border: 1px solid @borders;
        }
        
        .gesture-compact {
            font-size: 11px;
            padding: 2px 0;
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
        
        # Header toolbar compacto
        header_toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header_toolbar.get_style_context().add_class("header-toolbar")
        
        # Título da aplicação
        title_label = Gtk.Label(label="WaveControl")
        title_label.get_style_context().add_class("app-title")
        title_label.set_halign(Gtk.Align.START)
        
        # Controles do toolbar
        toolbar_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar_controls.get_style_context().add_class("toolbar-controls")
        
        # Botão principal no header
        self.header_start_button = Gtk.Button.new_with_label("▶ Iniciar")
        self.header_start_button.get_style_context().add_class("primary-button")
        self.header_start_button.connect("clicked", self.on_start_clicked)
        
        # Status principal no header
        self.header_status = Gtk.Label(label="Parado")
        self.header_status.get_style_context().add_class("status-indicator")
        
        toolbar_controls.pack_start(self.header_status, False, False, 0)
        toolbar_controls.pack_start(self.header_start_button, False, False, 0)
        
        header_toolbar.pack_start(title_label, False, False, 0)
        header_toolbar.pack_end(toolbar_controls, False, False, 0)
        main_container.pack_start(header_toolbar, False, False, 0)
        
        # Layout principal maximizado
        main_layout = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        main_layout.get_style_context().add_class("main-layout")
        main_container.pack_start(main_layout, True, True, 0)
        
        # === SIDEBAR COMPACTA ===
        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_min_content_width(280)
        sidebar_scroll.set_max_content_width(320)
        
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sidebar.get_style_context().add_class("sidebar")
        sidebar_scroll.add(sidebar)
        main_layout.pack_start(sidebar_scroll, False, False, 0)
        
        # Card de Configurações
        config_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        config_card.get_style_context().add_class("compact-card")
        
        config_title = Gtk.Label(label="Configurações")
        config_title.get_style_context().add_class("card-title")
        config_title.set_halign(Gtk.Align.START)
        
        # Checkbox compacto
        self.show_landmarks_check = Gtk.CheckButton.new_with_label("Mostrar landmarks")
        self.show_landmarks_check.set_active(DRAW)
        
        config_card.pack_start(config_title, False, False, 0)
        config_card.pack_start(self.show_landmarks_check, False, False, 0)
        sidebar.pack_start(config_card, False, False, 0)
        
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
        
        self.zoom_2x_btn = Gtk.Button.new_with_label("2x")
        self.zoom_2x_btn.get_style_context().add_class("secondary-button")
        self.zoom_2x_btn.connect("clicked", lambda btn: self.set_zoom(2.0))
        
        self.zoom_3x_btn = Gtk.Button.new_with_label("3x")
        self.zoom_3x_btn.get_style_context().add_class("secondary-button")
        self.zoom_3x_btn.connect("clicked", lambda btn: self.set_zoom(3.0))
        
        self.zoom_4x_btn = Gtk.Button.new_with_label("4x")
        self.zoom_4x_btn.get_style_context().add_class("secondary-button")
        self.zoom_4x_btn.connect("clicked", lambda btn: self.set_zoom(4.0))
        
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
        
        action_item.pack_start(action_label, False, False, 0)
        action_item.pack_end(self.action_indicator, False, False, 0)
        
        # Filtro temporal
        filter_item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        filter_item.get_style_context().add_class("status-item")
        
        filter_label = Gtk.Label(label="Filtro:")
        filter_label.get_style_context().add_class("status-label")
        
        self.filter_label = Gtk.Label(label="0/8")
        self.filter_label.get_style_context().add_class("status-indicator")
        
        filter_item.pack_start(filter_label, False, False, 0)
        filter_item.pack_end(self.filter_label, False, False, 0)
        
        status_grid.pack_start(self.status_label, False, False, 0)
        status_grid.pack_start(action_item, False, False, 0)
        status_grid.pack_start(filter_item, False, False, 0)
        
        status_card.pack_start(status_title, False, False, 0)
        status_card.pack_start(status_grid, False, False, 0)
        sidebar.pack_start(status_card, False, False, 0)
        
        # Card de Gestos Compacto
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
        sidebar.pack_start(gestures_card, True, True, 0)
        
        # === ÁREA PRINCIPAL MAXIMIZADA ===
        main_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main_content.get_style_context().add_class("main-content")
        main_layout.pack_start(main_content, True, True, 0)
        
        # Área de vídeo maximizada
        video_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        video_area.get_style_context().add_class("video-area")
        
        # Container do vídeo responsivo
        video_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        video_container.get_style_context().add_class("video-container")
        
        self.video_image = Gtk.Image()
        self.video_image.set_halign(Gtk.Align.CENTER)
        self.video_image.set_valign(Gtk.Align.CENTER)
        
        # Placeholder moderno
        self.placeholder_label = Gtk.Label(label="📷 Câmera não ativada\n\nClique em '▶ Iniciar' para começar")
        self.placeholder_label.get_style_context().add_class("video-placeholder")
        self.placeholder_label.set_halign(Gtk.Align.CENTER)
        self.placeholder_label.set_valign(Gtk.Align.CENTER)
        
        video_container.pack_start(self.video_image, True, True, 0)
        video_container.pack_start(self.placeholder_label, True, True, 0)
        
        video_area.pack_start(video_container, True, True, 0)
        main_content.pack_start(video_area, True, True, 0)
        
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
        self.header_start_button.set_label("⏹ Parar")
        self.header_status.set_text("Calibrando...")
        self.status_label.set_text("Sistema calibrando...")
        
        # Esconde placeholder e mostra vídeo
        self.placeholder_label.hide()
        self.video_image.show()
        
        # Inicia thread de processamento
        self.processing_thread = threading.Thread(target=self.process_video)
        self.processing_thread.daemon = True
        self.processing_thread.start()
        
    def stop_detection(self):
        self.is_running = False
        if self.cap:
            self.cap.release()
        self.header_start_button.set_label("▶ Iniciar")
        self.header_status.set_text("Parado")
        self.status_label.set_text("Sistema parado")
        
        # Mostra placeholder e esconde vídeo
        self.video_image.clear()
        self.video_image.hide()
        self.placeholder_label.show()
        
        # Reset dos indicadores
        self.action_indicator.set_text("neutral")
        self.filter_label.set_text("0/8")
        
    def process_video(self):
        while self.is_running and self.cap and self.cap.isOpened():
            ok, frame = self.cap.read()
            if not ok:
                break
                
            frame = cv2.flip(frame, 1)
            
            # Aplica zoom digital se necessário
            frame = apply_digital_zoom(frame, self.zoom_level)
            
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = hands.process(rgb)
            
            raw_action = "neutral"
            handed = "Right"
            
            if res.multi_hand_landmarks:
                lm = res.multi_hand_landmarks[0]
                if res.multi_handedness and len(res.multi_handedness) > 0:
                    handed = res.multi_handedness[0].classification[0].label
                raw_action = classify_gesture(lm.landmark, handed)
            
            # Adiciona gesto ao histórico e obtém gesto estável
            add_gesture_to_history(raw_action)
            action = get_stable_gesture()
            
            # Desenha landmarks se habilitado
            if res.multi_hand_landmarks and self.show_landmarks_check.get_active():
                lm = res.multi_hand_landmarks[0]
                mp_drawing.draw_landmarks(
                    frame, lm, mp_hands.HAND_CONNECTIONS,
                    mp_drawing.DrawingSpec(color=(0,255,0), thickness=2, circle_radius=2),
                    mp_drawing.DrawingSpec(color=(255,0,0), thickness=2)
                )
            
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
                        GLib.idle_add(self.header_status.set_text, "Próximo →")
                        GLib.idle_add(self.status_label.set_text, "Próximo slide executado")
                    elif action == "prev":
                        press_prev()
                        GLib.idle_add(self.header_status.set_text, "← Anterior")
                        GLib.idle_add(self.status_label.set_text, "Slide anterior executado")
                    elif action == "home":
                        press_home()
                        GLib.idle_add(self.header_status.set_text, "⏮ Início")
                        GLib.idle_add(self.status_label.set_text, "Indo para o início")
                    elif action == "end":
                        press_end()
                        GLib.idle_add(self.header_status.set_text, "⏭ Fim")
                        GLib.idle_add(self.status_label.set_text, "Indo para o fim")
                    self.action_executed = True
                    self.last_action = action
                elif action != "neutral" and self.action_executed:
                    GLib.idle_add(self.header_status.set_text, "Aguardando...")
                    GLib.idle_add(self.status_label.set_text, "Aguardando posição neutra")
            
            # Atualiza indicadores de status
            GLib.idle_add(self.action_indicator.set_text, action)
            GLib.idle_add(self.filter_label.set_text, f"{len(gesture_history)}/{GESTURE_WINDOW_SIZE}")
            
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
            
            # Calcula nova dimensão responsiva - usa mais espaço disponível
            max_height = min(600, self.get_allocated_height() - 120)  # Altura dinamica menos header
            max_width = min(800, self.get_allocated_width() - 350)    # Largura dinamica menos sidebar
            
            # Calcula escala baseada nos limites disponiveis
            scale_height = max_height / original_height if original_height > max_height else 1
            scale_width = max_width / original_width if original_width > max_width else 1
            scale_factor = min(scale_height, scale_width, 1)
            
            new_width = int(original_width * scale_factor)
            new_height = int(original_height * scale_factor)
                
            pixbuf = pixbuf.scale_simple(new_width, new_height, GdkPixbuf.InterpType.BILINEAR)
            GLib.idle_add(self.video_image.set_from_pixbuf, pixbuf)
            
            time.sleep(0.03)  # ~30 FPS
            
    def on_window_destroy(self, window):
        self.stop_detection()
        hands.close()
        Gtk.main_quit()

# ===== Execução Principal =====
def main():
    app = WaveControlGUI()
    app.show_all()
    Gtk.main()

if __name__ == "__main__":
    main()
