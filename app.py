# ------------------------------
# Imports da biblioteca padrão
# ------------------------------
import os
import csv
import cv2
import json
import base64
import threading
from database import conectar
from datetime import datetime
# ------------------------------
# Imports de bibliotecas externas
# ------------------------------
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from vision_engine import processar_frame, dados_medicao
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from flask import Flask, render_template, Response, request, redirect, jsonify, session, send_file



app = Flask(__name__)

# 🔐 segurança
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))
DEBUG_VISIONAI = os.getenv("VISIONAI_DEBUG", "0") == "1"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv("VISIONAI_DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
CSV_PACIENTES_MEDICOES = os.path.join(DATA_DIR, "pacientes_medicoes.csv")
CSV_LOCK = threading.Lock()
CSV_COLUNAS = [
    "paciente_id",
    "nome",
    "rg",
    "data_nascimento",
    "sexo",
    "idade",
    "telefone",
    "data_exame",
    "cadastro_em",
    "medicao_em",
    "dp",
    "dnp_e",
    "dnp_d",
    "score",
    "status_validacao",
    "validacao_json",
    "historico_json",
    "capturas_json",
    "fotos_capturadas",
    "foto_final",
]

def debug_log(*args):
    if DEBUG_VISIONAI:
        print(*args)

# -----------------------------
# CONFIG INICIAL
# -----------------------------

#carregar_armacao("Police - VPL599 - Front.png")
camera = None
# -----------------------------
# HELPERS
# -----------------------------

def get_db():
    conn = conectar()
    conn.row_factory = lambda cursor, row: {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
    return conn


def carregar_paciente(paciente_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pacientes WHERE id=?", (paciente_id,))
    paciente = cursor.fetchone()
    conn.close()
    return paciente


def ler_linhas_csv():
    if not os.path.exists(CSV_PACIENTES_MEDICOES):
        return []

    with open(CSV_PACIENTES_MEDICOES, "r", newline="", encoding="utf-8-sig") as arquivo:
        return list(csv.DictReader(arquivo))


def escrever_linhas_csv(linhas):
    with open(CSV_PACIENTES_MEDICOES, "w", newline="", encoding="utf-8-sig") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=CSV_COLUNAS, extrasaction="ignore")
        writer.writeheader()
        for linha in linhas:
            writer.writerow({coluna: linha.get(coluna, "") for coluna in CSV_COLUNAS})


def salvar_linha_csv(paciente_id, dados):
    paciente_id = str(paciente_id)

    with CSV_LOCK:
        linhas = ler_linhas_csv()
        linha_existente = None

        for linha in linhas:
            if linha.get("paciente_id") == paciente_id:
                linha_existente = linha
                break

        if linha_existente is None:
            linha_existente = {"paciente_id": paciente_id}
            linhas.append(linha_existente)

        for chave, valor in dados.items():
            if chave in CSV_COLUNAS:
                linha_existente[chave] = "" if valor is None else valor

        escrever_linhas_csv(linhas)


def registrar_paciente_no_csv(paciente):
    salvar_linha_csv(paciente["id"], {
        "paciente_id": paciente["id"],
        "nome": paciente.get("nome"),
        "rg": paciente.get("rg"),
        "data_nascimento": paciente.get("data_nascimento"),
        "sexo": paciente.get("sexo"),
        "idade": paciente.get("idade"),
        "telefone": paciente.get("telefone"),
        "data_exame": paciente.get("data_exame"),
        "cadastro_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


def registrar_medicao_no_csv(paciente_id, dados_medicao_csv):
    paciente = carregar_paciente(paciente_id)
    dados = {}

    if paciente:
        dados.update({
            "nome": paciente.get("nome"),
            "rg": paciente.get("rg"),
            "data_nascimento": paciente.get("data_nascimento"),
            "sexo": paciente.get("sexo"),
            "idade": paciente.get("idade"),
            "telefone": paciente.get("telefone"),
            "data_exame": paciente.get("data_exame"),
        })

    dados.update(dados_medicao_csv)
    salvar_linha_csv(paciente_id, dados)

# -----------------------------
# ROTAS
# -----------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/healthz")
def healthz():
    return {"status": "ok"}


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

    paciente_id = request.args.get("paciente_id")

    paciente = None
    medicoes = []
    medicao = None
    receitas = []
    armacao = None

    # lista lateral
    cursor.execute("SELECT id, nome FROM pacientes ORDER BY nome")
    pacientes = cursor.fetchall()

    if paciente_id:
        # PACIENTE
        cursor.execute("SELECT * FROM pacientes WHERE id=?", (paciente_id,))
        paciente = cursor.fetchone()

        # HISTÓRICO DE MEDIÇÕES
        cursor.execute("""
            SELECT dp, dnp_e, dnp_d, score, data
            FROM medicoes
            WHERE paciente_id=?
            ORDER BY id DESC
            LIMIT 5
        """, (paciente_id,))
        medicoes = cursor.fetchall()

        # ÚLTIMA MEDIÇÃO
        if medicoes:
            medicao = medicoes[0]

        # RECEITAS
        cursor.execute("""
            SELECT * FROM receitas
            WHERE paciente_id=?
            ORDER BY id DESC
        """, (paciente_id,))
        receitas = cursor.fetchall()

        # ARMAÇÃO
        cursor.execute("""
            SELECT a.*
            FROM pedidos p
            JOIN armacoes a ON p.armacao = a.id
            WHERE p.paciente_id=?
            ORDER BY p.id DESC LIMIT 1
        """, (paciente_id,))
        armacao = cursor.fetchone()

    conn.close()

    return render_template("dashboard.html",
        paciente=paciente,
        medicoes=medicoes,
        medicao=medicao,
        receitas=receitas,
        armacao=armacao,
        pacientes=pacientes
    )


@app.route("/prontuario/<int:id>")
def prontuario(id):
    import json

    conn = get_db()
    cursor = conn.cursor()

    # PACIENTE
    cursor.execute("SELECT * FROM pacientes WHERE id=?", (id,))
    paciente = cursor.fetchone()
    paciente = dict(paciente) if paciente else None

    # RECEITAS
    cursor.execute("SELECT * FROM receitas WHERE paciente_id=? ORDER BY id DESC", (id,))
    receitas = cursor.fetchall()
    receitas = [dict(r) for r in receitas]

    # MEDIÇÃO (última)
    cursor.execute("SELECT * FROM medicoes WHERE paciente_id=? ORDER BY id DESC LIMIT 1", (id,))
    medicao = cursor.fetchone()
    medicao = dict(medicao) if medicao else None

    if medicao:
        # Validação
        if medicao.get("validacao_json"):
            medicao["validacao"] = json.loads(medicao["validacao_json"])
        else:
            medicao["validacao"] = None

        # Histórico
        if medicao.get("historico_json"):
            medicao["historico"] = [float(x) for x in json.loads(medicao["historico_json"])]
        else:
            medicao["historico"] = None

    # ARMAÇÃO
    cursor.execute("""
        SELECT a.modelo, a.marca, a.tamanho, a.material
        FROM pedidos p
        JOIN armacoes a ON p.armacao = a.id
        WHERE p.paciente_id=?
        ORDER BY p.id DESC LIMIT 1
    """, (id,))
    armacao = cursor.fetchone()
    armacao = dict(armacao) if armacao else None

    conn.close()

    return render_template(
        "prontuario.html",
        paciente=paciente,
        receitas=receitas,
        medicao=medicao,
        armacao=armacao
    )



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

@app.route("/api/armacoes")
def listar_armacoes():
    import os

    pasta = os.path.join("static", "armacoes")
    arquivos = os.listdir(pasta)

    imagens = [f for f in arquivos if f.endswith(".png")]

    return {"armacoes": imagens}


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
    paciente_id_session = session.get("paciente_id")

    print("URL ID:", paciente_id)
    print("SESSION ID:", paciente_id_session)

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
    # ARMAÇÃO
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
    # RECEITA (TABELA)
    # =========================
    if receita:
        story.append(Paragraph("<b>RECEITA</b>", styles['Heading2']))
        story.append(Spacer(1, 10))
        print("RECEITA:", receita)
        tabela_receita = Table([
            ["Olho", "ESF", "CIL", "EIXO"],
            ["OD", receita['od_esf'], receita['od_cil'], receita['od_eixo']],
            ["OE", receita['oe_esf'], receita['oe_cil'], receita['oe_eixo']],
        ])

        tabela_receita.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]))

        story.append(tabela_receita)
        story.append(Spacer(1, 10))

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
    # MEDIÇÕES (TABELA)
    # =========================
    if medicao:
        story.append(Paragraph("<b>MEDIÇÕES BIOMÉTRICAS</b>", styles['Heading2']))
        story.append(Spacer(1, 10))

        tabela_medicao = Table([
            ["Parâmetro", "Valor"],
            ["DP", f"{medicao['dp']:.1f} mm"],
            ["DNP Esquerdo", f"{medicao['dnp_e']:.1f} mm"],
            ["DNP Direito", f"{medicao['dnp_d']:.1f} mm"],
            ["Precisão", f"{medicao['score']:.0f}%"],
            ["Data", medicao['data']],
        ])

        tabela_medicao.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]))

        story.append(tabela_medicao)
        story.append(Spacer(1, 20))

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
        rg = request.form["rg"]
        data_nascimento = request.form["data_nascimento"]
        sexo = request.form["sexo"]
        idade = int(request.form["idade"])
        telefone = request.form["telefone"]
        data_exame = request.form["data_exame"]

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO pacientes 
        (nome, rg, data_nascimento, sexo, idade, telefone, data_exame)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            nome,
            rg,
            data_nascimento,
            sexo,
            idade,
            telefone,
            data_exame
        ))

        paciente_id = cursor.lastrowid

        conn.commit()
        conn.close()

        session["paciente_id"] = paciente_id
        registrar_paciente_no_csv({
            "id": paciente_id,
            "nome": nome,
            "rg": rg,
            "data_nascimento": data_nascimento,
            "sexo": sexo,
            "idade": idade,
            "telefone": telefone,
            "data_exame": data_exame,
        })

        return redirect(f"/medicao?paciente_id={paciente_id}")

    except Exception as e:
        return f"Erro ao salvar paciente: {str(e)}"


@app.route("/salvar_receita", methods=["POST"])
def salvar_receita():
    paciente_id = session.get("paciente_id")

    if not paciente_id:
        return redirect("/paciente")

    conn = get_db()
    cursor = conn.cursor()

    # Cria a tabela se não existir
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS receitas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paciente_id INTEGER NOT NULL,
        od_esf REAL,
        od_cil REAL,
        od_eixo INTEGER,
        oe_esf REAL,
        oe_cil REAL,
        oe_eixo INTEGER,
        adicao REAL,
        data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()

    # Pega os valores do formulário de forma segura
    od_esf = float(request.form.get("od_esf_longe", 0) or 0)
    od_cil = float(request.form.get("od_cil_longe", 0) or 0)
    od_eixo = int(request.form.get("od_eixo_longe", 0) or 0)

    oe_esf = float(request.form.get("oe_esf_longe", 0) or 0)
    oe_cil = float(request.form.get("oe_cil_longe", 0) or 0)
    oe_eixo = int(request.form.get("oe_eixo_longe", 0) or 0)

    adicao = float(request.form.get("adicao", 0) or 0)  # campo ADD

    # Insere os dados na tabela
    cursor.execute("""
        INSERT INTO receitas (paciente_id, od_esf, od_cil, od_eixo, oe_esf, oe_cil, oe_eixo, adicao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (paciente_id, od_esf, od_cil, od_eixo, oe_esf, oe_cil, oe_eixo, adicao))

    conn.commit()
    conn.close()

    return redirect(f"/medicao?paciente_id={paciente_id}")


# -----------------------------
# VIDEO STREAM
# -----------------------------

def iniciar_camera():
    global camera

    if camera is None:

        print("📸 Tentando ligar câmera...")

        camera = cv2.VideoCapture(0)

        # 🔥 VERIFICA SE A CÂMERA EXISTE
        if not camera.isOpened():

            print("❌ Nenhuma câmera disponível")

            camera.release()
            camera = None

            return False

    return True


def gen_frames():

    global camera, camera_ativa

    # 🔥 SE NÃO CONSEGUIR ABRIR A CÂMERA
    if not iniciar_camera():

        print("🚫 Stream cancelado")

        return

    camera_ativa = True

    while True:

        # 🔥 PARA STREAM
        if not camera_ativa:

            print("🛑 Parando stream da câmera...")
            break

        # 🔥 CÂMERA INVÁLIDA
        if camera is None:

            print("❌ Camera None")
            break

        success, frame = camera.read()

        # 🔥 FALHA DE LEITURA
        if not success:

            print("❌ Falha ao capturar frame")
            break

        # 🔥 PROCESSA FRAME
        frame = processar_frame(frame)

        ret, buffer = cv2.imencode('.jpg', frame)

        if not ret:
            continue

        frame_bytes = buffer.tobytes()

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' +
            frame_bytes +
            b'\r\n'
        )

    # 🔥 FINALIZA
    if camera is not None:

        camera.release()
        camera = None

        print("📴 Câmera desligada")


@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/dados")
def dados():

    paciente_id = request.args.get("paciente_id")

    faixa = "indefinido"
    dp_min, dp_max = 50, 80
    idade = None
    sexo = "outro"

    # =========================
    # 🔍 BUSCA PACIENTE
    # =========================
    if paciente_id:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT sexo, data_nascimento
            FROM pacientes
            WHERE id=?
        """, (paciente_id,))

        paciente = cursor.fetchone()
        conn.close()

        # 🔥 DEBUG AGORA NO LUGAR CERTO
        debug_log("===================================")
        debug_log("PACIENTE RAW:", paciente)

        if paciente:
            sexo = (paciente["sexo"] or "outro").lower().strip()

            debug_log("SEXO:", sexo)
            debug_log("DATA NASC:", paciente["data_nascimento"])

            # =========================
            # 🎂 CALCULA IDADE
            # =========================
            if paciente["data_nascimento"]:
                try:
                    from datetime import datetime

                    nascimento = datetime.strptime(
                        paciente["data_nascimento"], "%Y-%m-%d"
                    )
                    hoje = datetime.now()

                    idade = hoje.year - nascimento.year
                    if (hoje.month, hoje.day) < (nascimento.month, nascimento.day):
                        idade -= 1

                except Exception as e:
                    debug_log("ERRO IDADE:", e)
                    idade = None

            debug_log("IDADE:", idade)

    # =========================
    # 🧠 PERFIL BIOMÉTRICO
    # =========================
    if idade is not None and idade < 18:
        faixa = "crianca"
        dp_min, dp_max = 40, 58

    elif idade is not None:
        faixa = "adulto"

        if sexo == "masculino":
            dp_min, dp_max = 62, 70
        elif sexo == "feminino":
            dp_min, dp_max = 58, 66
        else:
            dp_min, dp_max = 58, 70

    debug_log("PERFIL FINAL:", faixa, dp_min, dp_max)

    # =========================
    # 📊 VALIDAÇÃO EM TEMPO REAL
    # =========================
    dp_atual = dados_medicao.get("dp")

    status_dp = "indefinido"

    if dp_atual is not None:

        if dp_atual < dp_min:
            status_dp = "baixo"
        elif dp_atual > dp_max:
            status_dp = "alto"
        else:
            status_dp = "normal"

    # =========================
    # 📦 RESPOSTA FINAL
    # =========================
    return jsonify({
        "dp": dados_medicao.get("dp", 0),
        "dnp_e": dados_medicao.get("dnp_e", 0),
        "dnp_d": dados_medicao.get("dnp_d", 0),
        "score": dados_medicao.get("score", 0),
        "status": dados_medicao.get("status", ""),
        "instrucao": dados_medicao.get("instrucao", ""),
        "capturado": dados_medicao.get("capturado", False),
        "confiavel": dados_medicao.get("confiavel", False),
        "distancia_cm": dados_medicao.get("distancia_cm"),
        "iris_px": dados_medicao.get("iris_px"),

        # 🔥 INTELIGÊNCIA
        "faixa": faixa,
        "idade": idade,
        "sexo": sexo,
        "dp_min": dp_min,
        "dp_max": dp_max,
        "status_dp": status_dp
    })

#"frames_validos": dados_medicao["frames_validos"]  # 🔥 AQUI
# -----------------------------
# API
# -----------------------------

@app.route("/salvar_medicao", methods=["POST"])
def salvar_medicao():
    import json
    import statistics

    dados = request.get_json()

    dp = float(dados["dp"])
    dnp_e = float(dados["dnp_e"])
    dnp_d = float(dados["dnp_d"])
    score = float(dados["score"])

    historico_dp = dados.get("historico", [])
    caminho_foto = dados.get("foto", None)

    # =========================
    # VALIDAÇÃO INTELIGENTE
    # =========================

    erro = abs((dnp_e + dnp_d) - dp)

    if erro > 2:
        return {"status": "erro", "msg": "Medição inconsistente"}

    if dp < 50 or dp > 80:
        return {"status": "erro", "msg": "DP fora do padrão"}

    if score < 70:
        return {"status": "erro", "msg": "Baixa confiabilidade"}

    # =========================
    # AJUSTE FINAL
    # =========================

    dp = (dnp_e + dnp_d)

    # =========================
    # VALIDAÇÃO CLÍNICA
    # =========================

    if historico_dp:
        media = round(statistics.mean(historico_dp), 2)
        desvio = round(statistics.stdev(historico_dp), 2) if len(historico_dp) > 1 else 0
        erro_max = round(max(historico_dp) - min(historico_dp), 2)
    else:
        media = dp
        desvio = 0
        erro_max = 0

    status_validacao = "APROVADO" if desvio < 1.0 else "REPROVADO"

    validacao = {
        "media": media,
        "desvio": desvio,
        "erro_max": erro_max,
        "status": status_validacao
    }

    # =========================
    # SALVAR NO BANCO
    # =========================

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO medicoes (
        paciente_id, dp, dnp_e, dnp_d, score,
        validacao_json, historico_json, foto_captura, data
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (
        dados["paciente_id"],
        dp,
        dnp_e,
        dnp_d,
        score,
        json.dumps(validacao),
        json.dumps(historico_dp),
        caminho_foto
    ))

    conn.commit()
    conn.close()

    registrar_medicao_no_csv(dados["paciente_id"], {
        "medicao_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dp": dp,
        "dnp_e": dnp_e,
        "dnp_d": dnp_d,
        "score": score,
        "status_validacao": status_validacao,
        "validacao_json": json.dumps(validacao, ensure_ascii=False),
        "historico_json": json.dumps(historico_dp, ensure_ascii=False),
        "foto_final": caminho_foto,
    })

    return {
        "status": "ok",
        "validacao": validacao,
        "dp_final": dp
    }


@app.route("/salvar_foto", methods=["POST"])
def salvar_foto():
    dados = request.json

    paciente_id = dados["paciente_id"]
    imagem = dados["imagem"]

    dp = dados["dp"]
    dnp_e = dados["dnp_e"]
    dnp_d = dados["dnp_d"]
    score = dados.get("score", 0)

    img_data = base64.b64decode(imagem.split(",")[1])

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    caminho = f"static/fotos/paciente_{paciente_id}_{timestamp}.jpg"

    os.makedirs("static/fotos", exist_ok=True)

    with open(caminho, "wb") as f:
        f.write(img_data)

    conn = get_db()
    cursor = conn.cursor()

    # 🔥 SALVA MEDIÇÃO COMPLETA
    cursor.execute("""
        INSERT INTO medicoes 
        (paciente_id, dp, dnp_e, dnp_d, score, data, caminho_imagem)
        VALUES (?, ?, ?, ?, ?, datetime('now'), ?)
    """, (paciente_id, dp, dnp_e, dnp_d, score, caminho))

    # 🔥 Atualiza só a última foto no paciente (opcional)
    cursor.execute("""
        UPDATE pacientes SET foto=? WHERE id=?
    """, (caminho, paciente_id))

    conn.commit()
    conn.close()

    registrar_medicao_no_csv(paciente_id, {
        "medicao_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dp": dp,
        "dnp_e": dnp_e,
        "dnp_d": dnp_d,
        "score": score,
        "fotos_capturadas": caminho,
        "foto_final": caminho,
    })

    return {"status": "ok"}

@app.route("/reset_medicoes/<int:paciente_id>", methods=["POST"])
def reset_medicoes(paciente_id):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM medicoes WHERE paciente_id=?", (paciente_id,))

    conn.commit()
    conn.close()

    return {"status": "ok"}


@app.route("/salvar_lote", methods=["POST"])
def salvar_lote():

    dados = request.json
    paciente_id = dados["paciente_id"]
    medicoes = dados["medicoes"]

    if not medicoes:
        return {"status": "erro", "msg": "Nenhuma medicao recebida"}

    import numpy as np
    import base64, os, json
    from datetime import datetime

    conn = get_db()
    cursor = conn.cursor()

    dps = []
    dnps_e = []
    dnps_d = []
    scores = []
    capturas_csv = []
    imagens_salvas = []

    for m in medicoes:

        dp = m["dp"]
        dnp_e = m["dnp_e"]
        dnp_d = m["dnp_d"]
        score = m["score"]
        imagem = m["imagem"]

        # salvar imagem
        img_data = base64.b64decode(imagem.split(",")[1])

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        caminho = f"static/fotos/paciente_{paciente_id}_{timestamp}.jpg"

        os.makedirs("static/fotos", exist_ok=True)

        with open(caminho, "wb") as f:
            f.write(img_data)

        imagens_salvas.append(caminho)
        dps.append(dp)
        dnps_e.append(dnp_e)
        dnps_d.append(dnp_d)
        scores.append(score)
        capturas_csv.append({
            "dp": dp,
            "dnp_e": dnp_e,
            "dnp_d": dnp_d,
            "score": score,
            "foto": caminho,
        })

    # =========================
    # 📊 VALIDAÇÃO
    # =========================
    media = float(np.mean(dps))
    dnp_e_media = float(np.mean(dnps_e))
    dnp_d_media = float(np.mean(dnps_d))
    score_medio = float(np.mean(scores))
    desvio = float(np.std(dps))
    erro_max = float(max([abs(x - media) for x in dps]))

    status = "APROVADO" if erro_max <= 2 else "REPROVADO"

    validacao = {
        "media": round(media, 2),
        "desvio": round(desvio, 3),
        "erro_max": round(erro_max, 2),
        "status": status
    }

    # =========================
    # 💾 SALVAR (UMA LINHA FINAL)
    # =========================
    caminho_final = imagens_salvas[-1]  # última imagem

    cursor.execute("""
        INSERT INTO medicoes 
        (paciente_id, dp, dnp_e, dnp_d, score, caminho_imagem, validacao_json, historico_json, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (
        paciente_id,
        round(media, 2),  # 🔥 usa média
        round(dnp_e_media, 2),
        round(dnp_d_media, 2),
        round(score_medio, 2),
        caminho_final,
        json.dumps(validacao),
        json.dumps(dps)
    ))

    # =========================
    # 🖼️ ATUALIZA FOTO DO PACIENTE
    # =========================
    cursor.execute("""
        UPDATE pacientes SET foto=? WHERE id=?
    """, (caminho_final, paciente_id))

    conn.commit()
    conn.close()

    registrar_medicao_no_csv(paciente_id, {
        "medicao_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dp": round(media, 2),
        "dnp_e": round(dnp_e_media, 2),
        "dnp_d": round(dnp_d_media, 2),
        "score": round(score_medio, 2),
        "status_validacao": status,
        "validacao_json": json.dumps(validacao, ensure_ascii=False),
        "historico_json": json.dumps(dps, ensure_ascii=False),
        "capturas_json": json.dumps(capturas_csv, ensure_ascii=False),
        "fotos_capturadas": "|".join(imagens_salvas),
        "foto_final": caminho_final,
    })

    return {
        "status": "ok",
        "dp_medio": round(media, 2),
        "dnp_e_media": round(dnp_e_media, 2),
        "dnp_d_media": round(dnp_d_media, 2),
        "desvio": round(desvio, 2),
        "erro_max": round(erro_max, 2),
        "status_validacao": status
    }

@app.route("/process-frame", methods=["POST"])
def process_frame():
    import numpy as np

    data = request.json["image"]

    img_data = base64.b64decode(data.split(",")[1])
    np_arr = np.frombuffer(img_data, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    processar_frame(frame)

    return jsonify({
        "status": "ok",
        "dp": dados_medicao.get("dp", 0),
        "dnp_e": dados_medicao.get("dnp_e", 0),
        "dnp_d": dados_medicao.get("dnp_d", 0),
        "score": dados_medicao.get("score", 0),
        "confiavel": dados_medicao.get("confiavel", False),
        "iris_px": dados_medicao.get("iris_px"),
    })


camera_ativa = True

@app.route("/stop_camera")
def stop_camera():
    global camera_ativa, camera

    camera_ativa = False

    if camera is not None and camera.isOpened():
        camera.release()
        camera = None
        print("📴 Câmera desligada via rota")

    return {"status": "ok"}

# -----------------------------
# START
# -----------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
