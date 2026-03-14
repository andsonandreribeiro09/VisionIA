from flask import Flask, render_template, Response, request, redirect, jsonify, session
import cv2
from vision_engine import processar_frame, carregar_armacao
import base64
import os
from datetime import datetime
from database import conectar
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4


app = Flask(__name__)

app.secret_key = "visionai123"

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

@app.route("/pacientes")
def pacientes():

    busca = request.args.get("busca","")

    conn = conectar()
    cursor = conn.cursor()

    if busca:
        cursor.execute(
            "SELECT id,nome,telefone FROM pacientes WHERE nome LIKE ?",
            ('%'+busca+'%',)
        )
    else:
        cursor.execute(
            "SELECT id,nome,telefone FROM pacientes"
        )

    lista = cursor.fetchall()

    conn.close()

    return render_template("pacientes.html", pacientes=lista)

@app.route("/dashboard")
def dashboard():

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM pacientes")
    total_pacientes = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM receitas")
    total_receitas = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM armacoes")
    total_armacoes = cursor.fetchone()[0]

    conn.close()

    return render_template(
        "dashboard.html",
        total_pacientes=total_pacientes,
        total_receitas=total_receitas,
        total_armacoes=total_armacoes
    )


@app.route("/prontuario/<int:id>")
def prontuario(id):

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM pacientes WHERE id=?", (id,))
    paciente = cursor.fetchone()

    cursor.execute("SELECT * FROM receitas WHERE paciente_id=?", (id,))
    receitas = cursor.fetchall()

    conn.close()

    return render_template(
        "prontuario.html",
        paciente=paciente,
        receitas=receitas
    )


@app.route("/receita")
def receita():

    paciente_id = session.get("paciente_id")

    print("Paciente ID:", paciente_id)

    if not paciente_id:
        return redirect("/paciente")

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT nome, idade, telefone, data_exame
    FROM pacientes
    WHERE id = ?
    """,(paciente_id,))

    paciente = cursor.fetchone()

    print("Paciente:", paciente)

    conn.close()

    return render_template("receita.html", paciente=paciente)

@app.route("/armacao")
def armacao():

    paciente_id = session.get("paciente_id")

    conn = conectar()
    cursor = conn.cursor()

    # buscar paciente
    cursor.execute(
        "SELECT nome FROM pacientes WHERE id = ?",
        (paciente_id,)
    )
    paciente = cursor.fetchone()

    # buscar armações
    cursor.execute(
        "SELECT * FROM armacoes"
    )
    armacoes = cursor.fetchall()

    conn.close()

    return render_template(
        "armacao.html",
        paciente=paciente,
        armacoes=armacoes
    )


@app.route("/medicao")
def medicao():
    return render_template("medicao.html")


@app.route("/gerar_pdf/<int:paciente_id>")
def gerar_pdf(paciente_id):

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT nome,idade,telefone,data_exame FROM pacientes WHERE id=?", (paciente_id,))
    paciente = cursor.fetchone()

    cursor.execute("SELECT od_esf,od_cil,od_eixo,oe_esf,oe_cil,oe_eixo FROM receitas WHERE paciente_id=?", (paciente_id,))
    receita = cursor.fetchone()

    cursor.execute("SELECT modelo,marca,tamanho,material FROM armacoes WHERE paciente_id=?", (paciente_id,))
    armacao = cursor.fetchone()

    cursor.execute("""
    SELECT dp,dnp_e,dnp_d,rosto,armacao_ideal,yaw,pitch,roll
    FROM medicoes WHERE paciente_id=?
    """, (paciente_id,))
    medicao = cursor.fetchone()

    conn.close()

    caminho_pdf = f"static/relatorio_{paciente_id}.pdf"

    styles = getSampleStyleSheet()

    story = []

    story.append(Paragraph("VISION AI • RELATÓRIO OPTOMÉTRICO", styles['Title']))
    story.append(Spacer(1,20))

    # Dados paciente

    story.append(Paragraph("1. Dados do Paciente", styles['Heading2']))
    story.append(Paragraph(f"Nome: {paciente[0]}", styles['Normal']))
    story.append(Paragraph(f"Idade: {paciente[1]}", styles['Normal']))
    story.append(Paragraph(f"Telefone: {paciente[2]}", styles['Normal']))
    story.append(Paragraph(f"Data exame: {paciente[3]}", styles['Normal']))

    story.append(Spacer(1,20))

    # Receita

    story.append(Paragraph("2. Receita", styles['Heading2']))
    story.append(Paragraph(f"OD: ESF {receita[0]}  CIL {receita[1]}  EIXO {receita[2]}", styles['Normal']))
    story.append(Paragraph(f"OE: ESF {receita[3]}  CIL {receita[4]}  EIXO {receita[5]}", styles['Normal']))

    story.append(Spacer(1,20))

    # Armação

    story.append(Paragraph("3. Armação Escolhida", styles['Heading2']))
    story.append(Paragraph(f"Marca: {armacao[1]}", styles['Normal']))
    story.append(Paragraph(f"Modelo: {armacao[0]}", styles['Normal']))
    story.append(Paragraph(f"Material: {armacao[3]}", styles['Normal']))
    story.append(Paragraph(f"Tamanho: {armacao[2]}", styles['Normal']))

    story.append(Spacer(1,20))

    # Medições

    story.append(Paragraph("4. Medições Inteligentes", styles['Heading2']))

    story.append(Paragraph(f"DP: {medicao[0]} mm", styles['Normal']))
    story.append(Paragraph(f"DNP Esquerda: {medicao[1]} mm", styles['Normal']))
    story.append(Paragraph(f"DNP Direita: {medicao[2]} mm", styles['Normal']))
    story.append(Paragraph(f"Largura do rosto: {medicao[3]} mm", styles['Normal']))
    story.append(Paragraph(f"Armação ideal: {medicao[4]} mm", styles['Normal']))
    story.append(Paragraph(f"Yaw: {medicao[5]}", styles['Normal']))
    story.append(Paragraph(f"Pitch: {medicao[6]}", styles['Normal']))
    story.append(Paragraph(f"Roll: {medicao[7]}", styles['Normal']))

    story.append(Spacer(1,20))

    # Foto

    foto_path = f"static/fotos/paciente_{paciente_id}.jpg"

    if os.path.exists(foto_path):
        story.append(Paragraph("5. Foto da medição", styles['Heading2']))
        story.append(Image(foto_path, width=400, height=300))

    doc = SimpleDocTemplate(caminho_pdf, pagesize=A4)
    doc.build(story)

    return caminho_pdf


@app.route("/escolher_armacao/<int:armacao_id>")
def escolher_armacao(armacao_id):

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT imagem FROM armacoes WHERE id=?",
        (armacao_id,)
    )

    resultado = cursor.fetchone()

    conn.close()

    if resultado:
        nome_imagem = resultado[0]
        carregar_armacao(nome_imagem)

    return redirect("/medicao")
# -----------------------------
# SALVAR PACIENTE
# -----------------------------


@app.route("/salvar_paciente", methods=["POST"])
def salvar_paciente():

    nome = request.form["nome"]
    idade = int(request.form["idade"])
    telefone = request.form["telefone"]
    data_exame = request.form["data_exame"]

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO pacientes (nome, idade, telefone, data_exame)
    VALUES (?,?,?,?)
    """,(nome, idade, telefone, data_exame))

    paciente_id = cursor.lastrowid

    conn.commit()
    conn.close()

    session["paciente_id"] = paciente_id

    return redirect("/receita")


@app.route("/salvar_receita", methods=["POST"])
def salvar_receita():

    paciente_id = session.get("paciente_id")

    od_esf = request.form["od_esf"]
    od_cil = request.form["od_cil"]
    od_eixo = request.form["od_eixo"]

    oe_esf = request.form["oe_esf"]
    oe_cil = request.form["oe_cil"]
    oe_eixo = request.form["oe_eixo"]

    adicao = request.form["adicao"]

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO receitas (
        paciente_id,
        od_esf, od_cil, od_eixo,
        oe_esf, oe_cil, oe_eixo,
        adicao
    )
    VALUES (?,?,?,?,?,?,?,?)
    """,(
        paciente_id,
        od_esf, od_cil, od_eixo,
        oe_esf, oe_cil, oe_eixo,
        adicao
    ))

    conn.commit()
    conn.close()

    return redirect("/armacao")




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