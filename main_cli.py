#!/usr/bin/env python3
import cv2
import time
import uinput
import mediapipe as mp

# ===== Configurações =====
MIN_DET = 0.6
MIN_TRK = 0.6
CALIBRATION_S = 2.0     # tempo inicial para estabilizar câmera
CAM_INDEX = 0           # índice da webcam

# ===== Filtro Temporal =====
GESTURE_WINDOW_SIZE = 8  # número de frames para confirmar gesto
CONSISTENCY_THRESHOLD = 0.75  # 75% das amostras devem ser iguais

# ===== Dispositivo virtual (uinput) =====
kb = uinput.Device([uinput.KEY_RIGHT, uinput.KEY_LEFT, uinput.KEY_HOME, uinput.KEY_END])

# ===== MediaPipe =====
mp_hands = mp.solutions.hands
hands = None  # Será inicializado depois

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

# ===== Controle de Estado =====
class WaveControlCLI:
    def __init__(self):
        self.is_running = False
        self.cap = None
        self.start_ts = None
        self.last_action = "neutral"
        self.action_executed = False
        
    def find_camera(self):
        """Tenta encontrar uma câmera disponível testando vários índices"""
        print("🔍 Procurando câmeras disponíveis...")
        
        for i in range(10):  # Testa índices 0-9
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                # Testa se consegue ler um frame
                ret, _ = cap.read()
                if ret:
                    print(f"✅ Câmera encontrada no índice {i}")
                    return cap, i
                cap.release()
                
        return None, -1
    
    def start_detection(self):
        global gesture_history, hands
        gesture_history.clear()
        
        print("🎯 WaveControl CLI - Iniciando detecção de gestos...")
        
        self.cap, cam_index = self.find_camera()
        if self.cap is None:
            print("❌ Erro: Nenhuma câmera disponível encontrada!")
            print("   Possíveis soluções:")
            print("   • Conecte uma webcam USB")
            print("   • Verifique se a câmera não está sendo usada por outro app")
            print("   • Reinicie o sistema se necessário")
            return False
        
        # Inicializa MediaPipe após abrir a câmera
        print("🤖 Inicializando MediaPipe...")
        hands = mp_hands.Hands(
            max_num_hands=1,
            model_complexity=0,
            min_detection_confidence=MIN_DET,
            min_tracking_confidence=MIN_TRK,
        )
            
        self.is_running = True
        self.start_ts = time.time()
        
        print("✅ Câmera iniciada com sucesso!")
        print("⏱️  Calibrando por 2 segundos...")
        print("\n📋 Gestos disponíveis:")
        print("   👆 1 dedo → Próximo slide")
        print("   ✌️  2 dedos → Slide anterior")
        print("   🤟 3 dedos → Início da apresentação")
        print("   🖐️  4 dedos → Fim da apresentação")
        print("   ✊ Mão fechada → Neutro")
        print("\n💡 Mantenha a mão visível na câmera!")
        print("🛑 Pressione Ctrl+C para parar\n")
        
        return True
        
    def process_video(self):
        frame_count = 0
        
        while self.is_running and self.cap and self.cap.isOpened():
            try:
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
                
                now = time.time()
                
                # Calibração inicial
                if now - self.start_ts < CALIBRATION_S:
                    if frame_count % 30 == 0:  # Mostra a cada segundo
                        remaining = int(CALIBRATION_S - (now - self.start_ts))
                        print(f"⏱️  Calibrando... {remaining}s restantes")
                else:
                    # Lógica de execução de ações
                    if action == "neutral":
                        if self.action_executed:
                            self.action_executed = False
                            print("✅ Sistema pronto para nova ação")
                    elif action != "neutral" and not self.action_executed:
                        if action == "next":
                            press_next()
                            print("➡️  PRÓXIMO slide executado")
                        elif action == "prev":
                            press_prev()
                            print("⬅️  ANTERIOR slide executado")
                        elif action == "home":
                            press_home()
                            print("🏠 INÍCIO da apresentação")
                        elif action == "end":
                            press_end()
                            print("🔚 FIM da apresentação")
                        self.action_executed = True
                        self.last_action = action
                    elif action != "neutral" and self.action_executed:
                        # Não mostra mensagem repetitiva, apenas aguarda
                        pass
                
                frame_count += 1
                time.sleep(0.03)  # ~30 FPS
                
            except KeyboardInterrupt:
                print("\n🛑 Interrompido pelo usuário")
                break
                
    def stop_detection(self):
        self.is_running = False
        if self.cap:
            self.cap.release()
        print("📷 Câmera desconectada")
        print("👋 WaveControl CLI finalizado")

def list_cameras():
    """Lista todas as câmeras disponíveis"""
    print("🔍 Listando câmeras disponíveis:")
    found = False
    
    for i in range(10):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                print(f"   📷 Câmera {i}: Disponível")
                found = True
            cap.release()
    
    if not found:
        print("   ❌ Nenhuma câmera encontrada")
    print()

def main():
    import sys
    
    print("🌊 WaveControl CLI")
    print("================")
    
    # Verifica argumentos da linha de comando
    if len(sys.argv) > 1:
        if sys.argv[1] in ["-l", "--list", "list"]:
            list_cameras()
            return
        elif sys.argv[1] in ["-h", "--help", "help"]:
            print("Uso:")
            print("  python3 main_cli.py          # Executar detecção de gestos")
            print("  python3 main_cli.py -l       # Listar câmeras disponíveis")
            print("  python3 main_cli.py -h       # Mostrar esta ajuda")
            print()
            print("Gestos:")
            print("  👆 1 dedo → Próximo slide")
            print("  ✌️  2 dedos → Slide anterior")
            print("  🤟 3 dedos → Início da apresentação")
            print("  🖐️  4 dedos → Fim da apresentação")
            print("  ✊ Mão fechada → Neutro")
            return
    
    try:
        cli = WaveControlCLI()
        if cli.start_detection():
            cli.process_video()
        cli.stop_detection()
        
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
    
    finally:
        if hands:
            hands.close()

if __name__ == "__main__":
    main()
