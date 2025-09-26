#!/usr/bin/env python3
import cv2
import time
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import threading
from pynput.keyboard import Key
from pynput import keyboard
import numpy as np

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

# ===== Detecção de Movimento Simples =====
class SimpleGestureDetector:
    def __init__(self):
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(detectShadows=True)
        self.kernel = np.ones((5,5), np.uint8)
        self.last_gesture = "neutral"
        
    def detect_gesture(self, frame):
        """Detecção simples baseada em movimento e contornos"""
        # Aplica subtração de fundo
        fg_mask = self.bg_subtractor.apply(frame)
        
        # Operações morfológicas para limpar a máscara
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, self.kernel)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, self.kernel)
        
        # Encontra contornos
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return "neutral", fg_mask
        
        # Pega o maior contorno (assumindo que é a mão)
        largest_contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest_contour)
        
        # Classifica baseado na área do contorno
        if area < 5000:
            return "neutral", fg_mask
        elif area < 15000:
            return "next", fg_mask  # 1 dedo (área pequena)
        elif area < 25000:
            return "prev", fg_mask  # 2 dedos
        elif area < 35000:
            return "home", fg_mask  # 3 dedos
        else:
            return "end", fg_mask   # 4 dedos (área grande)
    
    def close(self):
        pass

# Instância do detector
detector = SimpleGestureDetector()

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

# ===== Ações de Teclado =====
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

# ===== Interface Tkinter para Windows =====
class WaveControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("WaveControl - Windows Edition (Simples)")
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
        self.show_movement = tk.BooleanVar(value=DRAW)
        
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
        
        title_label = ttk.Label(header_left, text="WaveControl - Windows (Simples)", style='Title.TLabel')
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
        
        footer_label = ttk.Label(footer, text="WaveControl Windows - Controle por gestos (Versão Simples) | Criado por Karan Luciano",
                                font=('Arial', 9), foreground='gray')
        footer_label.pack(anchor='center')
    
    def create_gestures_card(self, parent):
        card = ttk.LabelFrame(parent, text="Gestos (Movimento)", padding=15)
        card.pack(fill='x', pady=(0, 10))
        
        gestures = [
            "🟢 Pouco movimento → Próximo (→)",
            "🟡 Movimento médio → Anterior (←)", 
            "🟠 Movimento grande → Início (Home)",
            "🔴 Movimento máximo → Fim (End)",
            "⚫ Sem movimento → Neutro"
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
    
    def create_config_card(self, parent):
        card = ttk.LabelFrame(parent, text="Configurações", padding=15)
        card.pack(fill='x', pady=(0, 10))
        
        movement_check = ttk.Checkbutton(card, text="Mostrar detecção",
                                       variable=self.show_movement)
        movement_check.pack(anchor='w')
    
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
        if self.cap:
            self.cap.release()
        
        # Atualiza interface
        self.start_button.config(text="▶ Iniciar")
        self.status_label.config(text="Sistema parado", foreground=self.colors['warning'])
        self.main_status.config(text="Sistema parado")
        
        # Limpa vídeo e mostra placeholder
        if hasattr(self, 'video_display'):
            self.video_display.destroy()
        
        self.video_label.config(text="📷\n\nCâmera não ativada\n\nClique em 'Iniciar' para começar")
        self.video_label.pack(expand=True)
        
        # Reset status
        self.gesture_status.config(text="neutral")
        self.filter_status.config(text="0/8")
    
    def process_video(self):
        # Cria label para o vídeo
        if not hasattr(self, 'video_display'):
            self.video_display = ttk.Label(self.video_container)
            self.video_display.pack(expand=True)
        
        while self.is_running and self.cap and self.cap.isOpened():
            ok, frame = self.cap.read()
            if not ok:
                break
            
            frame = cv2.flip(frame, 1)
            frame = apply_digital_zoom(frame, self.zoom_level.get())
            
            # Detecta gesto baseado em movimento
            action, movement_mask = detector.detect_gesture(frame)
            
            add_gesture_to_history(action)
            stable_action = get_stable_gesture()
            
            # Desenha detecção se habilitado
            if self.show_movement.get():
                # Converte máscara para 3 canais para exibir
                movement_colored = cv2.applyColorMap(movement_mask, cv2.COLORMAP_JET)
                # Sobrepor na imagem original
                frame = cv2.addWeighted(frame, 0.7, movement_colored, 0.3, 0)
            
            now = time.time()
            
            # Informações na tela
            if self.zoom_level.get() > 1.0:
                zoom_text = f"Zoom: {self.zoom_level.get():.1f}x"
                cv2.putText(frame, zoom_text, (20, frame.shape[0] - 20), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)
            
            # Calibração
            if now - self.start_ts < CALIBRATION_S:
                cv2.putText(frame, "Calibrando...", (20,40), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
                self.root.after(0, lambda: self.status_label.config(text="Calibrando...", 
                                                                   foreground=self.colors['warning']))
            else:
                # Executa ações
                if stable_action == "neutral":
                    if self.action_executed:
                        self.action_executed = False
                        self.root.after(0, lambda: self.status_label.config(text="Sistema ativo", 
                                                                           foreground=self.colors['success']))
                        self.root.after(0, lambda: self.main_status.config(text="Sistema ativo - Pronto"))
                elif stable_action != "neutral" and not self.action_executed:
                    if stable_action == "next":
                        press_next()
                        self.root.after(0, lambda: self.status_label.config(text="Próximo →", 
                                                                           foreground=self.colors['accent']))
                        self.root.after(0, lambda: self.main_status.config(text="Próximo slide executado"))
                    elif stable_action == "prev":
                        press_prev()
                        self.root.after(0, lambda: self.status_label.config(text="← Anterior", 
                                                                           foreground=self.colors['accent']))
                        self.root.after(0, lambda: self.main_status.config(text="Slide anterior executado"))
                    elif stable_action == "home":
                        press_home()
                        self.root.after(0, lambda: self.status_label.config(text="⏮ Início", 
                                                                           foreground=self.colors['accent']))
                        self.root.after(0, lambda: self.main_status.config(text="Indo para o início"))
                    elif stable_action == "end":
                        press_end()
                        self.root.after(0, lambda: self.status_label.config(text="⏭ Fim", 
                                                                           foreground=self.colors['accent']))
                        self.root.after(0, lambda: self.main_status.config(text="Indo para o fim"))
                    self.action_executed = True
                    self.last_action = stable_action
                elif stable_action != "neutral" and self.action_executed:
                    self.root.after(0, lambda: self.status_label.config(text="Aguardando...", 
                                                                       foreground=self.colors['warning']))
                    self.root.after(0, lambda: self.main_status.config(text="Aguardando posição neutra"))
            
            # Atualiza indicadores
            self.root.after(0, lambda: self.gesture_status.config(text=stable_action))
            self.root.after(0, lambda: self.filter_status.config(text=f"{len(gesture_history)}/{GESTURE_WINDOW_SIZE}"))
            
            # Converte e exibe frame
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb)
            
            # Redimensiona para caber na interface
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
            
            time.sleep(0.03)  # ~30 FPS
    
    def update_video_display(self, photo):
        if hasattr(self, 'video_display') and self.video_display.winfo_exists():
            self.video_display.config(image=photo)
            self.video_display.image = photo  # Manter referência
    
    def on_closing(self):
        self.stop_detection()
        if detector:
            detector.close()
        self.root.destroy()

# ===== Execução Principal =====
def main():
    root = tk.Tk()
    app = WaveControlApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
