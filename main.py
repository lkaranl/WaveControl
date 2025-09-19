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
        self.set_default_size(1000, 600)
        self.set_position(Gtk.WindowPosition.CENTER)
        
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
    
    def apply_modern_styling(self):
        """Aplica estilo minimalista respeitando o tema GTK"""
        css_provider = Gtk.CssProvider()
        css = """
        /* Layout moderno com sidebar */
        .main-container {
            margin: 0;
        }
        
        .header-bar {
            padding: 20px 24px;
            background: alpha(@theme_selected_bg_color, 0.1);
            border-bottom: 1px solid alpha(@borders, 0.2);
        }
        
        .app-title {
            font-size: 22px;
            font-weight: 600;
            margin-bottom: 4px;
        }
        
        .app-subtitle {
            font-size: 14px;
            opacity: 0.7;
        }
        
        .content-layout {
            background: @theme_base_color;
        }
        
        .sidebar {
            min-width: 300px;
            padding: 24px 20px;
            background: alpha(@theme_base_color, 0.5);
            border-right: 1px solid alpha(@borders, 0.2);
        }
        
        .main-content {
            padding: 24px;
            background: @theme_base_color;
        }
        
        .video-preview {
            border-radius: 12px;
            border: 1px solid alpha(@borders, 0.3);
            background: alpha(@borders, 0.05);
        }
        
        .video-container {
            min-height: 280px;
            background: alpha(@theme_base_color, 0.8);
        }
        
        .video-placeholder {
            color: alpha(@theme_fg_color, 0.5);
            font-size: 16px;
        }
        
        .control-card {
            background: @theme_base_color;
            border: 1px solid alpha(@borders, 0.2);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px alpha(@borders, 0.1);
        }
        
        .card-header {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 16px;
            color: @theme_fg_color;
        }
        
        .primary-button {
            padding: 12px 20px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 14px;
            min-height: 44px;
        }
        
        .status-badge {
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
            background: alpha(@theme_selected_bg_color, 0.15);
            color: @theme_selected_bg_color;
            border: 1px solid alpha(@theme_selected_bg_color, 0.3);
        }
        
        .gesture-grid {
            background: alpha(@theme_selected_bg_color, 0.05);
            border-radius: 8px;
            padding: 16px;
            border: 1px solid alpha(@theme_selected_bg_color, 0.2);
        }
        
        .gesture-item {
            padding: 8px 0;
            border-bottom: 1px solid alpha(@borders, 0.1);
            font-size: 13px;
        }
        
        .gesture-item:last-child {
            border-bottom: none;
        }
        
        .status-row {
            padding: 8px 0;
        }
        
        .status-label {
            font-size: 13px;
            opacity: 0.8;
        }
        
        .tip-box {
            background: alpha(@theme_selected_bg_color, 0.08);
            border-radius: 6px;
            padding: 12px;
            margin-top: 16px;
            border-left: 3px solid alpha(@theme_selected_bg_color, 0.4);
        }
        
        .tip-text {
            font-size: 12px;
            opacity: 0.8;
        }
        
        .zoom-controls {
            background: alpha(@theme_selected_bg_color, 0.05);
            border-radius: 8px;
            padding: 12px;
            border: 1px solid alpha(@theme_selected_bg_color, 0.2);
        }
        
        .zoom-label {
            font-size: 12px;
            font-weight: 500;
            margin-bottom: 8px;
        }
        
        .zoom-buttons {
            margin-top: 8px;
        }
        
        .zoom-button {
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 12px;
            min-height: 32px;
            margin: 0 2px;
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
        
        # Header moderno
        header_bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        header_bar.get_style_context().add_class("header-bar")
        
        title_label = Gtk.Label(label="WaveControl")
        title_label.get_style_context().add_class("app-title")
        title_label.set_halign(Gtk.Align.START)
        
        subtitle_label = Gtk.Label(label="Controle inteligente de apresentações")
        subtitle_label.get_style_context().add_class("app-subtitle")
        subtitle_label.set_halign(Gtk.Align.START)
        
        header_bar.pack_start(title_label, False, False, 0)
        header_bar.pack_start(subtitle_label, False, False, 0)
        main_container.pack_start(header_bar, False, False, 0)
        
        # Layout principal com sidebar
        content_layout = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        content_layout.get_style_context().add_class("content-layout")
        main_container.pack_start(content_layout, True, True, 0)
        
        # === SIDEBAR ===
        # Scrolled window para a sidebar
        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_min_content_width(300)
        
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sidebar.get_style_context().add_class("sidebar")
        sidebar_scroll.add(sidebar)
        content_layout.pack_start(sidebar_scroll, False, False, 0)
        
        # Card de Controles
        controls_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        controls_card.get_style_context().add_class("control-card")
        
        controls_header = Gtk.Label(label="Controles")
        controls_header.get_style_context().add_class("card-header")
        controls_header.set_halign(Gtk.Align.START)
        
        # Botão principal moderno
        self.start_button = Gtk.Button.new_with_label("Iniciar Detecção")
        self.start_button.get_style_context().add_class("primary-button")
        self.start_button.connect("clicked", self.on_start_clicked)
        
        # Checkbox modernizado
        self.show_landmarks_check = Gtk.CheckButton.new_with_label("Exibir landmarks da mão")
        self.show_landmarks_check.set_active(DRAW)
        
        controls_card.pack_start(controls_header, False, False, 0)
        controls_card.pack_start(self.start_button, False, False, 0)
        controls_card.pack_start(self.show_landmarks_check, False, False, 0)
        sidebar.pack_start(controls_card, False, False, 0)
        
        # Card de Zoom
        zoom_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        zoom_card.get_style_context().add_class("control-card")
        
        zoom_header = Gtk.Label(label="Controle de Zoom")
        zoom_header.get_style_context().add_class("card-header")
        zoom_header.set_halign(Gtk.Align.START)
        
        # Controles de zoom
        zoom_controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        zoom_controls.get_style_context().add_class("zoom-controls")
        
        # Label do zoom atual
        self.zoom_value_label = Gtk.Label(label=f"Zoom: {DEFAULT_ZOOM:.1f}x")
        self.zoom_value_label.get_style_context().add_class("zoom-label")
        self.zoom_value_label.set_halign(Gtk.Align.START)
        
        # Slider de zoom
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
        self.zoom_scale.connect("value-changed", self.on_zoom_changed)
        
        # Botões de zoom rápido
        zoom_buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        zoom_buttons.get_style_context().add_class("zoom-buttons")
        zoom_buttons.set_halign(Gtk.Align.CENTER)
        
        self.zoom_reset_btn = Gtk.Button.new_with_label("1.0x")
        self.zoom_reset_btn.get_style_context().add_class("zoom-button")
        self.zoom_reset_btn.connect("clicked", lambda btn: self.set_zoom(1.0))
        
        self.zoom_2x_btn = Gtk.Button.new_with_label("2.0x")
        self.zoom_2x_btn.get_style_context().add_class("zoom-button")
        self.zoom_2x_btn.connect("clicked", lambda btn: self.set_zoom(2.0))
        
        self.zoom_3x_btn = Gtk.Button.new_with_label("3.0x")
        self.zoom_3x_btn.get_style_context().add_class("zoom-button")
        self.zoom_3x_btn.connect("clicked", lambda btn: self.set_zoom(3.0))
        
        zoom_buttons.pack_start(self.zoom_reset_btn, True, True, 0)
        zoom_buttons.pack_start(self.zoom_2x_btn, True, True, 0)
        zoom_buttons.pack_start(self.zoom_3x_btn, True, True, 0)
        
        zoom_controls.pack_start(self.zoom_value_label, False, False, 0)
        zoom_controls.pack_start(self.zoom_scale, False, False, 0)
        zoom_controls.pack_start(zoom_buttons, False, False, 0)
        
        zoom_card.pack_start(zoom_header, False, False, 0)
        zoom_card.pack_start(zoom_controls, False, False, 0)
        sidebar.pack_start(zoom_card, False, False, 0)
        
        # Card de Status
        status_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        status_card.get_style_context().add_class("control-card")
        
        status_header = Gtk.Label(label="Status do Sistema")
        status_header.get_style_context().add_class("card-header")
        status_header.set_halign(Gtk.Align.START)
        
        # Status principal
        self.status_label = Gtk.Label(label="Sistema parado")
        self.status_label.set_halign(Gtk.Align.START)
        
        # Status da ação atual
        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        action_row.get_style_context().add_class("status-row")
        
        action_label = Gtk.Label(label="Ação atual:")
        action_label.get_style_context().add_class("status-label")
        
        self.action_indicator = Gtk.Label(label="neutral")
        self.action_indicator.get_style_context().add_class("status-badge")
        
        action_row.pack_start(action_label, False, False, 0)
        action_row.pack_end(self.action_indicator, False, False, 0)
        
        # Filtro temporal
        filter_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        filter_row.get_style_context().add_class("status-row")
        
        filter_label = Gtk.Label(label="Filtro temporal:")
        filter_label.get_style_context().add_class("status-label")
        
        self.filter_label = Gtk.Label(label="0/8")
        self.filter_label.get_style_context().add_class("status-badge")
        
        filter_row.pack_start(filter_label, False, False, 0)
        filter_row.pack_end(self.filter_label, False, False, 0)
        
        status_card.pack_start(status_header, False, False, 0)
        status_card.pack_start(self.status_label, False, False, 0)
        status_card.pack_start(action_row, False, False, 0)
        status_card.pack_start(filter_row, False, False, 0)
        sidebar.pack_start(status_card, False, False, 0)
        
        # Card de Gestos
        gestures_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        gestures_card.get_style_context().add_class("control-card")
        
        gestures_header = Gtk.Label(label="Gestos Disponíveis")
        gestures_header.get_style_context().add_class("card-header")
        gestures_header.set_halign(Gtk.Align.START)
        
        # Grid de gestos
        gesture_grid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        gesture_grid.get_style_context().add_class("gesture-grid")
        
        gestures = [
            "👆 1 dedo → Próximo slide",
            "✌️ 2 dedos → Slide anterior",
            "🤟 3 dedos → Início da apresentação", 
            "🖐️ 4 dedos → Fim da apresentação",
            "✊ Mão fechada → Neutro"
        ]
        
        for gesture in gestures:
            gesture_item = Gtk.Label(label=gesture)
            gesture_item.get_style_context().add_class("gesture-item")
            gesture_item.set_halign(Gtk.Align.START)
            gesture_grid.pack_start(gesture_item, False, False, 0)
        
        # Dica
        tip_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        tip_box.get_style_context().add_class("tip-box")
        
        tip_text = Gtk.Label(label="💡 Mantenha a mão visível na câmera e retorne à posição neutra entre os gestos para melhor detecção.")
        tip_text.get_style_context().add_class("tip-text")
        tip_text.set_line_wrap(True)
        tip_text.set_max_width_chars(35)
        tip_text.set_halign(Gtk.Align.START)
        
        tip_box.pack_start(tip_text, False, False, 0)
        
        gestures_card.pack_start(gestures_header, False, False, 0)
        gestures_card.pack_start(gesture_grid, False, False, 0)
        gestures_card.pack_start(tip_box, False, False, 0)
        sidebar.pack_start(gestures_card, True, True, 0)
        
        # === ÁREA PRINCIPAL ===
        main_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main_content.get_style_context().add_class("main-content")
        content_layout.pack_start(main_content, True, True, 0)
        
        # Preview da câmera
        video_preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        video_preview.get_style_context().add_class("video-preview")
        
        # Container do vídeo
        video_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        video_container.get_style_context().add_class("video-container")
        video_container.set_size_request(-1, 280)
        
        self.video_image = Gtk.Image()
        self.video_image.set_halign(Gtk.Align.CENTER)
        self.video_image.set_valign(Gtk.Align.CENTER)
        
        # Placeholder elegante
        self.placeholder_label = Gtk.Label(label="Câmera não ativada\n\nClique em 'Iniciar Detecção' para começar")
        self.placeholder_label.get_style_context().add_class("video-placeholder")
        self.placeholder_label.set_halign(Gtk.Align.CENTER)
        self.placeholder_label.set_valign(Gtk.Align.CENTER)
        
        video_container.pack_start(self.video_image, True, True, 0)
        video_container.pack_start(self.placeholder_label, True, True, 0)
        
        video_preview.pack_start(video_container, True, True, 0)
        main_content.pack_start(video_preview, True, True, 0)
        
    def on_zoom_changed(self, scale):
        self.zoom_level = scale.get_value()
        self.zoom_value_label.set_text(f"Zoom: {self.zoom_level:.1f}x")
    
    def set_zoom(self, zoom_value):
        self.zoom_level = zoom_value
        self.zoom_scale.set_value(zoom_value)
        self.zoom_value_label.set_text(f"Zoom: {zoom_value:.1f}x")
    
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
        self.start_button.set_label("Parar Detecção")
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
        self.start_button.set_label("Iniciar Detecção")
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
                GLib.idle_add(self.status_label.set_text, "Sistema calibrando...")
            else:
                # Lógica de execução de ações
                if action == "neutral":
                    if self.action_executed:
                        self.action_executed = False
                        GLib.idle_add(self.status_label.set_text, "Sistema ativo - Pronto")
                elif action != "neutral" and not self.action_executed:
                    if action == "next":
                        press_next()
                        GLib.idle_add(self.status_label.set_text, "Próximo slide executado")
                    elif action == "prev":
                        press_prev()
                        GLib.idle_add(self.status_label.set_text, "Slide anterior executado")
                    elif action == "home":
                        press_home()
                        GLib.idle_add(self.status_label.set_text, "Indo para o início")
                    elif action == "end":
                        press_end()
                        GLib.idle_add(self.status_label.set_text, "Indo para o fim")
                    self.action_executed = True
                    self.last_action = action
                elif action != "neutral" and self.action_executed:
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
            
            # Calcula nova dimensão mantendo proporção e limitando altura a 260px
            if original_height > 260:
                scale_factor = 260 / original_height
                new_width = int(original_width * scale_factor)
                new_height = 260
            else:
                new_width = original_width
                new_height = original_height
                
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
