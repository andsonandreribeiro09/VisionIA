import cv2
import mediapipe as mp
import numpy as np
import math
import os
import time

from mediapipe.tasks.python import vision
from mediapipe.tasks.python import BaseOptions


# -----------------------------
# CONFIGURAÇÃO MEDIAPIPE
# -----------------------------

options = vision.FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path="face_landmarker.task"),
    running_mode=vision.RunningMode.VIDEO,
    num_faces=1
)

detector = vision.FaceLandmarker.create_from_options(options)


# -----------------------------
# VARIÁVEIS GLOBAIS
# -----------------------------

armacao = None

SMOOTH = 0.7
smooth_lx = None
smooth_rx = None
smooth_nx = None


# -----------------------------
# FUNÇÃO POSE 3D
# -----------------------------

def calcular_pose_3d(landmarks, w, h):

    image_points = np.array([

        (landmarks[1].x * w, landmarks[1].y * h),      # nariz
        (landmarks[199].x * w, landmarks[199].y * h),  # queixo
        (landmarks[33].x * w, landmarks[33].y * h),    # olho esquerdo
        (landmarks[263].x * w, landmarks[263].y * h),  # olho direito
        (landmarks[61].x * w, landmarks[61].y * h),    # boca esquerda
        (landmarks[291].x * w, landmarks[291].y * h)   # boca direita

    ], dtype="double")


    model_points = np.array([

        (0.0, 0.0, 0.0),        # nariz
        (0.0, -330.0, -65.0),   # queixo
        (-225.0, 170.0, -135.0),
        (225.0, 170.0, -135.0),
        (-150.0, -150.0, -125.0),
        (150.0, -150.0, -125.0)

    ])


    focal_length = w
    center = (w/2, h/2)

    camera_matrix = np.array(
        [[focal_length,0,center[0]],
         [0,focal_length,center[1]],
         [0,0,1]], dtype="double"
    )

    dist_coeffs = np.zeros((4,1))


    success, rotation_vector, translation_vector = cv2.solvePnP(
        model_points,
        image_points,
        camera_matrix,
        dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE
    )


    rmat,_ = cv2.Rodrigues(rotation_vector)

    angles,_,_,_,_,_ = cv2.RQDecomp3x3(rmat)

    pitch = angles[0]
    yaw = angles[1]
    roll = angles[2]

    return pitch, yaw, roll


# -----------------------------
# CARREGAR ARMAÇÃO
# -----------------------------

def carregar_armacao(nome):

    global armacao

    caminho = os.path.join("static", "armacoes", nome)

    print(f"\nCarregando armação: {caminho}")

    img = cv2.imread(caminho, cv2.IMREAD_UNCHANGED)

    if img is None:
        print("Erro ao carregar armação")
        return

    if img.shape[2] == 4:
        armacao = img
        return

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray,(7,7),0)

    _, mask = cv2.threshold(blur,230,255,cv2.THRESH_BINARY_INV)

    kernel = np.ones((5,5),np.uint8)

    mask = cv2.morphologyEx(mask,cv2.MORPH_CLOSE,kernel)
    mask = cv2.morphologyEx(mask,cv2.MORPH_OPEN,kernel)

    mask = cv2.GaussianBlur(mask,(5,5),0)

    b,g,r = cv2.split(img)

    armacao = cv2.merge([b,g,r,mask])

    print("Armação preparada com transparência")


# -----------------------------
# OVERLAY SEGURO
# -----------------------------

def overlay(frame, overlay_img, x, y, w, h, angle):

    if overlay_img is None:
        return frame

    h_frame, w_frame = frame.shape[:2]

    if x >= w_frame or y >= h_frame or x + w <= 0 or y + h <= 0:
        return frame

    x1 = max(0,x)
    y1 = max(0,y)

    x2 = min(w_frame,x+w)
    y2 = min(h_frame,y+h)

    w = x2-x1
    h = y2-y1

    if w <= 0 or h <= 0:
        return frame

    overlay = cv2.resize(overlay_img,(w,h),interpolation=cv2.INTER_AREA)

    center = (w//2,h//2)

    rot = cv2.getRotationMatrix2D(center,-angle,1)

    overlay = cv2.warpAffine(
        overlay,
        rot,
        (w,h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0,0,0,0)
    )

    if overlay.shape[2] == 4:

        overlay_rgb = overlay[:,:,:3]
        alpha = overlay[:,:,3] / 255.0

        for c in range(3):

            frame[y1:y2,x1:x2,c] = (
                alpha * overlay_rgb[:,:,c] +
                (1-alpha) * frame[y1:y2,x1:x2,c]
            )

    return frame


# -----------------------------
# PROCESSAR FRAME
# -----------------------------

def processar_frame(frame):

    global armacao
    global smooth_lx,smooth_rx,smooth_nx

    h_frame,w_frame,_ = frame.shape

    rgb = cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)

    mp_image = mp.Image(
        image_format=mp.ImageFormat.SRGB,
        data=rgb
    )

    timestamp = int(time.time()*1000)

    result = detector.detect_for_video(mp_image,timestamp)

    if not result.face_landmarks:

        cv2.putText(frame,"Nenhum rosto detectado",(30,50),
        cv2.FONT_HERSHEY_SIMPLEX,1,(0,0,255),2)

        return frame


    landmarks = result.face_landmarks[0]


# -----------------------------
# POSE 3D
# -----------------------------

    pitch, yaw, roll = calcular_pose_3d(landmarks, w_frame, h_frame)


# -----------------------------
# PONTOS IMPORTANTES
# -----------------------------

    olho_esq = landmarks[33]
    olho_dir = landmarks[263]

    iris_esq = landmarks[468]
    iris_dir = landmarks[473]

    temp_esq = landmarks[127]
    temp_dir = landmarks[356]

    nariz = landmarks[1]


    x1 = int(olho_esq.x * w_frame)
    y1 = int(olho_esq.y * h_frame)

    x2 = int(olho_dir.x * w_frame)
    y2 = int(olho_dir.y * h_frame)

    xi1 = int(iris_esq.x * w_frame)
    yi1 = int(iris_esq.y * h_frame)

    xi2 = int(iris_dir.x * w_frame)
    yi2 = int(iris_dir.y * h_frame)

    xt1 = int(temp_esq.x * w_frame)
    xt2 = int(temp_dir.x * w_frame)

    nx = int(nariz.x * w_frame)
    ny = int(nariz.y * h_frame)


# -----------------------------
# SUAVIZAÇÃO
# -----------------------------

    if smooth_lx is None:

        smooth_lx = xi1
        smooth_rx = xi2
        smooth_nx = nx

    smooth_lx = int(SMOOTH*smooth_lx + (1-SMOOTH)*xi1)
    smooth_rx = int(SMOOTH*smooth_rx + (1-SMOOTH)*xi2)
    smooth_nx = int(SMOOTH*smooth_nx + (1-SMOOTH)*nx)


# -----------------------------
# CALIBRAÇÃO DA ESCALA (ÍRIS)
# -----------------------------

    iris_pixels = math.dist((xi1,yi1),(x1,y1))

    if iris_pixels < 1:
        iris_pixels = 1

    escala_mm = 11.7 / (iris_pixels * 2)


# -----------------------------
# MEDIÇÕES ÓPTICAS
# -----------------------------

    dp_pixels = math.dist((smooth_lx,yi1),(smooth_rx,yi2))

    dnp_esq_pixels = math.dist((smooth_lx,yi1),(smooth_nx,ny))
    dnp_dir_pixels = math.dist((smooth_rx,yi2),(smooth_nx,ny))

    dp_mm = dp_pixels * escala_mm
    dnp_esq_mm = dnp_esq_pixels * escala_mm
    dnp_dir_mm = dnp_dir_pixels * escala_mm


# -----------------------------
# LARGURA DO ROSTO
# -----------------------------

    face_pixels = abs(xt2 - xt1)

    face_width_mm = face_pixels * escala_mm

    armacao_ideal = face_width_mm - 8


# -----------------------------
# DIMENSÃO DA ARMAÇÃO
# -----------------------------

    largura = int(face_pixels * 1.2)

    escala = 1 - abs(yaw) * 0.01

    largura = int(largura * escala)

    if armacao is not None:

        proporcao = armacao.shape[0] / armacao.shape[1]

        altura = int(largura * proporcao)

    else:

        altura = int(largura * 0.4)


# -----------------------------
# POSIÇÃO
# -----------------------------

    x = int((xt1 + xt2)/2 - largura/2)

    y = y1 - int(altura*0.50)


# -----------------------------
# DESENHAR ARMAÇÃO
# -----------------------------

    if armacao is not None and largura > 10:

        frame = overlay(frame,armacao,x,y,largura,altura,roll)


# -----------------------------
# TEXTO NA TELA
# -----------------------------

    cv2.putText(frame,f"DP: {dp_mm:.1f} mm",(30,50),
    cv2.FONT_HERSHEY_SIMPLEX,0.8,(0,255,0),2)

    cv2.putText(frame,f"DNP E: {dnp_esq_mm:.1f} mm",(30,80),
    cv2.FONT_HERSHEY_SIMPLEX,0.6,(255,255,0),2)

    cv2.putText(frame,f"DNP D: {dnp_dir_mm:.1f} mm",(30,110),
    cv2.FONT_HERSHEY_SIMPLEX,0.6,(255,255,0),2)

    cv2.putText(frame,f"Rosto: {face_width_mm:.1f} mm",(30,140),
    cv2.FONT_HERSHEY_SIMPLEX,0.6,(0,255,255),2)

    cv2.putText(frame,f"Armacao ideal: {armacao_ideal:.1f} mm",(30,170),
    cv2.FONT_HERSHEY_SIMPLEX,0.6,(0,255,255),2)

    cv2.putText(frame,f"Yaw: {yaw:.1f}",(30,200),
    cv2.FONT_HERSHEY_SIMPLEX,0.6,(255,255,255),2)

    cv2.putText(frame,f"Pitch: {pitch:.1f}",(30,230),
    cv2.FONT_HERSHEY_SIMPLEX,0.6,(255,255,255),2)

    cv2.putText(frame,f"Roll: {roll:.1f}",(30,260),
    cv2.FONT_HERSHEY_SIMPLEX,0.6,(255,255,255),2)


# -----------------------------
# DEBUG LANDMARKS
# -----------------------------

    for lm in landmarks:

        px = int(lm.x*w_frame)
        py = int(lm.y*h_frame)

        cv2.circle(frame,(px,py),1,(0,255,0),-1)


    cv2.circle(frame,(smooth_lx,yi1),5,(255,0,0),-1)
    cv2.circle(frame,(smooth_rx,yi2),5,(255,0,0),-1)
    cv2.circle(frame,(smooth_nx,ny),5,(255,0,255),-1)

    return frame