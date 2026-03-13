from flask import Flask, render_template, Response, request, redirect, jsonify
import cv2
from vision_engine import processar_frame, carregar_armacao
import base64
import os
from datetime import datetime

app = Flask(__name__)

# -----------------------------
# Webcam
# -----------------------------

camera = cv2.VideoCapture(0)

# armação padrão
carregar_armacao("armacao1.png")
# -----------------------------
# ROTAS PRINCIPAIS
# -----------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/paciente")
def paciente():
    return render_template("paciente.html")


@app.route("/receita")
def receita():
    return render_template("receita.html")


@app.route("/armacao")
def armacao():
    return render_template("armacao.html")


@app.route("/medicao")
def medicao():
    return render_template("medicao.html")


@app.route("/escolher_armacao/<nome>")
def escolher_armacao(nome):

    carregar_armacao(nome)

    return redirect("/medicao")
# -----------------------------
# SALVAR PACIENTE
# -----------------------------

@app.route("/salvar_paciente", methods=["POST"])
def salvar_paciente():

    nome = request.form.get("nome")
    idade = request.form.get("idade")
    telefone = request.form.get("telefone")

    print("\nPACIENTE CADASTRADO")
    print("Nome:", nome)
    print("Idade:", idade)
    print("Telefone:", telefone)

    return redirect("/receita")

@app.route("/salvar_foto", methods=["POST"])
def salvar_foto():

    data = request.json["imagem"]

    img_data = data.split(",")[1]

    img_bytes = base64.b64decode(img_data)

    nome = "foto_" + datetime.now().strftime("%Y%m%d%H%M%S") + ".png"

    caminho = os.path.join("static/fotos", nome)

    with open(caminho,"wb") as f:
        f.write(img_bytes)

    link = f"http://127.0.0.1:5000/static/fotos/{nome}"

    whatsapp = f"https://wa.me/?text=Veja%20seu%20novo%20óculos:%20{link}"

    return jsonify({
        "foto":link,
        "whatsapp":whatsapp
    })


# -----------------------------
# STREAM DE VIDEO
# -----------------------------

def gerar_frames():

    while True:

        success, frame = camera.read()

        if not success:
            break

        # processa IA
        frame = processar_frame(frame)

        ret, buffer = cv2.imencode(".jpg", frame)
        frame = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


@app.route("/video")
def video():

    return Response(
        gerar_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


# -----------------------------
# INICIAR SERVIDOR
# -----------------------------

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )