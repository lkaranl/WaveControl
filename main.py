#!/usr/bin/env python3
import cv2
import time
import uinput
import mediapipe as mp
import gi
import os
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

# ===== Interface Gráfica GTK =====
class WaveControlGUI(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self)
        self.set_default_size(850, 600)
        self.set_position(Gtk.WindowPosition.CENTER)
        
        # Aplicar CSS moderno
        self.apply_modern_styling()
        
        # Variáveis de controle
        self.is_running = False
        self.cap = None
        self.start_ts = None
        self.last_action = "neutral"
        self.action_executed = False
        
        # Setup da interface
        self.setup_ui()
        
        # Conecta eventos
        self.connect("destroy", self.on_window_destroy)
    
    def apply_modern_styling(self):
        """Aplica estilo minimalista respeitando o tema GTK"""
        css_provider = Gtk.CssProvider()
        css = """
        /* Layout minimalista usando cores do tema */
        .main-container {
            margin: 12px;
        }
        
        .header-section {
            padding: 16px 20px;
            margin-bottom: 8px;
            border-bottom: 1px solid alpha(@borders, 0.3);
        }
        
        .app-title {
            font-size: 20px;
            font-weight: 500;
        }
        
        .app-subtitle {
            font-size: 13px;
            opacity: 0.7;
            margin-top: 2px;
        }
        
        .content-section {
            margin: 8px 0;
        }
        
        .video-area {
            border-radius: 8px;
            border: 1px solid alpha(@borders, 0.2);
            padding: 12px;
            margin: 8px;
        }
        
        .video-container {
            border-radius: 6px;
            border: 2px dashed alpha(@borders, 0.4);
            min-height: 300px;
            background: alpha(@theme_base_color, 0.3);
        }
        
        .controls-section {
            margin: 8px;
            padding: 16px;
            border-radius: 8px;
            border: 1px solid alpha(@borders, 0.2);
        }
        
        .section-title {
            font-size: 14px;
            font-weight: 500;
            margin-bottom: 12px;
            opacity: 0.9;
        }
        
        .primary-button {
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: 500;
        }
        
        .status-indicator {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-family: monospace;
            background: alpha(@theme_selected_bg_color, 0.1);
            color: @theme_selected_bg_color;
        }
        
        .info-section {
            margin: 8px;
            padding: 12px;
            border-radius: 6px;
            background: alpha(@theme_selected_bg_color, 0.05);
            border-left: 3px solid alpha(@theme_selected_bg_color, 0.3);
        }
        
        .instruction-text {
            font-size: 13px;
            margin: 4px 0;
        }
        
        .tip-text {
            font-size: 12px;
            font-style: italic;
            opacity: 0.7;
            margin-top: 8px;
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
        
        # Header minimalista
        header_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        header_section.get_style_context().add_class("header-section")
        
        title_label = Gtk.Label(label="WaveControl")
        title_label.get_style_context().add_class("app-title")
        title_label.set_halign(Gtk.Align.START)
        
        subtitle_label = Gtk.Label(label="Controle de slides por gestos")
        subtitle_label.get_style_context().add_class("app-subtitle")
        subtitle_label.set_halign(Gtk.Align.START)
        
        header_section.pack_start(title_label, False, False, 0)
        header_section.pack_start(subtitle_label, False, False, 0)
        main_container.pack_start(header_section, False, False, 0)
        
        # Área de vídeo
        video_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        video_section.get_style_context().add_class("video-area")
        
        video_title = Gtk.Label(label="Visualização")
        video_title.get_style_context().add_class("section-title")
        video_title.set_halign(Gtk.Align.START)
        
        # Container do vídeo
        video_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        video_container.get_style_context().add_class("video-container")
        video_container.set_size_request(-1, 300)
        
        self.video_image = Gtk.Image()
        self.video_image.set_halign(Gtk.Align.CENTER)
        self.video_image.set_valign(Gtk.Align.CENTER)
        
        # Placeholder simples
        self.placeholder_label = Gtk.Label(label="Câmera desativada\nClique em 'Iniciar' para começar")
        self.placeholder_label.set_halign(Gtk.Align.CENTER)
        self.placeholder_label.set_valign(Gtk.Align.CENTER)
        self.placeholder_label.set_opacity(0.6)
        
        video_container.pack_start(self.video_image, True, True, 0)
        video_container.pack_start(self.placeholder_label, True, True, 0)
        
        video_section.pack_start(video_title, False, False, 0)
        video_section.pack_start(video_container, True, True, 0)
        main_container.pack_start(video_section, True, True, 0)
        
        # Layout horizontal para controles e status
        horizontal_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        main_container.pack_start(horizontal_container, False, False, 0)
        
        # Seção de controles
        controls_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        controls_section.get_style_context().add_class("controls-section")
        controls_section.set_size_request(240, -1)
        
        controls_title = Gtk.Label(label="Controles")
        controls_title.get_style_context().add_class("section-title")
        controls_title.set_halign(Gtk.Align.START)
        
        # Botão principal
        self.start_button = Gtk.Button.new_with_label("Iniciar")
        self.start_button.get_style_context().add_class("primary-button")
        self.start_button.connect("clicked", self.on_start_clicked)
        
        # Checkbox
        self.show_landmarks_check = Gtk.CheckButton.new_with_label("Mostrar landmarks")
        self.show_landmarks_check.set_active(DRAW)
        
        controls_section.pack_start(controls_title, False, False, 0)
        controls_section.pack_start(self.start_button, False, False, 0)
        controls_section.pack_start(self.show_landmarks_check, False, False, 0)
        horizontal_container.pack_start(controls_section, False, False, 0)
        
        # Seção de status
        status_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        status_section.get_style_context().add_class("controls-section")
        
        status_title = Gtk.Label(label="Status")
        status_title.get_style_context().add_class("section-title")
        status_title.set_halign(Gtk.Align.START)
        
        self.status_label = Gtk.Label(label="Sistema parado")
        self.status_label.set_halign(Gtk.Align.START)
        
        # Container para ação atual
        action_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        action_label = Gtk.Label(label="Ação:")
        action_label.set_halign(Gtk.Align.START)
        
        self.action_indicator = Gtk.Label(label="neutral")
        self.action_indicator.get_style_context().add_class("status-indicator")
        
        action_container.pack_start(action_label, False, False, 0)
        action_container.pack_start(self.action_indicator, False, False, 0)
        
        # Filtro
        self.filter_label = Gtk.Label(label="Filtro: 0/8")
        self.filter_label.set_halign(Gtk.Align.START)
        self.filter_label.set_opacity(0.7)
        
        status_section.pack_start(status_title, False, False, 0)
        status_section.pack_start(self.status_label, False, False, 0)
        status_section.pack_start(action_container, False, False, 0)
        status_section.pack_start(self.filter_label, False, False, 0)
        horizontal_container.pack_start(status_section, True, True, 0)
        
        # Seção de informações
        info_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        info_section.get_style_context().add_class("info-section")
        
        info_title = Gtk.Label(label="Instruções")
        info_title.get_style_context().add_class("section-title")
        info_title.set_halign(Gtk.Align.START)
        
        instructions = [
            "1 dedo → Próximo slide",
            "2 dedos → Slide anterior",
            "3 dedos → Início da apresentação",
            "4 dedos → Fim da apresentação",
            "Mão fechada → Neutro"
        ]
        
        for instruction in instructions:
            label = Gtk.Label(label=instruction)
            label.get_style_context().add_class("instruction-text")
            label.set_halign(Gtk.Align.START)
            info_section.pack_start(label, False, False, 0)
        
        tip_label = Gtk.Label(label="Retorne à posição neutra antes da próxima ação")
        tip_label.get_style_context().add_class("tip-text")
        tip_label.set_halign(Gtk.Align.START)
        tip_label.set_line_wrap(True)
        tip_label.set_max_width_chars(40)
        
        info_section.pack_start(info_title, False, False, 0)
        info_section.pack_start(tip_label, False, False, 8)
        main_container.pack_start(info_section, False, False, 0)
        
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
        self.start_button.set_label("Parar")
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
        self.start_button.set_label("Iniciar")
        self.status_label.set_text("Sistema parado")
        
        # Mostra placeholder e esconde vídeo
        self.video_image.clear()
        self.video_image.hide()
        self.placeholder_label.show()
        
        # Reset dos indicadores
        self.action_indicator.set_text("neutral")
        self.filter_label.set_text("Filtro: 0/8")
        
    def process_video(self):
        while self.is_running and self.cap and self.cap.isOpened():
            ok, frame = self.cap.read()
            if not ok:
                break
                
            frame = cv2.flip(frame, 1)
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
            GLib.idle_add(self.filter_label.set_text, f"Filtro: {len(gesture_history)}/{GESTURE_WINDOW_SIZE}")
            
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
            
            # Calcula nova dimensão mantendo proporção e limitando altura a 300px
            if original_height > 300:
                scale_factor = 300 / original_height
                new_width = int(original_width * scale_factor)
                new_height = 300
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
