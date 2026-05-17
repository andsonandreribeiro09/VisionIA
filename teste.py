import torch
import torch.nn as nn
import cv2
import os
from torchvision import transforms
from torchvision.models import mobilenet_v3_small

# =========================
# CONFIG
# =========================
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
DEBUG = True

# =========================
# MODELO
# =========================
model = mobilenet_v3_small(weights=None)
model.classifier[3] = nn.Linear(model.classifier[3].in_features, 1)

model.load_state_dict(torch.load("oculos_model_forte.pth", map_location=device))
model.to(device)
model.eval()

print("✅ Modelo carregado!")

# =========================
# TRANSFORM
# =========================
transform = transforms.Compose([
    transforms.ToPILImage(),
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
])

# =========================
# DETECTOR DE ROSTO
# =========================
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

# =========================
# LABELS
# =========================
labels = ["Sem Oculos", "Com armacao"]

# =========================
# PASTA
# =========================
os.makedirs("capturas", exist_ok=True)

# =========================
# CONTROLES
# =========================
historico = []
MAX_HIST = 5

estado_oculos = False
TH_ENTRAR = 0.75
TH_SAIR = 0.55

frames_estavel = 0
FRAMES_MIN = 5

capturado = False

# =========================
# WEBCAM
# =========================
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("❌ Erro ao abrir webcam")
    exit()

print("🚀 Rodando... pressione Q para sair")

# =========================
# LOOP
# =========================
while True:
    ret, frame = cap.read()
    if not ret:
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)

    # RESET TOTAL se não há rosto
    if len(faces) == 0:
        historico.clear()
        estado_oculos = False
        frames_estavel = 0
        capturado = False
        faces = [(0, 0, frame.shape[1], frame.shape[0])]

    for (x, y, w, h) in faces:

        # =========================
        # RECORTE
        # =========================
        margin = 30
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(frame.shape[1], x + w + margin)
        y2 = min(frame.shape[0], y + h + margin)

        face = frame[y1:y2, x1:x2]
        if face.size == 0:
            continue

        # =========================
        # REGIÃO DOS OLHOS
        # =========================
        h_face, w_face = face.shape[:2]
        y_eye1 = int(h_face * 0.25)
        y_eye2 = int(h_face * 0.55)

        eye_region = face[y_eye1:y_eye2, :]
        if eye_region.size == 0:
            continue

        # =========================
        # PREPROCESSAMENTO
        # =========================
        img_rgb = cv2.cvtColor(eye_region, cv2.COLOR_BGR2RGB)
        input_tensor = transform(img_rgb).unsqueeze(0).to(device)

        # =========================
        # PREDIÇÃO
        # =========================
        with torch.no_grad():
            output = model(input_tensor)
            prob = torch.sigmoid(output)

        conf = prob.item()

        # ignora lixo muito baixo
        if conf < 0.2:
            continue

        # =========================
        # FILTRO DE SALTO
        # =========================
        if len(historico) > 0:
            delta = abs(conf - historico[-1])
            if delta > 0.5 and conf < historico[-1]:
                if DEBUG:
                    print("⚠️ Salto ignorado:", conf)
                continue

        # =========================
        # SUAVIZAÇÃO
        # =========================
        historico.append(conf)
        if len(historico) > MAX_HIST:
            historico.pop(0)

        media_conf = sum(historico) / len(historico)

        # =========================
        # DECISÃO COM HISTERESE
        # =========================
        if not estado_oculos:
            if media_conf > TH_ENTRAR:
                estado_oculos = True
                frames_estavel = 0
        else:
            if media_conf < TH_SAIR:
                estado_oculos = False
                frames_estavel = 0
                historico.clear()  # 🔥 ESSENCIAL

        # =========================
        # ESTABILIDADE REAL
        # =========================
        if estado_oculos and conf > 0.6:
            frames_estavel += 1
        else:
            frames_estavel = 0

        pred = 1 if estado_oculos else 0
        label = f"{labels[pred]} ({media_conf*100:.1f}%)"

        if DEBUG:
            print(f"Conf: {conf:.4f} | Média: {media_conf:.4f} | Estado: {estado_oculos} | Frames: {frames_estavel}")

        # =========================
        # DESENHO
        # =========================
        color = (0,255,0) if estado_oculos else (0,0,255)

        cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
        cv2.putText(frame, label, (x, y-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

        # =========================
        # CAPTURA INTELIGENTE
        # =========================
        if (estado_oculos and 
            frames_estavel >= FRAMES_MIN and 
            media_conf > 0.75 and 
            not capturado):

            nome = f"capturas/captura_{int(media_conf*100)}.jpg"

            if cv2.imwrite(nome, frame):
                print(f"📸 CAPTURADO: {nome}")
                capturado = True
            else:
                print("❌ erro ao salvar")

        # reset captura
        if not estado_oculos:
            capturado = False

    # =========================
    # EXIBIÇÃO
    # =========================
    cv2.imshow("Vision AI", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# =========================
# FINALIZAR
# =========================
cap.release()
cv2.destroyAllWindows()