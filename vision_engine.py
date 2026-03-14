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
# VARIÁVEIS
# -----------------------------

armacao = None

SMOOTH = 0.7
smooth_lx = None
smooth_rx = None
smooth_nx = None


# -----------------------------
# POSE 3D
# -----------------------------

def calcular_pose_3d(landmarks,w,h):

    image_points = np.array([
        (landmarks[1].x*w,landmarks[1].y*h),
        (landmarks[199].x*w,landmarks[199].y*h),
        (landmarks[33].x*w,landmarks[33].y*h),
        (landmarks[263].x*w,landmarks[263].y*h),
        (landmarks[61].x*w,landmarks[61].y*h),
        (landmarks[291].x*w,landmarks[291].y*h)
    ],dtype="double")

    model_points = np.array([
        (0.0,0.0,0.0),
        (0.0,-330.0,-65.0),
        (-225.0,170.0,-135.0),
        (225.0,170.0,-135.0),
        (-150.0,-150.0,-125.0),
        (150.0,-150.0,-125.0)
    ])

    focal_length = w
    center = (w/2,h/2)

    camera_matrix = np.array([
        [focal_length,0,center[0]],
        [0,focal_length,center[1]],
        [0,0,1]
    ],dtype="double")

    dist_coeffs = np.zeros((4,1))

    success,rotation_vector,translation_vector = cv2.solvePnP(
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

    return pitch,yaw,roll


# -----------------------------
# CARREGAR ARMAÇÃO
# -----------------------------

def carregar_armacao(nome):

    global armacao

    caminho = os.path.join("static","armacoes",nome)

    img = cv2.imread(caminho,cv2.IMREAD_UNCHANGED)

    if img is None:
        return

    if img.shape[2] == 4:
        armacao = img
        return

    gray = cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray,(7,7),0)

    _,mask = cv2.threshold(blur,230,255,cv2.THRESH_BINARY_INV)

    b,g,r = cv2.split(img)

    armacao = cv2.merge([b,g,r,mask])


# -----------------------------
# OVERLAY ARMAÇÃO
# -----------------------------

def overlay(frame,overlay_img,x,y,w,h,angle):

    if overlay_img is None:
        return frame

    h_frame,w_frame = frame.shape[:2]

    x1=max(0,x)
    y1=max(0,y)

    x2=min(w_frame,x+w)
    y2=min(h_frame,y+h)

    w=x2-x1
    h=y2-y1

    if w<=0 or h<=0:
        return frame

    overlay=cv2.resize(overlay_img,(w,h))

    center=(w//2,h//2)

    rot=cv2.getRotationMatrix2D(center,-angle,1)

    overlay=cv2.warpAffine(
        overlay,
        rot,
        (w,h),
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0,0,0,0)
    )

    overlay_rgb=overlay[:,:,:3]
    alpha=overlay[:,:,3]/255.0

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
        return frame

    landmarks = result.face_landmarks[0]

    pitch,yaw,roll = calcular_pose_3d(landmarks,w_frame,h_frame)


# -----------------------------
# ESTABILIDADE
# -----------------------------

    estabilidade = 100 - (abs(yaw)*2 + abs(pitch)*1.5 + abs(roll)*2)
    estabilidade = max(0,min(100,estabilidade))


# -----------------------------
# SCANNER FACIAL
# -----------------------------

    # -----------------------------
# SCANNER OVAL (ESTILO GOV.BR)
# -----------------------------

    cx=int(w_frame/2)
    cy=int(h_frame/2)

    oval_w=int(w_frame*0.35)
    oval_h=int(h_frame*0.45)

    cor=(0,255,0) if estabilidade>80 else (0,0,255)

    cv2.ellipse(frame,(cx,cy),(oval_w,oval_h),0,0,360,cor,2)


# -----------------------------
# LANDMARKS IMPORTANTES
# -----------------------------

    olho_esq = landmarks[33]
    olho_dir = landmarks[263]

    iris_esq = landmarks[468]
    iris_dir = landmarks[473]

    temp_esq = landmarks[127]
    temp_dir = landmarks[356]

    nariz = landmarks[1]


    x1=int(olho_esq.x*w_frame)
    y1=int(olho_esq.y*h_frame)

    x2=int(olho_dir.x*w_frame)
    y2=int(olho_dir.y*h_frame)

    xi1=int(iris_esq.x*w_frame)
    yi1=int(iris_esq.y*h_frame)

    xi2=int(iris_dir.x*w_frame)
    yi2=int(iris_dir.y*h_frame)

    xt1=int(temp_esq.x*w_frame)
    xt2=int(temp_dir.x*w_frame)

    nx=int(nariz.x*w_frame)
    ny=int(nariz.y*h_frame)


# -----------------------------
# SUAVIZAÇÃO
# -----------------------------

    if smooth_lx is None:

        smooth_lx=xi1
        smooth_rx=xi2
        smooth_nx=nx

    smooth_lx=int(SMOOTH*smooth_lx+(1-SMOOTH)*xi1)
    smooth_rx=int(SMOOTH*smooth_rx+(1-SMOOTH)*xi2)
    smooth_nx=int(SMOOTH*smooth_nx+(1-SMOOTH)*nx)


# -----------------------------
# ESCALA
# -----------------------------

    iris_pixels = math.dist((xi1,yi1),(x1,y1))

    if iris_pixels < 1:
        iris_pixels = 1

    escala_mm = 11.7/(iris_pixels*2)


# -----------------------------
# MEDIÇÕES
# -----------------------------

    dp_pixels = math.dist((smooth_lx,yi1),(smooth_rx,yi2))

    dnp_esq_pixels = math.dist((smooth_lx,yi1),(smooth_nx,ny))
    dnp_dir_pixels = math.dist((smooth_rx,yi2),(smooth_nx,ny))

    dp_mm = dp_pixels * escala_mm
    dnp_esq_mm = dnp_esq_pixels * escala_mm
    dnp_dir_mm = dnp_dir_pixels * escala_mm


# -----------------------------
# ROSTO
# -----------------------------

    face_pixels = abs(xt2-xt1)

    face_width_mm = face_pixels * escala_mm

    armacao_ideal = face_width_mm - 8

    recomendacao = round(armacao_ideal)


# -----------------------------
# FORMATO ROSTO
# -----------------------------

    altura_rosto = abs(landmarks[152].y*h_frame - landmarks[10].y*h_frame)

    ratio = altura_rosto / face_pixels

    if ratio > 1.45:
        formato="Oval"
    elif ratio > 1.30:
        formato="Retangular"
    elif ratio > 1.15:
        formato="Redondo"
    else:
        formato="Quadrado"


# -----------------------------
# ARMAÇÃO
# -----------------------------

    largura=int(face_pixels*1.2)

    if armacao is not None:

        proporcao=armacao.shape[0]/armacao.shape[1]

        altura=int(largura*proporcao)

        x=int((xt1+xt2)/2-largura/2)

        y=y1-int(altura*0.5)

        frame=overlay(frame,armacao,x,y,largura,altura,roll)


# -----------------------------
# FRAME FINAL (DASHBOARD)
# -----------------------------

    panel_width=280

    frame_final=np.zeros((h_frame,w_frame+panel_width,3),dtype=np.uint8)

    frame_final[:,0:w_frame]=frame


# -----------------------------
# DASHBOARD
# -----------------------------

    panel_x=w_frame+10
    linha=60

    cv2.putText(frame_final,"VisionAI",(panel_x,linha),
    cv2.FONT_HERSHEY_SIMPLEX,0.8,(0,255,255),2)

    linha+=40

    cv2.putText(frame_final,f"DP: {dp_mm:.1f} mm",(panel_x,linha),
    cv2.FONT_HERSHEY_SIMPLEX,0.6,(0,255,0),2)

    linha+=30

    cv2.putText(frame_final,f"DNP E: {dnp_esq_mm:.1f}",(panel_x,linha),
    cv2.FONT_HERSHEY_SIMPLEX,0.6,(255,255,0),2)

    linha+=30

    cv2.putText(frame_final,f"DNP D: {dnp_dir_mm:.1f}",(panel_x,linha),
    cv2.FONT_HERSHEY_SIMPLEX,0.6,(255,255,0),2)

    linha+=40

    cv2.putText(frame_final,f"Rosto: {face_width_mm:.1f} mm",(panel_x,linha),
    cv2.FONT_HERSHEY_SIMPLEX,0.6,(0,255,255),2)

    linha+=30

    cv2.putText(frame_final,f"Armacao: {recomendacao} mm",(panel_x,linha),
    cv2.FONT_HERSHEY_SIMPLEX,0.6,(255,200,0),2)

    linha+=30

    cv2.putText(frame_final,f"Formato: {formato}",(panel_x,linha),
    cv2.FONT_HERSHEY_SIMPLEX,0.6,(255,150,0),2)


# -----------------------------
# BARRA ESTABILIDADE
# -----------------------------

    bar_x=panel_x
    bar_y=linha+50
    bar_w=200
    bar_h=12

    cv2.rectangle(frame_final,(bar_x,bar_y),(bar_x+bar_w,bar_y+bar_h),(80,80,80),-1)

    fill=int((estabilidade/100)*bar_w)

    cv2.rectangle(frame_final,(bar_x,bar_y),(bar_x+fill,bar_y+bar_h),(0,255,0),-1)

    cv2.putText(frame_final,f"Estabilidade {estabilidade:.0f}%",
    (bar_x,bar_y-5),
    cv2.FONT_HERSHEY_SIMPLEX,
    0.5,
    (0,255,0),
    1)

    return frame_final