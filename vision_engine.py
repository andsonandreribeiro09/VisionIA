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

# =========================================================
# CALIBRAÇÃO DA CÂMERA
# =========================================================

camera_matrix = np.load("camera_matrix.npy")
dist_coeffs = np.load("dist_coeffs.npy")

# =========================================================
# CONFIG MEDIAPIPE
# =========================================================

detector = None

try:

    options = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(
            model_asset_path="face_landmarker.task"
        ),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=1,
        output_face_blendshapes=False,
        output_facial_transformation_matrixes=False
    )

    detector = vision.FaceLandmarker.create_from_options(options)

    print("✅ MediaPipe carregado")

except Exception as e:

    print("❌ Erro MediaPipe:")
    print(e)

    detector = None

# =========================================================
# ESTADO GLOBAL
# =========================================================

IRIS_REAL_MM = 11.7

escala_suave = None

historico_dp = []

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
    "capturado": False,
    "validacao": {},
    "historico": []
}

# =========================================================
# LANDMARKS DOS OLHOS
# =========================================================

olho_esq = [33, 160, 158, 133, 153, 144]
olho_dir = [362, 385, 387, 263, 373, 380]

# =========================================================
# SUAVIZAÇÃO
# =========================================================

smooth = {
    "lx": None,
    "ly": None,
    "rx": None,
    "ry": None,
    "nx": None,
    "ny": None
}

# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def resetar_medicao():

    global historico_dp
    global capturado
    global medicao_final
    global tempo_ok_inicio
    global escala_suave

    historico_dp = []

    capturado = False

    medicao_final = None

    tempo_ok_inicio = None

    escala_suave = None


def suavizar(a, b):

    if a is None:
        return b

    movimento = abs(b - a)

    alpha = 0.4 if movimento > 10 else 0.8

    return int(alpha * a + (1 - alpha) * b)


def olho_aberto(landmarks, indices, w, h):

    pts = [
        (landmarks[i].x * w, landmarks[i].y * h)
        for i in indices
    ]

    altura = abs(pts[1][1] - pts[5][1])

    return altura > 6


def calcular_diametro_iris(landmarks, w, h):

    pontos = [468, 469, 470, 471, 472]

    coords = np.array([
        [landmarks[i].x * w, landmarks[i].y * h]
        for i in pontos
    ])

    centro = np.mean(coords, axis=0)

    raio = np.mean([
        np.linalg.norm(p - centro)
        for p in coords
    ])

    return raio * 2


def centro_iris(landmarks, indices, w, h):

    coords = np.array([
        [landmarks[i].x * w, landmarks[i].y * h]
        for i in indices
    ])

    # EVITA ERRO fitEllipse
    if len(coords) < 5:
        return None, None

    try:

        centro = cv2.fitEllipse(
            coords.astype(np.int32)
        )[0]

        return int(centro[0]), int(centro[1])

    except:
        return None, None

# =========================================================
# PROCESSAMENTO PRINCIPAL
# =========================================================

def processar_frame(frame):

    global escala_suave
    global historico_dp
    global capturado
    global medicao_final
    global tempo_ok_inicio
    global dados_medicao

    # =====================================================
    # FALLBACK RENDER
    # =====================================================

    if detector is None:

        cv2.putText(
            frame,
            "MediaPipe indisponivel no servidor",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2
        )

        return frame

    try:

        h, w = frame.shape[:2]

        # =================================================
        # CORREÇÃO DE DISTORÇÃO
        # =================================================

        if not hasattr(processar_frame, "newcameramtx"):

            processar_frame.newcameramtx, _ = cv2.getOptimalNewCameraMatrix(
                camera_matrix,
                dist_coeffs,
                (w, h),
                0.3,
                (w, h)
            )

        frame = cv2.undistort(
            frame,
            camera_matrix,
            dist_coeffs,
            None,
            processar_frame.newcameramtx
        )

        # =================================================
        # TIMESTAMP
        # =================================================

        timestamp = int(time.time() * 1000)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=rgb
        )

        result = detector.detect_for_video(
            mp_image,
            timestamp
        )

        # =================================================
        # SEM ROSTO
        # =================================================

        if not result.face_landmarks:

            resetar_medicao()

            dados_medicao["instrucao"] = "Posicione seu rosto"

            return frame

        lm = result.face_landmarks[0]

        # =================================================
        # ÍRIS
        # =================================================

        iris_left = [468, 469, 470, 471, 472]
        iris_right = [473, 474, 475, 476, 477]

        lx, ly = centro_iris(
            lm,
            iris_left,
            w,
            h
        )

        rx, ry = centro_iris(
            lm,
            iris_right,
            w,
            h
        )

        # =================================================
        # VALIDAÇÕES
        # =================================================

        if lx is None or rx is None:
            return frame

        if lx <= 0 or rx <= 0:
            return frame

        if abs(lx - rx) < 10:
            return frame

        # =================================================
        # NARIZ
        # =================================================

        nx = int(lm[1].x * w)
        ny = int(lm[1].y * h)

        # =================================================
        # SUAVIZAÇÃO
        # =================================================

        smooth["lx"] = suavizar(smooth["lx"], lx)
        smooth["ly"] = suavizar(smooth["ly"], ly)

        smooth["rx"] = suavizar(smooth["rx"], rx)
        smooth["ry"] = suavizar(smooth["ry"], ry)

        smooth["nx"] = suavizar(smooth["nx"], nx)
        smooth["ny"] = suavizar(smooth["ny"], ny)

        lx = smooth["lx"]
        ly = smooth["ly"]

        rx = smooth["rx"]
        ry = smooth["ry"]

        nx = smooth["nx"]
        ny = smooth["ny"]

        # =================================================
        # ÂNGULO
        # =================================================

        angulo = np.degrees(
            np.arctan2(
                ry - ly,
                rx - lx
            )
        )

        # =================================================
        # DIÂMETRO ÍRIS
        # =================================================

        iris_px = calcular_diametro_iris(
            lm,
            w,
            h
        )

        if iris_px < 5:

            resetar_medicao()

            dados_medicao["instrucao"] = "Aproxime o rosto"

            return frame

        # =================================================
        # ESCALA
        # =================================================

        dist_olhos_px = np.linalg.norm([
            rx - lx,
            ry - ly
        ])

        if dist_olhos_px < 1:
            return frame

        escala_olho = 63 / dist_olhos_px

        escala_iris = IRIS_REAL_MM / iris_px

        peso_iris = 0.4 if iris_px > 20 else 0.2

        escala_raw = (
            (escala_olho * (1 - peso_iris))
            + (escala_iris * peso_iris)
        )

        if escala_suave is None:
            escala_suave = escala_raw
        else:
            escala_suave = (
                0.9 * escala_suave
                + 0.1 * escala_raw
            )

        escala = np.clip(
            escala_suave,
            0.3,
            0.6
        )

        # =================================================
        # MEDIDAS
        # =================================================

        dp_px = np.linalg.norm([
            rx - lx,
            ry - ly
        ])

        dp_mm = dp_px * escala

        dnp_e_mm = dp_mm / 2
        dnp_d_mm = dp_mm / 2

        # =================================================
        # SCORE
        # =================================================

        score = 0

        olhos_ok = (
            olho_aberto(lm, olho_esq, w, h)
            and
            olho_aberto(lm, olho_dir, w, h)
        )

        cabeca_ok = abs(angulo) < 4

        centro_ok = abs(nx - w / 2) < 40

        dist_ok = 20 < iris_px < 50

        if olhos_ok:
            score += 25

        if cabeca_ok:
            score += 25

        if centro_ok:
            score += 25

        if dist_ok:
            score += 25

        # =================================================
        # ESTABILIDADE
        # =================================================

        if score >= 85:

            if tempo_ok_inicio is None:
                tempo_ok_inicio = time.time()

        elif score < 70:

            tempo_ok_inicio = None

        # =================================================
        # HISTÓRICO
        # =================================================

        if score >= 80 and not capturado:

            historico_dp.append(dp_mm)

            if len(historico_dp) > 25:
                historico_dp.pop(0)

        # =================================================
        # PRECISÃO
        # =================================================

        confiavel = False

        if len(historico_dp) > 10:

            desvio = np.std(historico_dp)

            if desvio < 0.5:
                confiavel = True

        # =================================================
        # CAPTURA FINAL
        # =================================================

        if (
            tempo_ok_inicio is not None
            and
            time.time() - tempo_ok_inicio > 2
            and
            confiavel
            and
            not capturado
        ):

            medicao_final = np.median(historico_dp)

            capturado = True

        # =================================================
        # VALIDAÇÃO
        # =================================================

        media = 0
        desvio = 0
        erro_max = 0

        if len(historico_dp) > 6:

            historico_array = np.array(historico_dp)

            media = float(np.mean(historico_array))

            desvio = float(np.std(historico_array))

            erro_max = float(
                np.max(
                    np.abs(historico_array - media)
                )
            )

        aprovado = (
            desvio < 0.5
            and
            erro_max < 1.0
        )

        validacao = {
            "media": round(media, 2),
            "desvio": round(desvio, 3),
            "erro_max": round(erro_max, 2),
            "status": "APROVADO" if aprovado else "REPROVADO"
        }

        # =================================================
        # RESET CONTROLADO
        # =================================================

        if capturado:

            dp_mm = medicao_final

            if (
                not hasattr(processar_frame, "tempo_reset")
                or
                processar_frame.tempo_reset is None
            ):

                processar_frame.tempo_reset = time.time()

            else:

                if time.time() - processar_frame.tempo_reset > 3:

                    resetar_medicao()

                    processar_frame.tempo_reset = None

        # =================================================
        # INSTRUÇÕES
        # =================================================

        if capturado:

            instrucao = "Medição concluída"

        else:

            if not olhos_ok:
                instrucao = "Abra os olhos"

            elif not cabeca_ok:
                instrucao = "Endireite a cabeça"

            elif not dist_ok:
                instrucao = "Ajuste a distância"

            elif not centro_ok:
                instrucao = "Centralize o rosto"

            elif score >= 80:
                instrucao = "Fique parado..."

            else:
                instrucao = "Ajustando posição..."

        # =================================================
        # SALVAR DADOS
        # =================================================

        dados_medicao["dp"] = round(dp_mm, 1)

        dados_medicao["dnp_e"] = round(dnp_e_mm, 1)

        dados_medicao["dnp_d"] = round(dnp_d_mm, 1)

        dados_medicao["score"] = score

        dados_medicao["status"] = (
            "OK" if capturado else "Medindo"
        )

        dados_medicao["instrucao"] = instrucao

        dados_medicao["capturado"] = capturado

        dados_medicao["validacao"] = validacao

        dados_medicao["historico"] = historico_dp

        # =================================================
        # OVERLAY
        # =================================================

        cor = (0, 255, 0) if capturado else (0, 255, 255)

        cv2.circle(
            frame,
            (int(lx), int(ly)),
            3,
            (255, 0, 0),
            -1
        )

        cv2.circle(
            frame,
            (int(rx), int(ry)),
            3,
            (255, 0, 0),
            -1
        )

        cv2.circle(
            frame,
            (nx, ny),
            4,
            (0, 0, 255),
            -1
        )

        cv2.putText(
            frame,
            f"DP: {round(dp_mm,1)} mm",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            cor,
            2
        )

        cv2.putText(
            frame,
            instrucao,
            (20, 80),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            cor,
            2
        )

        return frame

    except Exception as e:

        print("❌ Erro no processamento:")
        print(e)

        cv2.putText(
            frame,
            "Erro no processamento",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2
        )

        return frame
