# app_teste.py
import cv2
import mediapipe as mp
import numpy as np
import time

from mediapipe.tasks.python import vision
from mediapipe.tasks.python import BaseOptions

# -----------------------------
# CONFIGURAÇÃO DO MEDIAPIPE
# -----------------------------
options = vision.FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path="face_landmarker.task"),  # seu modelo
    running_mode=vision.RunningMode.VIDEO,
    num_faces=1
)
detector = vision.FaceLandmarker.create_from_options(options)

# -----------------------------
# LANDMARKS DE INTERESSE
# -----------------------------
# Pupila
iris_left = [468, 469, 470, 471, 472]
iris_right = [473, 474, 475, 476, 477]

# Borda inferior da armação aproximada (olho)
frame_border = [33, 263]  # canto externo inferior olho esquerdo/direito como referência

# -----------------------------
# FUNÇÕES DE CÁLCULO
# -----------------------------
def centro_iris(landmarks, indices, w, h):
    coords = np.array([[landmarks[i].x * w, landmarks[i].y * h] for i in indices])
    if len(coords) < 5:
        return 0,0
    try:
        centro = cv2.fitEllipse(coords.astype(np.int32))[0]
        return int(centro[0]), int(centro[1])
    except:
        # fallback para média simples
        return int(np.mean(coords[:,0])), int(np.mean(coords[:,1]))

def calcular_altura_montagem(ly, borda_inf):
    # distância vertical pupila → borda inferior da armação
    return borda_inf - ly

def calcular_corredor_progresso(ly, y_top_lente, y_bottom_lente):
    # retorna % de progressão pupila dentro da lente (0=topo, 100=parte inferior)
    return ((ly - y_top_lente) / (y_bottom_lente - y_top_lente)) * 100

# -----------------------------
# MAIN LOOP
# -----------------------------
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("Erro: webcam não encontrada!")
    exit()

print("Iniciando teste de medição com debug completo...")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Erro capturando frame")
        break

    h, w = frame.shape[:2]
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    timestamp = int(time.time() * 1000)
    result = detector.detect_for_video(mp_image, timestamp)

    if not result.face_landmarks:
        print("[DEBUG] Nenhuma face detectada")
        cv2.imshow("Teste Montagem", frame)
        if cv2.waitKey(1) & 0xFF == 27:
            break
        continue

    lm = result.face_landmarks[0]

    # =========================
    # Pupilas
    lx, ly = centro_iris(lm, iris_left, w, h)
    rx, ry = centro_iris(lm, iris_right, w, h)
    print(f"[DEBUG] Pupila esquerda: ({lx},{ly})  Pupila direita: ({rx},{ry})")

    # =========================
    # Borda inferior (aproximação)
    borda_inf_y = int((lm[frame_border[0]].y + lm[frame_border[1]].y)/2 * h)
    print(f"[DEBUG] Borda inferior da armação aprox: y={borda_inf_y}")

    # =========================
    # Altura de Montagem
    altura_montagem = calcular_altura_montagem((ly+ry)/2, borda_inf_y)
    print(f"[DEBUG] Altura de montagem (pixels): {altura_montagem}")

    # =========================
    # Corredor de Progressão
    y_top_lente = borda_inf_y - 50  # arbitrário para teste
    y_bottom_lente = borda_inf_y
    progresso = calcular_corredor_progresso((ly+ry)/2, y_top_lente, y_bottom_lente)
    print(f"[DEBUG] Corredor de progressão: {progresso:.1f}%")

    # =========================
    # OVERLAY
    cv2.circle(frame, (lx, ly), 4, (0,255,0), -1)
    cv2.circle(frame, (rx, ry), 4, (0,255,0), -1)
    cv2.line(frame, (0, borda_inf_y), (w, borda_inf_y), (255,0,0), 2)
    cv2.putText(frame, f"Altura montagem: {altura_montagem:.1f}px", (10,30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,255), 2)
    cv2.putText(frame, f"Corredor prog: {progresso:.1f}%", (10,60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,255), 2)

    cv2.imshow("Teste Montagem", frame)
    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()