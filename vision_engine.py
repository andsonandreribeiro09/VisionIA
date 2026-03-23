import cv2
import mediapipe as mp
import numpy as np
import os

from mediapipe.tasks.python import vision
from mediapipe.tasks.python import BaseOptions

# -----------------------------
# CONFIG MEDIAPIPE
# -----------------------------
options = vision.FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path="face_landmarker.task"),
    running_mode=vision.RunningMode.VIDEO,
    num_faces=1
)

detector = vision.FaceLandmarker.create_from_options(options)

# -----------------------------
# SUAVIZAÇÃO
# -----------------------------
SMOOTH = 0.75
smooth = {
    "lx": None, "ly": None,
    "rx": None, "ry": None,
    "nx": None, "ny": None
}

# -----------------------------
# CACHE DE ARMAÇÕES
# -----------------------------
cache_armacoes = {}

def carregar_armacao(nome):

    if nome in cache_armacoes:
        return cache_armacoes[nome]

    caminho = os.path.join("static", "armacoes", nome)

    img = cv2.imread(caminho, cv2.IMREAD_UNCHANGED)

    if img is None:
        print("Erro carregando:", caminho)
        return None

    # garante canal alpha
    if img.shape[2] == 4:
        cache_armacoes[nome] = img
        return img

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)

    b, g, r = cv2.split(img)
    img = cv2.merge([b, g, r, mask])

    cache_armacoes[nome] = img
    return img

# -----------------------------
# CÁLCULO DE MEDIDAS
# -----------------------------
def calcular_medidas(smooth, escala):

    dp_px = np.linalg.norm(
        np.array([smooth["lx"], smooth["ly"]]) -
        np.array([smooth["rx"], smooth["ry"]])
    )

    dnp_e_px = np.linalg.norm(
        np.array([smooth["lx"], smooth["ly"]]) -
        np.array([smooth["nx"], smooth["ny"]])
    )

    dnp_d_px = np.linalg.norm(
        np.array([smooth["rx"], smooth["ry"]]) -
        np.array([smooth["nx"], smooth["ny"]])
    )

    dp_mm = dp_px * escala
    dnp_e_mm = dnp_e_px * escala
    dnp_d_mm = dnp_d_px * escala

    return dp_mm, dnp_e_mm, dnp_d_mm

# -----------------------------
# FUNÇÃO PRINCIPAL
# -----------------------------
def processar_frame(frame):

    h, w = frame.shape[:2]

    # timestamp
    frame_id = getattr(processar_frame, "frame_id", 0) + 1
    processar_frame.frame_id = frame_id
    timestamp = frame_id * 33

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    mp_image = mp.Image(
        image_format=mp.ImageFormat.SRGB,
        data=rgb
    )

    result = detector.detect_for_video(mp_image, timestamp)

    if not result.face_landmarks:
        return frame

    lm = result.face_landmarks[0]

    # -----------------------------
    # LANDMARKS
    # -----------------------------
    iris_l = lm[468]
    iris_r = lm[473]
    nose = lm[1]
    t_l = lm[127]
    t_r = lm[356]

    lx, ly = int(iris_l.x * w), int(iris_l.y * h)
    rx, ry = int(iris_r.x * w), int(iris_r.y * h)
    nx, ny = int(nose.x * w), int(nose.y * h)

    xt1 = int(t_l.x * w)
    xt2 = int(t_r.x * w)

    # -----------------------------
    # SUAVIZAÇÃO
    # -----------------------------
    if smooth["lx"] is None:
        smooth["lx"], smooth["ly"] = lx, ly
        smooth["rx"], smooth["ry"] = rx, ry
        smooth["nx"], smooth["ny"] = nx, ny

    for k, v in [("lx", lx), ("ly", ly),
                 ("rx", rx), ("ry", ry),
                 ("nx", nx), ("ny", ny)]:
        smooth[k] = int(SMOOTH * smooth[k] + (1 - SMOOTH) * v)

    # -----------------------------
    # ESCALA PELA ÍRIS (REAL)
    # -----------------------------
    iris_points = [468, 469, 470, 471, 472]
    pts = [(lm[i].x * w, lm[i].y * h) for i in iris_points]

    x_coords = [p[0] for p in pts]
    iris_px = max(x_coords) - min(x_coords)

    if iris_px < 1:
        return frame

    escala_iris = 11.7 / iris_px  # mm reais da íris

    # -----------------------------
    # ESCALA PELO ROSTO
    # -----------------------------
    face_px = max(1, abs(xt2 - xt1))
    escala_face = 140 / face_px  # mm médio rosto

    # -----------------------------
    # ESCALA FINAL
    # -----------------------------
    escala = (escala_iris * 0.7) + (escala_face * 0.3)

    # -----------------------------
    # MEDIÇÕES
    # -----------------------------
    dp_mm, dnp_e_mm, dnp_d_mm = calcular_medidas(smooth, escala)

    # -----------------------------
    # VALIDAÇÃO
    # -----------------------------
    if dp_mm < 50 or dp_mm > 80:
        status = "Ajuste distância"
        cor = (0, 0, 255)
    else:
        status = "Medição OK"
        cor = (0, 255, 0)

    # -----------------------------
    # VISUAL DEBUG
    # -----------------------------
    cv2.circle(frame, (smooth["lx"], smooth["ly"]), 4, (255, 0, 0), -1)
    cv2.circle(frame, (smooth["rx"], smooth["ry"]), 4, (0, 255, 0), -1)
    cv2.circle(frame, (smooth["nx"], smooth["ny"]), 4, (0, 0, 255), -1)

    # -----------------------------
    # TEXTO
    # -----------------------------
    cv2.putText(frame, f"DP: {dp_mm:.1f} mm", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, cor, 2)

    cv2.putText(frame, f"DNP E: {dnp_e_mm:.1f}", (20, 70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

    cv2.putText(frame, f"DNP D: {dnp_d_mm:.1f}", (20, 100),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

    cv2.putText(frame, status, (20, 130),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, cor, 2)

    return frame