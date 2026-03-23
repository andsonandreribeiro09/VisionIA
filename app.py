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
from flask import send_file

app = Flask(__name__)

# 🔐 segurança
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))

# -----------------------------
# CONFIG INICIAL
# -----------------------------

carregar_armacao("armacao1.png")

# -----------------------------
# HELPERS
# -----------------------------

def get_db():
    conn = conectar()
    conn.row_factory = lambda cursor, row: {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
    return conn

# -----------------------------
# ROTAS
# -----------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/paciente")
def paciente():
    return render_template("paciente.html")


@app.route("/pacientes")
def pacientes():
    busca = request.args.get("busca", "")

    conn = get_db()
    cursor = conn.cursor()

    if busca:
        cursor.execute("SELECT id,nome,telefone FROM pacientes WHERE nome LIKE ?", ('%' + busca + '%',))
    else:
        cursor.execute("SELECT id,nome,telefone FROM pacientes")

    lista = cursor.fetchall()
    conn.close()

    return render_template("pacientes.html", pacientes=lista)


@app.route("/dashboard")
def dashboard():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as total FROM pacientes")
    total_pacientes = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM receitas")
    total_receitas = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM armacoes")
    total_armacoes = cursor.fetchone()["total"]

    conn.close()

    return render_template("dashboard.html",
                           total_pacientes=total_pacientes,
                           total_receitas=total_receitas,
                           total_armacoes=total_armacoes)


@app.route('/dashboard/<int:paciente_id>')
def dashboard_paciente(paciente_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM pacientes WHERE id=?", (paciente_id,))
    paciente = cursor.fetchone()

    cursor.execute("""
        SELECT * FROM pedidos
        WHERE paciente_id=?
        ORDER BY id DESC LIMIT 1
    """, (paciente_id,))
    pedido = cursor.fetchone()

    armacao = None
    if pedido:
        cursor.execute("SELECT * FROM armacoes WHERE id=?", (pedido["armacao"],))
        armacao = cursor.fetchone()

    conn.close()

    return render_template("dashboard.html",
                           paciente=paciente,
                           pedido=pedido,
                           armacao=armacao)


@app.route("/prontuario/<int:id>")
def prontuario(id):
    conn = get_db()
    cursor = conn.cursor()

    # PACIENTE
    cursor.execute("SELECT * FROM pacientes WHERE id=?", (id,))
    paciente = cursor.fetchone()

    # RECEITAS
    cursor.execute("""
    SELECT * FROM receitas
    WHERE paciente_id=?
    ORDER BY id DESC
    """, (id,))
    receitas = cursor.fetchall()

    # MEDIÇÃO (última)
    cursor.execute("""
    SELECT dp, dnp_e, dnp_d, score, data
    FROM medicoes
    WHERE paciente_id=?
    ORDER BY id DESC LIMIT 1
    """, (id,))
    medicao = cursor.fetchone()

    # ARMAÇÃO (via pedido)
    cursor.execute("""
    SELECT a.modelo, a.marca, a.tamanho, a.material
    FROM pedidos p
    JOIN armacoes a ON p.armacao = a.id
    WHERE p.paciente_id=?
    ORDER BY p.id DESC LIMIT 1
    """, (id,))
    armacao = cursor.fetchone()

    conn.close()

    return render_template("prontuario.html",
                           paciente=paciente,
                           receitas=receitas,
                           medicao=medicao,
                           armacao=armacao)


@app.route("/receita")
def receita():
    paciente_id = session.get("paciente_id")

    if not paciente_id:
        return redirect("/paciente")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT nome, idade, telefone, data_exame
    FROM pacientes
    WHERE id = ?
    """, (paciente_id,))

    paciente = cursor.fetchone()
    conn.close()

    return render_template("receita.html", paciente=paciente)


@app.route("/armacao")
def armacao():
    paciente_id = session.get("paciente_id")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT nome FROM pacientes WHERE id = ?", (paciente_id,))
    paciente = cursor.fetchone()

    cursor.execute("SELECT * FROM armacoes")
    armacoes = cursor.fetchall()

    conn.close()

    return render_template("armacao.html",
                           paciente=paciente,
                           armacoes=armacoes)


@app.route('/medicao')
def medicao():
    paciente_id = request.args.get('paciente_id')

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT nome FROM pacientes WHERE id = ?", (paciente_id,))
    paciente = cursor.fetchone()

    cursor.execute("SELECT * FROM armacoes")
    armacoes = cursor.fetchall()

    conn.close()

    return render_template("medicao.html",
                           armacoes=armacoes,
                           paciente=paciente,
                           paciente_id=paciente_id)

# -----------------------------
# PDF
# -----------------------------

@app.route("/gerar_pdf/<int:paciente_id>")
def gerar_pdf(paciente_id):

    conn = get_db()
    cursor = conn.cursor()

    # =========================
    # PACIENTE
    # =========================
    cursor.execute("""
    SELECT nome, idade, telefone, data_exame, foto
    FROM pacientes
    WHERE id=?
    """, (paciente_id,))
    paciente = cursor.fetchone()

    # =========================
    # RECEITA
    # =========================
    cursor.execute("""
    SELECT od_esf, od_cil, od_eixo,
           oe_esf, oe_cil, oe_eixo,
           adicao
    FROM receitas
    WHERE paciente_id=?
    ORDER BY id DESC LIMIT 1
    """, (paciente_id,))
    receita = cursor.fetchone()

    # =========================
    # ARMAÇÃO (CORRETO)
    # =========================
    cursor.execute("""
    SELECT a.modelo, a.marca, a.tamanho, a.material
    FROM pedidos p
    JOIN armacoes a ON p.armacao = a.id
    WHERE p.paciente_id=?
    ORDER BY p.id DESC LIMIT 1
    """, (paciente_id,))
    armacao = cursor.fetchone()

    # =========================
    # MEDIÇÃO
    # =========================
    cursor.execute("""
    SELECT dp, dnp_e, dnp_d, score, data
    FROM medicoes
    WHERE paciente_id=?
    ORDER BY id DESC LIMIT 1
    """, (paciente_id,))
    medicao = cursor.fetchone()

    conn.close()

    # =========================
    # CRIA PDF
    # =========================
    os.makedirs("static/relatorios", exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho_pdf = f"static/relatorios/relatorio_{paciente_id}_{timestamp}.pdf"

    styles = getSampleStyleSheet()
    story = []

    # =========================
    # TÍTULO
    # =========================
    story.append(Paragraph("VISION AI • RELATÓRIO OPTOMÉTRICO", styles['Title']))
    story.append(Spacer(1, 20))

    # =========================
    # PACIENTE
    # =========================
    if paciente:
        story.append(Paragraph("<b>DADOS DO PACIENTE</b>", styles['Heading2']))
        story.append(Spacer(1, 10))

        story.append(Paragraph(f"Nome: {paciente['nome']}", styles['Normal']))
        story.append(Paragraph(f"Idade: {paciente['idade']}", styles['Normal']))
        story.append(Paragraph(f"Telefone: {paciente['telefone']}", styles['Normal']))
        story.append(Paragraph(f"Data do exame: {paciente['data_exame']}", styles['Normal']))

        story.append(Spacer(1, 10))

        # FOTO
        if paciente.get("foto") and os.path.exists(paciente["foto"]):
            story.append(Image(paciente["foto"], width=150, height=150))
            story.append(Spacer(1, 20))

    # =========================
    # RECEITA
    # =========================
    if receita:
        story.append(Paragraph("<b>RECEITA OFTALMOLÓGICA</b>", styles['Heading2']))
        story.append(Spacer(1, 10))

        story.append(Paragraph(
            f"OD: ESF {receita['od_esf']} | CIL {receita['od_cil']} | EIXO {receita['od_eixo']}",
            styles['Normal']
        ))

        story.append(Paragraph(
            f"OE: ESF {receita['oe_esf']} | CIL {receita['oe_cil']} | EIXO {receita['oe_eixo']}",
            styles['Normal']
        ))

        story.append(Paragraph(f"Adição: {receita['adicao']}", styles['Normal']))

        story.append(Spacer(1, 20))

    # =========================
    # ARMAÇÃO
    # =========================
    if armacao:
        story.append(Paragraph("<b>ARMAÇÃO SELECIONADA</b>", styles['Heading2']))
        story.append(Spacer(1, 10))

        story.append(Paragraph(f"Marca: {armacao['marca']}", styles['Normal']))
        story.append(Paragraph(f"Modelo: {armacao['modelo']}", styles['Normal']))
        story.append(Paragraph(f"Tamanho: {armacao['tamanho']}", styles['Normal']))
        story.append(Paragraph(f"Material: {armacao['material']}", styles['Normal']))

        story.append(Spacer(1, 20))

    # =========================
    # MEDIÇÕES
    # =========================
    # =========================
# MEDIÇÕES
# =========================
    if medicao:
        story.append(Paragraph("<b>MEDIÇÕES BIOMÉTRICAS</b>", styles['Heading2']))
        story.append(Spacer(1, 10))

        story.append(Paragraph(f"DP: {medicao['dp']:.1f} mm", styles['Normal']))
        story.append(Paragraph(f"DNP Esquerdo: {medicao['dnp_e']:.1f} mm", styles['Normal']))
        story.append(Paragraph(f"DNP Direito: {medicao['dnp_d']:.1f} mm", styles['Normal']))
        story.append(Paragraph(f"Precisão (Score): {medicao['score']:.0f}%", styles['Normal']))
        story.append(Paragraph(f"Data da medição: {medicao['data']}", styles['Normal']))

        story.append(Spacer(1, 20))

    # =========================
    # RODAPÉ
    # =========================
    story.append(Spacer(1, 30))
    story.append(Paragraph("Gerado por Vision AI", styles['Italic']))

    # =========================
    # BUILD
    # =========================
    doc = SimpleDocTemplate(caminho_pdf, pagesize=A4)
    doc.build(story)

    return send_file(caminho_pdf, as_attachment=False)

# -----------------------------
# SALVAR
# -----------------------------

@app.route("/salvar_paciente", methods=["POST"])
def salvar_paciente():
    try:
        nome = request.form["nome"]
        idade = int(request.form["idade"])
        telefone = request.form["telefone"]
        data_exame = request.form["data_exame"]

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO pacientes (nome, idade, telefone, data_exame)
        VALUES (?,?,?,?)
        """, (nome, idade, telefone, data_exame))

        paciente_id = cursor.lastrowid

        conn.commit()
        conn.close()

        session["paciente_id"] = paciente_id

        return redirect("/receita")

    except Exception as e:
        return f"Erro ao salvar paciente: {str(e)}"


@app.route("/salvar_receita", methods=["POST"])
def salvar_receita():
    paciente_id = session.get("paciente_id")

    if not paciente_id:
        return redirect("/paciente")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO receitas (
        paciente_id,
        od_esf, od_cil, od_eixo,
        oe_esf, oe_cil, oe_eixo,
        adicao
    )
    VALUES (?,?,?,?,?,?,?,?)
    """, (
        paciente_id,
        request.form["od_esf"],
        request.form["od_cil"],
        request.form["od_eixo"],
        request.form["oe_esf"],
        request.form["oe_cil"],
        request.form["oe_eixo"],
        request.form["adicao"]
    ))

    conn.commit()
    conn.close()

    return redirect(f"/medicao?paciente_id={paciente_id}")

# -----------------------------
# VIDEO STREAM
# -----------------------------

def gerar_frames():
    camera = cv2.VideoCapture(0)

    try:
        while True:
            success, frame = camera.read()

            if not success:
                break

            frame = processar_frame(frame)

            _, buffer = cv2.imencode(".jpg", frame)
            frame_bytes = buffer.tobytes()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    finally:
        camera.release()


@app.route("/video")
def video():
    return Response(gerar_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# -----------------------------
# API
# -----------------------------

@app.route("/salvar_medicao", methods=["POST"])
def salvar_medicao():
    dados = request.get_json()

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO medicoes (paciente_id, dp, dnp_e, dnp_d, score, data)
    VALUES (?, ?, ?, ?, ?, datetime('now'))
    """, (
        dados["paciente_id"],
        dados["dp"],
        dados["dnp_e"],
        dados["dnp_d"],
        dados["score"]
    ))

    conn.commit()
    conn.close()

    return {"status": "ok"}


@app.route("/salvar_foto", methods=["POST"])
def salvar_foto():
    import base64

    dados = request.json
    paciente_id = dados["paciente_id"]
    imagem = dados["imagem"]

    img_data = base64.b64decode(imagem.split(",")[1])

    caminho = f"static/fotos/paciente_{paciente_id}.jpg"

    os.makedirs("static/fotos", exist_ok=True)

    with open(caminho, "wb") as f:
        f.write(img_data)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("UPDATE pacientes SET foto=? WHERE id=?",
                   (caminho, paciente_id))

    conn.commit()
    conn.close()

    return {"status": "ok"}


@app.route("/process-frame", methods=["POST"])
def process_frame():
    import numpy as np

    data = request.json["image"]

    img_data = base64.b64decode(data.split(",")[1])
    np_arr = np.frombuffer(img_data, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    frame = processar_frame(frame)

    _, buffer = cv2.imencode(".jpg", frame)
    img_base64 = base64.b64encode(buffer).decode("utf-8")

    return jsonify({"image": img_base64})

# -----------------------------
# START
# -----------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)