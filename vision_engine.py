import os
import cv2
import time
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import vision
from mediapipe.tasks.python import BaseOptions

# =========================================================
# CONFIGURAÇÕES RENDER / SERVIDOR
# =========================================================

IS_RENDER = os.environ.get("RENDER") is not None

# -----------------------------
# CALIBRAÇÃO DE CÂMERA
# -----------------------------
def _env_float(nome, padrao):
    try:
        return float(os.environ.get(nome, padrao))
    except (TypeError, ValueError):
        return padrao


IPD_REAL_MM = _env_float("VISIONAI_IPD_REAL_MM", 63.0)
IRIS_REAL_MM = _env_float("VISIONAI_IRIS_REAL_MM", 11.7)
TARGET_DISTANCE_CM = _env_float("VISIONAI_TARGET_DISTANCE_CM", 40.0)
SCALE_MULTIPLIER = _env_float("VISIONAI_SCALE_MULTIPLIER", 1.0)
MIN_MM_PER_PX = _env_float("VISIONAI_MIN_MM_PER_PX", 0.08)
MAX_MM_PER_PX = _env_float("VISIONAI_MAX_MM_PER_PX", 0.80)
CAPTURE_MIN_SCORE = _env_float("VISIONAI_CAPTURE_MIN_SCORE", 75.0)
CAPTURE_RESET_SCORE = _env_float("VISIONAI_CAPTURE_RESET_SCORE", 55.0)
MAX_DP_STD_MM = _env_float("VISIONAI_MAX_DP_STD_MM", 1.1)
MIN_STABLE_FRAMES = int(_env_float("VISIONAI_MIN_STABLE_FRAMES", 4))
MIN_STABLE_SECONDS = _env_float("VISIONAI_MIN_STABLE_SECONDS", 0.55)
IRIS_PX_AT_TARGET_DISTANCE = _env_float("VISIONAI_IRIS_PX_AT_40CM", 0.0)
CAPTURED_RESET_SECONDS = _env_float("VISIONAI_CAPTURED_RESET_SECONDS", 3.0)

# -----------------------------
# CONFIG MEDIAPIPE
# -----------------------------
options = vision.FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path="face_landmarker.task"),
    running_mode=vision.RunningMode.VIDEO,
    num_faces=1,
    output_face_blendshapes=False,
    output_facial_transformation_matrixes=False
)

detector = vision.FaceLandmarker.create_from_options(options)

# -----------------------------
# ESTADO GLOBAL IA
# -----------------------------
escala_suave = None

historico_dp = []
historico_dnp_e = []
historico_dnp_d = []
capturado = False
medicao_final = None
tempo_ok_inicio = None

dados_medicao = {
    "dp": 0,
    "dnp_e": 0,
    "dnp_d": 0,
    "score": 0,
    "status": "Iniciando...",
    "instrucao": "Posicione seu rosto",
    "confiavel": False,
    "distancia_cm": None,
    "iris_px": None,
    "yaw": None,
    "pitch": None,
    "roll": None,
    "centro_face": None,
    "centro_face_offset": None,
    "score_geometrico": None,
    "ambiente_score": None,
    "brilho": None,
    "contraste": None,
    "nitidez": None,
}

# -----------------------------
# OLHOS (validação real)
# -----------------------------
olho_esq = [33, 160, 158, 133, 153, 144]
olho_dir = [362, 385, 387, 263, 373, 380]

def olho_aberto(landmarks, indices, w, h):
    pts = [(landmarks[i].x * w, landmarks[i].y * h) for i in indices]
    vertical_1 = np.linalg.norm(np.array(pts[1]) - np.array(pts[5]))
    vertical_2 = np.linalg.norm(np.array(pts[2]) - np.array(pts[4]))
    horizontal = np.linalg.norm(np.array(pts[0]) - np.array(pts[3]))

    if horizontal <= 0:
        return False

    abertura_px = (vertical_1 + vertical_2) / 2
    abertura_relativa = abertura_px / horizontal
    minimo_px = max(2.0, h * 0.0035)

    return abertura_px >= minimo_px or abertura_relativa >= 0.045

# -----------------------------
# SUAVIZAÇÃO
# -----------------------------
smooth = {"lx": None, "ly": None, "rx": None, "ry": None, "nx": None, "ny": None, "mx": None}

def suavizar(a, b):
    if a is None:
        return b
    movimento = abs(b - a)
    alpha = 0.4 if movimento > 10 else 0.8
    return int(alpha * a + (1 - alpha) * b)

# -----------------------------
# RESET MEDIÇÃO (🔥 AQUI)
# -----------------------------
def resetar_medicao():
    global historico_dp, historico_dnp_e, historico_dnp_d
    global capturado, medicao_final, tempo_ok_inicio, escala_suave

    historico_dp = []
    historico_dnp_e = []
    historico_dnp_d = []
    capturado = False
    medicao_final = None
    tempo_ok_inicio = None
    escala_suave = None

    for chave in smooth:
        smooth[chave] = None

    if hasattr(processar_frame, "tempo_reset"):
        processar_frame.tempo_reset = None

    dados_medicao.update({
        "dp": 0,
        "dnp_e": 0,
        "dnp_d": 0,
        "score": 0,
        "status": "Medindo",
        "instrucao": "Posicione seu rosto",
        "capturado": False,
        "confiavel": False,
        "distancia_cm": None,
        "iris_px": None,
        "yaw": None,
        "pitch": None,
        "roll": None,
        "centro_face": None,
        "centro_face_offset": None,
        "score_geometrico": None,
        "ambiente_score": None,
        "brilho": None,
        "contraste": None,
        "nitidez": None,
        "validacao": {},
        "historico": [],
    })


# -----------------------------
# ÍRIS
# -----------------------------
def calcular_diametro_iris(landmarks, w, h):
    pontos = [468, 469, 470, 471, 472]
    coords = np.array([[landmarks[i].x * w, landmarks[i].y * h] for i in pontos])
    centro = np.mean(coords, axis=0)
    raio = np.mean([np.linalg.norm(p - centro) for p in coords])
    return raio * 2

def centro_iris(landmarks, indices, w, h):
    coords = np.array([[landmarks[i].x * w, landmarks[i].y * h] for i in indices])
    centro = cv2.fitEllipse(coords.astype(np.int32))[0]
    return int(centro[0]), int(centro[1])


def limitar(valor, minimo, maximo):
    return max(minimo, min(maximo, valor))


def score_por_faixa(valor, minimo, ideal_min, ideal_max, maximo):
    if valor < minimo or valor > maximo:
        return 0
    if ideal_min <= valor <= ideal_max:
        return 100
    if valor < ideal_min:
        return round(((valor - minimo) / max(ideal_min - minimo, 1)) * 100, 1)
    return round(((maximo - valor) / max(maximo - ideal_max, 1)) * 100, 1)


def avaliar_ambiente(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    brilho = float(np.mean(gray))
    contraste = float(np.std(gray))
    nitidez = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    brilho_score = score_por_faixa(brilho, 45, 85, 190, 235)
    contraste_score = score_por_faixa(contraste, 18, 35, 90, 125)
    nitidez_score = score_por_faixa(nitidez, 20, 80, 900, 1600)
    ambiente_score = (brilho_score + contraste_score + nitidez_score) / 3

    return {
        "brilho": round(brilho, 1),
        "contraste": round(contraste, 1),
        "nitidez": round(nitidez, 1),
        "ambiente_score": round(ambiente_score, 1),
    }

# -----------------------------
# PROCESSAMENTO PRINCIPAL
# -----------------------------
def processar_frame(frame):
    global escala_suave, historico_dp, historico_dnp_e, historico_dnp_d
    global capturado, medicao_final, dados_medicao
    global tempo_ok_inicio

    h, w = frame.shape[:2]

    # -----------------------------
    # CORREÇÃO DE DISTORÇÃO (ESSENCIAL)
    # -----------------------------
    # timestamp
    frame_id = getattr(processar_frame, "frame_id", 0) + 1
    processar_frame.frame_id = frame_id
    ultimo_timestamp = getattr(processar_frame, "ultimo_timestamp", 0)
    timestamp = max(int(time.time() * 1000), ultimo_timestamp + 1)
    processar_frame.ultimo_timestamp = timestamp

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    ambiente = avaliar_ambiente(frame)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = detector.detect_for_video(mp_image, timestamp)

    if not result.face_landmarks:
        resetar_medicao()  # 🔥 AQUI
        dados_medicao["score"] = 0
        dados_medicao["status"] = "Medindo"
        dados_medicao["instrucao"] = "Posicione seu rosto"
        dados_medicao["iris_px"] = None
        dados_medicao.update(ambiente)
        return frame

    lm = result.face_landmarks[0]

    # -----------------------------
    # LANDMARKS
    # -----------------------------
    iris_left = [468, 469, 470, 471, 472]
    iris_right = [473, 474, 475, 476, 477]

    lx, ly = centro_iris(lm, iris_left, w, h)
    rx, ry = centro_iris(lm, iris_right, w, h)

    # =========================
    # 🔥 VALIDAÇÃO DOS OLHOS (ANTI-ERRO)
    # =========================
    if lx <= 0 or rx <= 0:
        dados_medicao["score"] = 0
        dados_medicao["confiavel"] = False
        return frame

    if abs(lx - rx) < 10:
        dados_medicao["score"] = 0
        dados_medicao["confiavel"] = False
        return frame

    nx, ny = int(lm[1].x * w), int(lm[1].y * h)
    mx = int(lm[168].x * w) if len(lm) > 168 else nx

    # -----------------------------
    # SUAVIZAÇÃO
    # -----------------------------
    smooth["lx"] = suavizar(smooth["lx"], lx)
    smooth["ly"] = suavizar(smooth["ly"], ly)
    smooth["rx"] = suavizar(smooth["rx"], rx)
    smooth["ry"] = suavizar(smooth["ry"], ry)
    smooth["nx"] = suavizar(smooth["nx"], nx)
    smooth["ny"] = suavizar(smooth["ny"], ny)
    smooth["mx"] = suavizar(smooth["mx"], mx)

    lx, ly = smooth["lx"], smooth["ly"]
    rx, ry = smooth["rx"], smooth["ry"]
    nx, ny = smooth["nx"], smooth["ny"]
    mx = smooth["mx"]

    # -----------------------------
    # ÂNGULO
    # -----------------------------
    angulo = np.degrees(np.arctan2(ry - ly, rx - lx))
    eye_mid_x = (lx + rx) / 2
    eye_mid_y = (ly + ry) / 2
    dist_olhos_pose = max(1.0, np.linalg.norm([rx - lx, ry - ly]))
    face_height = max(1.0, abs((lm[152].y * h) - (lm[10].y * h))) if len(lm) > 152 else max(1.0, h * 0.45)
    yaw = np.degrees(np.arctan2(nx - eye_mid_x, dist_olhos_pose))
    pitch = (((ny - eye_mid_y) / face_height) - 0.18) * 90

    # -----------------------------
    # ÍRIS
    # -----------------------------
    iris_px = calcular_diametro_iris(lm, w, h)

    if iris_px < 5:
        resetar_medicao()  # 🔥 evita lixo no histórico
        dados_medicao["score"] = 0
        dados_medicao["status"] = "Medindo"
        dados_medicao["instrucao"] = "Aproxime o rosto"
        dados_medicao["iris_px"] = round(float(iris_px), 2)
        dados_medicao.update(ambiente)
        return frame

    # -----------------------------
    # ESCALA (Plano B robusto)
    # -----------------------------
    dist_olhos_px = np.linalg.norm([rx - lx, ry - ly])

    if dist_olhos_px < 1:
        dados_medicao["score"] = 0
        dados_medicao["confiavel"] = False
        return frame

    escala_olho = IPD_REAL_MM / dist_olhos_px
    escala_iris = IRIS_REAL_MM / iris_px

    peso_iris = 0.4 if iris_px > 20 else 0.2
    escala_raw = (escala_olho * (1 - peso_iris)) + (escala_iris * peso_iris)

    if escala_suave is None:
        escala_suave = escala_raw
    else:
        escala_suave = 0.9 * escala_suave + 0.1 * escala_raw

    escala = np.clip(escala_suave * SCALE_MULTIPLIER, MIN_MM_PER_PX, MAX_MM_PER_PX)

    distancia_cm = None
    if IRIS_PX_AT_TARGET_DISTANCE > 0:
        distancia_cm = (TARGET_DISTANCE_CM * IRIS_PX_AT_TARGET_DISTANCE) / iris_px

    # -----------------------------
    # -----------------------------
    # PURKINJE (CORREÇÃO FINA REAL)
    # -----------------------------
    dx = rx - lx
    dy = 0  # força eixo horizontal

    norm = np.sqrt(dx**2 + dy**2)
    if norm == 0:
        dados_medicao["score"] = 0
        dados_medicao["confiavel"] = False
        return frame

    ux = dx / norm
    uy = dy / norm

    # vetor perpendicular
    perp_x = -uy
    perp_y = ux

    offset_mm = 0.5
    offset_px = offset_mm / escala

    # 🔥 ALINHA OS DOIS OLHOS NO MESMO EIXO
    y_medio = (ly + ry) / 2

    # 🔥 aplica correção
    lx_opt = lx - perp_x * offset_px
    ly_opt = y_medio - perp_y * offset_px

    rx_opt = rx + perp_x * offset_px
    ry_opt = y_medio + perp_y * offset_px

    # -----------------------------
    # MEDIDAS
    # -----------------------------
    dp_px = np.linalg.norm([rx_opt - lx_opt, ry_opt - ly_opt])

    centro_face = np.clip(mx, min(lx_opt, rx_opt), max(lx_opt, rx_opt))
    centro_ideal = (lx_opt + rx_opt) / 2
    centro_face_offset = ((centro_face - centro_ideal) / max(dp_px, 1)) * 100

    dnp_e_px = abs(lx_opt - centro_face)
    dnp_d_px = abs(rx_opt - centro_face)

    soma = dnp_e_px + dnp_d_px
    if soma > 0:
        fator = dp_px / soma
        dnp_e_px *= fator
        dnp_d_px *= fator

    dp_mm = dp_px * escala
    dnp_e_mm = dnp_e_px * escala
    dnp_d_mm = dnp_d_px * escala

    # -----------------------------
    # SCORE CLÍNICO
    # -----------------------------
    score = 0

    iris_ok = iris_px >= 5 and dist_olhos_px >= max(20, w * 0.05)
    olhos_ok = iris_ok or (olho_aberto(lm, olho_esq, w, h) and olho_aberto(lm, olho_dir, w, h))
    cabeca_desvio = abs(angulo)
    centro_desvio = abs(nx - w/2)
    cabeca_ok = cabeca_desvio < 6
    centro_ok = centro_desvio < w * 0.12
    if distancia_cm is not None:
        dist_ok = abs(distancia_cm - TARGET_DISTANCE_CM) <= 7
    else:
        dist_ok = 8 < iris_px < 90

    if olhos_ok:
        score += 30

    if cabeca_ok:
        score += 25
    elif cabeca_desvio < 10:
        score += 15

    if centro_ok:
        score += 25
    elif centro_desvio < w * 0.20:
        score += 15

    if dist_ok:
        score += 20

    pose_score = 100
    pose_score -= min(abs(yaw) * 3.5, 35)
    pose_score -= min(abs(pitch) * 2.5, 25)
    pose_score -= min(abs(angulo) * 4.0, 30)
    pose_score -= min(abs(centro_face_offset) * 1.2, 25)
    if distancia_cm is not None:
        pose_score -= min(abs(distancia_cm - TARGET_DISTANCE_CM) * 2.0, 25)
    pose_score = limitar(pose_score, 0, 100)
    score_geometrico = round((pose_score * 0.7) + (ambiente["ambiente_score"] * 0.3), 1)

    # -----------------------------
    # ESTABILIDADE (🔥 MELHORADO)
    # -----------------------------
    MARGEM_OK = CAPTURE_MIN_SCORE
    MARGEM_RESET = CAPTURE_RESET_SCORE

    if score >= MARGEM_OK:
        if tempo_ok_inicio is None:
            tempo_ok_inicio = time.time()

    elif score < MARGEM_RESET:
        tempo_ok_inicio = None

    # -----------------------------
    # HISTÓRICO
    # -----------------------------
    if score >= CAPTURE_MIN_SCORE and not capturado:
        historico_dp.append(dp_mm)
        historico_dnp_e.append(dnp_e_mm)
        historico_dnp_d.append(dnp_d_mm)

        if len(historico_dp) > 25:
            historico_dp.pop(0)
            historico_dnp_e.pop(0)
            historico_dnp_d.pop(0)

    # -----------------------------
    # PRECISÃO
    # -----------------------------
    confiavel = False

    if len(historico_dp) >= MIN_STABLE_FRAMES:
        desvio = np.std(historico_dp)
        if desvio < MAX_DP_STD_MM:
            confiavel = True

    # CAPTURA FINAL (AJUSTADO)
    # -----------------------------
    if (
        tempo_ok_inicio is not None and
        time.time() - tempo_ok_inicio > MIN_STABLE_SECONDS and
        confiavel and
        not capturado
    ):
        medicao_final = {
            "dp": float(np.median(historico_dp)),
            "dnp_e": float(np.median(historico_dnp_e)),
            "dnp_d": float(np.median(historico_dnp_d)),
        }
        capturado = True


    # VALIDAÇÃO CLÍNICA (CORRIGIDO)
    media, desvio, erro_max = 0, 0, 0  # inicializa sempre

    if len(historico_dp) > 6:
        historico_array = np.array(historico_dp)

        media = float(np.mean(historico_array))
        desvio = float(np.std(historico_array))
        erro_max = float(np.max(np.abs(historico_array - media)))

    aprovado = desvio < MAX_DP_STD_MM and erro_max < 1.2

    validacao = {
        "media": round(media, 2),
        "desvio": round(desvio, 3),
        "erro_max": round(erro_max, 2),
        "yaw": round(float(yaw), 2),
        "pitch": round(float(pitch), 2),
        "roll": round(float(angulo), 2),
        "centro_face": round(float(centro_face), 2),
        "centro_face_offset": round(float(centro_face_offset), 2),
        "score_geometrico": score_geometrico,
        "ambiente_score": ambiente["ambiente_score"],
        "brilho": ambiente["brilho"],
        "contraste": ambiente["contraste"],
        "nitidez": ambiente["nitidez"],
        "status": "APROVADO" if aprovado else "REPROVADO"
    }
    # =========================
    # RESET CONTROLADO (SEPARADO)
    # =========================
    if capturado:

        dp_mm = medicao_final["dp"]
        dnp_e_mm = medicao_final["dnp_e"]
        dnp_d_mm = medicao_final["dnp_d"]

        # cria variável própria do reset
        if not hasattr(processar_frame, "tempo_reset") or processar_frame.tempo_reset is None:
            processar_frame.tempo_reset = time.time()

        else:
            if time.time() - processar_frame.tempo_reset > CAPTURED_RESET_SECONDS:
                resetar_medicao()
                processar_frame.tempo_reset = None
    # -----------------------------
    # INSTRUÇÃO
    # -----------------------------
    if capturado:
        instrucao = "Medição concluída"
    else:
        if not iris_ok:
            instrucao = "Aproxime o rosto"
        elif not cabeca_ok:
            instrucao = "Endireite a cabeça"
        elif not dist_ok:
            if distancia_cm is not None:
                instrucao = f"Ajuste para {TARGET_DISTANCE_CM:.0f} cm"
            else:
                instrucao = "Mantenha 40 cm da camera"
        elif not centro_ok:
            instrucao = "Centralize o rosto"
        elif score >= 80:
            instrucao = "Fique parado..."
        else:
            instrucao = "Ajustando posição..."


    # -----------------------------
    # SALVAR
    # -----------------------------
    dados_medicao["dp"] = round(dp_mm, 1)
    dados_medicao["dnp_e"] = round(dnp_e_mm, 1)
    dados_medicao["dnp_d"] = round(dnp_d_mm, 1)
    dados_medicao["score"] = score
    dados_medicao["status"] = "OK" if capturado else "Medindo"
    dados_medicao["instrucao"] = instrucao
    dados_medicao["capturado"] = capturado
    dados_medicao["confiavel"] = confiavel or capturado
    dados_medicao["distancia_cm"] = round(distancia_cm, 1) if distancia_cm is not None else None
    dados_medicao["iris_px"] = round(float(iris_px), 2)
    dados_medicao["yaw"] = round(float(yaw), 2)
    dados_medicao["pitch"] = round(float(pitch), 2)
    dados_medicao["roll"] = round(float(angulo), 2)
    dados_medicao["centro_face"] = round(float(centro_face), 2)
    dados_medicao["centro_face_offset"] = round(float(centro_face_offset), 2)
    dados_medicao["score_geometrico"] = score_geometrico
    dados_medicao["ambiente_score"] = ambiente["ambiente_score"]
    dados_medicao["brilho"] = ambiente["brilho"]
    dados_medicao["contraste"] = ambiente["contraste"]
    dados_medicao["nitidez"] = ambiente["nitidez"]
    dados_medicao["iris_ok"] = bool(iris_ok)
    dados_medicao["olhos_ok"] = bool(olhos_ok)
    dados_medicao["cabeca_ok"] = bool(cabeca_ok)
    dados_medicao["centro_ok"] = bool(centro_ok)
    dados_medicao["dist_ok"] = bool(dist_ok)
    dados_medicao["validacao"] = validacao
    dados_medicao["historico"] = historico_dp

    return frame
