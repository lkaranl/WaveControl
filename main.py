#!/usr/bin/env python3
import cv2
import time
import math
import uinput
import mediapipe as mp

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

# ===== Loop principal =====
cap = cv2.VideoCapture(CAM_INDEX)
start_ts = time.time()
last_action = "neutral"
action_executed = False  # flag para controlar execução

while cap.isOpened():
    ok, frame = cap.read()
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
            handed = res.multi_handedness[0].classification[0].label  # "Left"/"Right"
        raw_action = classify_gesture(lm.landmark, handed)
    
    # Adiciona gesto ao histórico e obtém gesto estável
    add_gesture_to_history(raw_action)
    action = get_stable_gesture()

    # Desenha landmarks se mão detectada
    if res.multi_hand_landmarks and DRAW:
        lm = res.multi_hand_landmarks[0]
        mp_drawing.draw_landmarks(
            frame, lm, mp_hands.HAND_CONNECTIONS,
            mp_drawing.DrawingSpec(color=(0,255,0), thickness=2, circle_radius=2),
            mp_drawing.DrawingSpec(color=(255,0,0), thickness=2)
        )

    now = time.time()

    # Calibração inicial
    if now - start_ts < CALIBRATION_S:
        if DRAW:
            cv2.putText(frame, "Calibrando...", (20,40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
    else:
        # Nova lógica: executa ação e aguarda neutral
        if action == "neutral":
            # Reset: permite nova ação quando volta ao neutral
            if action_executed:
                print(f"[DEBUG] Neutral detectado - permitindo nova ação")
                action_executed = False
        elif action != "neutral" and not action_executed:
            # Executa ação apenas se não foi executada ainda
            if action == "next":
                press_next()
                print(f"[DEBUG] NEXT executado - aguardando neutral")
            elif action == "prev":
                press_prev()
                print(f"[DEBUG] PREV executado - aguardando neutral")
            action_executed = True
            last_action = action
        elif action != "neutral" and action_executed:
            # Bloqueia ação até retornar ao neutral
            print(f"[DEBUG] Ação bloqueada - aguardando neutral (current: {action})")

    if DRAW:
        cv2.putText(frame, f"1 dedo: NEXT | 2 dedos: PREV", (20,80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200,200,200), 2)
        cv2.putText(frame, f"Acao: {action}", (20,120),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,200,255), 2)
        
        # Info do filtro temporal
        history_size = len(gesture_history)
        cv2.putText(frame, f"Filtro: {history_size}/{GESTURE_WINDOW_SIZE}", (20,160),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 2)
        if history_size > 0:
            cv2.putText(frame, f"Raw: {raw_action}", (20,190),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100,100,255), 2)
        
        # Info de debug
        cv2.putText(frame, f"Last: {last_action}", (20,220),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,100,100), 2)
        status = "BLOQUEADO" if action_executed else "PRONTO"
        color = (0,100,255) if action_executed else (0,255,100)
        cv2.putText(frame, f"Status: {status}", (20,250),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        cv2.imshow("Slide Controller", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == 27:  # ESC
        break

cap.release()
cv2.destroyAllWindows()
hands.close()
