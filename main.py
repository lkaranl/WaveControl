#!/usr/bin/env python3
import cv2
import time
import math
import uinput
import mediapipe as mp
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, GdkPixbuf, Gdk
import threading
import numpy as np

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
kb = uinput.Device([uinput.KEY_RIGHT, uinput.KEY_LEFT])

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
# 1 dedo levantado: próximo; 2 dedos levantados: anterior; senão: neutro
def classify_gesture(lm, handed_label):
    n = count_extended(lm, handed_label)
    if n == 1: return "next"      # um dedo levantado
    if n == 2: return "prev"      # dois dedos levantados
    return "neutral"

def press_next():
    kb.emit_click(uinput.KEY_RIGHT)

def press_prev():
    kb.emit_click(uinput.KEY_LEFT)

# ===== Interface Gráfica GTK =====
class WaveControlGUI(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="WaveControl - Controle por Gestos")
        self.set_default_size(800, 600)
        self.set_position(Gtk.WindowPosition.CENTER)
        
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
        
    def setup_ui(self):
        # Container principal
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_left(20)
        main_box.set_margin_right(20)
        main_box.set_margin_top(20)
        main_box.set_margin_bottom(20)
        self.add(main_box)
        
        # Título
        title_label = Gtk.Label()
        title_label.set_markup("<big><b>WaveControl - Controle de Slides por Gestos</b></big>")
        main_box.pack_start(title_label, False, False, 0)
        
        # Área de vídeo
        self.video_frame = Gtk.Frame()
        self.video_frame.set_label("Visualização da Câmera")
        self.video_image = Gtk.Image()
        self.video_image.set_size_request(640, 480)
        self.video_frame.add(self.video_image)
        main_box.pack_start(self.video_frame, True, True, 0)
        
        # Painel de controles
        controls_frame = Gtk.Frame()
        controls_frame.set_label("Controles")
        controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        controls_box.set_margin_left(10)
        controls_box.set_margin_right(10)
        controls_box.set_margin_top(10)
        controls_box.set_margin_bottom(10)
        
        # Botão iniciar/parar
        self.start_button = Gtk.Button.new_with_label("Iniciar Detecção")
        self.start_button.connect("clicked", self.on_start_clicked)
        controls_box.pack_start(self.start_button, False, False, 0)
        
        # Checkbox para mostrar landmarks
        self.show_landmarks_check = Gtk.CheckButton.new_with_label("Mostrar Landmarks")
        self.show_landmarks_check.set_active(DRAW)
        controls_box.pack_start(self.show_landmarks_check, False, False, 0)
        
        controls_frame.add(controls_box)
        main_box.pack_start(controls_frame, False, False, 0)
        
        # Painel de status
        status_frame = Gtk.Frame()
        status_frame.set_label("Status")
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        status_box.set_margin_left(10)
        status_box.set_margin_right(10)
        status_box.set_margin_top(10)
        status_box.set_margin_bottom(10)
        
        self.status_label = Gtk.Label("Sistema parado")
        self.action_label = Gtk.Label("Ação: neutral")
        self.gesture_label = Gtk.Label("Gesto: neutral")
        self.filter_label = Gtk.Label("Filtro: 0/8")
        
        status_box.pack_start(self.status_label, False, False, 0)
        status_box.pack_start(self.action_label, False, False, 0)
        status_box.pack_start(self.gesture_label, False, False, 0)
        status_box.pack_start(self.filter_label, False, False, 0)
        
        status_frame.add(status_box)
        main_box.pack_start(status_frame, False, False, 0)
        
        # Informações
        info_frame = Gtk.Frame()
        info_frame.set_label("Instruções")
        info_label = Gtk.Label()
        info_label.set_markup(
            "<b>Como usar:</b>\n"
            "• <b>1 dedo levantado:</b> Próximo slide (tecla →)\n"
            "• <b>2 dedos levantados:</b> Slide anterior (tecla ←)\n"
            "• <b>Feche a mão:</b> Posição neutra (sem ação)\n\n"
            "<i>O sistema aguarda você retornar à posição neutra antes de executar a próxima ação.</i>"
        )
        info_label.set_line_wrap(True)
        info_label.set_margin_left(10)
        info_label.set_margin_right(10)
        info_label.set_margin_top(10)
        info_label.set_margin_bottom(10)
        info_frame.add(info_label)
        main_box.pack_start(info_frame, False, False, 0)
        
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
            dialog.format_secondary_text("Verifique se a câmera está conectada e não está sendo usada por outro aplicativo.")
            dialog.run()
            dialog.destroy()
            return
            
        self.is_running = True
        self.start_ts = time.time()
        self.start_button.set_label("Parar Detecção")
        self.status_label.set_text("Sistema rodando - Calibrando...")
        
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
        self.video_image.clear()
        
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
                GLib.idle_add(self.status_label.set_text, "Sistema rodando - Calibrando...")
            else:
                # Lógica de execução de ações
                if action == "neutral":
                    if self.action_executed:
                        self.action_executed = False
                        GLib.idle_add(self.status_label.set_text, "Sistema rodando - Pronto para nova ação")
                elif action != "neutral" and not self.action_executed:
                    if action == "next":
                        press_next()
                        GLib.idle_add(self.status_label.set_text, "Sistema rodando - NEXT executado")
                    elif action == "prev":
                        press_prev()
                        GLib.idle_add(self.status_label.set_text, "Sistema rodando - PREV executado")
                    self.action_executed = True
                    self.last_action = action
                elif action != "neutral" and self.action_executed:
                    GLib.idle_add(self.status_label.set_text, "Sistema rodando - Aguardando posição neutra")
            
            # Atualiza labels de status
            GLib.idle_add(self.action_label.set_text, f"Ação: {action}")
            GLib.idle_add(self.gesture_label.set_text, f"Gesto raw: {raw_action}")
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
            
            # Redimensiona para caber na interface
            pixbuf = pixbuf.scale_simple(640, 480, GdkPixbuf.InterpType.BILINEAR)
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
