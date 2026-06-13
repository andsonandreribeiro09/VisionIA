import os
import re
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from database import database_backend, inserir_retornando_id
from visionai_shared import get_db


app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))


ADMIN_USER = os.getenv("VISIONAI_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("VISIONAI_ADMIN_PASSWORD", "visionai-admin")
CHECKIN_ONLINE_MINUTES = int(os.getenv("VISIONAI_ADMIN_ONLINE_MINUTES", "10"))


def hoje_iso():
    return datetime.now().date().isoformat()


def agora_iso():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_data(valor):
    try:
        return datetime.strptime((valor or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def dias_restantes(vencimento):
    data = parse_data(vencimento)
    if not data:
        return None
    return (data - datetime.now().date()).days


def slugify(texto):
    texto = (texto or "").lower().strip()
    texto = texto.replace("ç", "c")
    texto = re.sub(r"[^a-z0-9]+", "-", texto)
    texto = re.sub(r"-+", "-", texto).strip("-")
    return texto or "loja"


def admin_logado():
    return session.get("visionai_admin") is True


def requer_admin(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not admin_logado():
            return redirect(url_for("admin_login", next=request.path))
        return func(*args, **kwargs)

    return wrapper


def criar_tabelas_admin():
    backend = database_backend()
    conn = get_db()
    cursor = conn.cursor()

    if backend == "postgresql":
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS lojas(
            id SERIAL PRIMARY KEY,
            loja_id TEXT UNIQUE,
            nome TEXT,
            cidade TEXT,
            status TEXT DEFAULT 'ativo',
            plano TEXT,
            vencimento TEXT,
            dominio_medicao TEXT,
            dominio_lab TEXT,
            criado_em TEXT DEFAULT (CURRENT_TIMESTAMP::text)
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS licencas(
            id SERIAL PRIMARY KEY,
            loja_pk INTEGER,
            license_key TEXT UNIQUE,
            status TEXT DEFAULT 'ativo',
            vence_em TEXT,
            ultimo_checkin TEXT,
            machine_id TEXT,
            criado_em TEXT DEFAULT (CURRENT_TIMESTAMP::text)
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS eventos(
            id SERIAL PRIMARY KEY,
            loja_pk INTEGER,
            tipo TEXT,
            mensagem TEXT,
            data TEXT DEFAULT (CURRENT_TIMESTAMP::text)
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS checkins(
            id SERIAL PRIMARY KEY,
            loja_pk INTEGER,
            online INTEGER DEFAULT 1,
            versao TEXT,
            medicoes_hoje INTEGER DEFAULT 0,
            banco_status TEXT,
            data TEXT DEFAULT (CURRENT_TIMESTAMP::text)
        )
        """)
    else:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS lojas(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loja_id TEXT UNIQUE,
            nome TEXT,
            cidade TEXT,
            status TEXT DEFAULT 'ativo',
            plano TEXT,
            vencimento TEXT,
            dominio_medicao TEXT,
            dominio_lab TEXT,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS licencas(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loja_pk INTEGER,
            license_key TEXT UNIQUE,
            status TEXT DEFAULT 'ativo',
            vence_em TEXT,
            ultimo_checkin TEXT,
            machine_id TEXT,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS eventos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loja_pk INTEGER,
            tipo TEXT,
            mensagem TEXT,
            data TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS checkins(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loja_pk INTEGER,
            online INTEGER DEFAULT 1,
            versao TEXT,
            medicoes_hoje INTEGER DEFAULT 0,
            banco_status TEXT,
            data TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

    conn.commit()
    conn.close()


def registrar_evento(cursor, loja_pk, tipo, mensagem):
    cursor.execute("""
        INSERT INTO eventos (loja_pk, tipo, mensagem, data)
        VALUES (?, ?, ?, ?)
    """, (loja_pk, tipo, mensagem, agora_iso()))


def carregar_lojas():
    criar_tabelas_admin()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            l.*,
            lic.license_key,
            lic.status AS licenca_status,
            lic.vence_em,
            lic.ultimo_checkin,
            lic.machine_id,
            (
                SELECT c.versao
                FROM checkins c
                WHERE c.loja_pk = l.id
                ORDER BY c.id DESC
                LIMIT 1
            ) AS versao,
            (
                SELECT c.medicoes_hoje
                FROM checkins c
                WHERE c.loja_pk = l.id
                ORDER BY c.id DESC
                LIMIT 1
            ) AS medicoes_hoje,
            (
                SELECT c.banco_status
                FROM checkins c
                WHERE c.loja_pk = l.id
                ORDER BY c.id DESC
                LIMIT 1
            ) AS banco_status
        FROM lojas l
        LEFT JOIN licencas lic ON lic.loja_pk = l.id
        ORDER BY l.id DESC
    """)
    lojas = [dict(row) for row in cursor.fetchall()]
    conn.close()

    agora = datetime.now()
    for loja in lojas:
        loja["dias_restantes"] = dias_restantes(loja.get("vence_em") or loja.get("vencimento"))
        ultimo = loja.get("ultimo_checkin")
        online = False
        if ultimo:
            try:
                data_ultimo = datetime.strptime(ultimo[:19], "%Y-%m-%d %H:%M:%S")
                online = agora - data_ultimo <= timedelta(minutes=CHECKIN_ONLINE_MINUTES)
            except ValueError:
                online = False
        loja["online"] = online

    return lojas


def buscar_loja_por_id(cursor, store_id, license_key=None):
    if license_key:
        cursor.execute("""
            SELECT l.*, lic.id AS licenca_id, lic.license_key, lic.status AS licenca_status,
                   lic.vence_em, lic.machine_id
            FROM lojas l
            JOIN licencas lic ON lic.loja_pk = l.id
            WHERE l.loja_id=? AND lic.license_key=?
            LIMIT 1
        """, (store_id, license_key))
    else:
        cursor.execute("""
            SELECT l.*, lic.id AS licenca_id, lic.license_key, lic.status AS licenca_status,
                   lic.vence_em, lic.machine_id
            FROM lojas l
            LEFT JOIN licencas lic ON lic.loja_pk = l.id
            WHERE l.loja_id=?
            LIMIT 1
        """, (store_id,))
    return cursor.fetchone()


def resultado_licenca(loja):
    dias = dias_restantes(loja.get("vence_em") or loja.get("vencimento"))
    loja_ativa = loja.get("status") == "ativo"
    licenca_ativa = loja.get("licenca_status") == "ativo"
    vencida = dias is not None and dias < 0
    captura_liberada = loja_ativa and licenca_ativa and not vencida

    if not loja_ativa:
        status = "suspenso"
        mensagem = "Loja suspensa. Entre em contato com o suporte VisionAI."
    elif not licenca_ativa:
        status = loja.get("licenca_status") or "inativa"
        mensagem = "Licenca inativa. Entre em contato com o suporte VisionAI."
    elif vencida:
        status = "expirado"
        mensagem = "Licenca expirada. Entre em contato com o suporte VisionAI."
    else:
        status = "ativo"
        mensagem = "Licenca ativa."

    return {
        "status": status,
        "plano": loja.get("plano"),
        "vence_em": loja.get("vence_em") or loja.get("vencimento"),
        "dias_restantes": dias,
        "captura_liberada": captura_liberada,
        "mensagem": mensagem,
        "loja": {
            "id": loja.get("loja_id"),
            "nome": loja.get("nome"),
            "cidade": loja.get("cidade"),
            "dominio_medicao": loja.get("dominio_medicao"),
            "dominio_lab": loja.get("dominio_lab"),
        },
    }


@app.route("/")
def index():
    return redirect(url_for("admin_dashboard"))


@app.route("/healthz")
def healthz():
    criar_tabelas_admin()
    return jsonify({"status": "ok", "app": "admin", "database": database_backend()})


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    erro = None
    if request.method == "POST":
        usuario = request.form.get("usuario", "")
        senha = request.form.get("senha", "")
        if usuario == ADMIN_USER and senha == ADMIN_PASSWORD:
            session["visionai_admin"] = True
            return redirect(request.args.get("next") or url_for("admin_dashboard"))
        erro = "Usuario ou senha invalidos."

    return render_template("admin_login.html", erro=erro)


@app.route("/admin/logout")
def admin_logout():
    session.pop("visionai_admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@requer_admin
def admin_dashboard():
    lojas = carregar_lojas()
    defaults = {
        "nome": "Detecta Vision Osasco",
        "cidade": "Osasco/SP",
        "loja_id": "detecta-vision-osasco-001",
        "status": "ativo",
        "plano": "validacao-30-dias",
        "vencimento": (datetime.now().date() + timedelta(days=30)).isoformat(),
        "dominio_medicao": "detectavision-medicao.visioniaotica.com.br",
        "dominio_lab": "detectavision-lab.visioniaotica.com.br",
    }
    return render_template(
        "admin.html",
        lojas=lojas,
        defaults=defaults,
        admin_user=ADMIN_USER,
        mensagem=request.args.get("msg"),
        erro=request.args.get("erro"),
    )


@app.route("/admin/lojas", methods=["POST"])
@requer_admin
def admin_criar_loja():
    criar_tabelas_admin()
    nome = (request.form.get("nome") or "").strip()
    cidade = (request.form.get("cidade") or "").strip()
    loja_id = (request.form.get("loja_id") or slugify(f"{nome}-{cidade}-001")).strip()
    loja_id = slugify(loja_id)
    status = request.form.get("status") or "ativo"
    plano = request.form.get("plano") or "validacao-30-dias"
    vencimento = request.form.get("vencimento") or (datetime.now().date() + timedelta(days=30)).isoformat()
    dominio_medicao = (request.form.get("dominio_medicao") or "").strip()
    dominio_lab = (request.form.get("dominio_lab") or "").strip()
    license_key = (request.form.get("license_key") or f"VAI-{secrets.token_urlsafe(24)}").strip()

    if not nome:
        return redirect(url_for("admin_dashboard", erro="Informe o nome da loja."))

    conn = get_db()
    cursor = conn.cursor()
    try:
        loja_pk = inserir_retornando_id(cursor, """
            INSERT INTO lojas
            (loja_id, nome, cidade, status, plano, vencimento, dominio_medicao, dominio_lab, criado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            loja_id,
            nome,
            cidade,
            status,
            plano,
            vencimento,
            dominio_medicao,
            dominio_lab,
            agora_iso(),
        ))

        cursor.execute("""
            INSERT INTO licencas
            (loja_pk, license_key, status, vence_em, criado_em)
            VALUES (?, ?, ?, ?, ?)
        """, (loja_pk, license_key, status, vencimento, agora_iso()))
        registrar_evento(cursor, loja_pk, "loja_criada", f"Loja {nome} criada com plano {plano}.")
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        return redirect(url_for("admin_dashboard", erro=f"Nao foi possivel criar a loja: {exc}"))

    conn.close()
    return redirect(url_for("admin_dashboard", msg=f"Loja {nome} criada."))


@app.route("/admin/lojas/<int:loja_pk>/editar", methods=["POST"])
@requer_admin
def admin_editar_loja(loja_pk):
    criar_tabelas_admin()
    nome = (request.form.get("nome") or "").strip()
    cidade = (request.form.get("cidade") or "").strip()
    loja_id = (request.form.get("loja_id") or "").strip()
    loja_id = slugify(loja_id)
    status = request.form.get("status") or "ativo"
    if status not in {"ativo", "suspenso"}:
        status = "ativo"
    plano = (request.form.get("plano") or "validacao-30-dias").strip()
    vencimento = request.form.get("vencimento") or (datetime.now().date() + timedelta(days=30)).isoformat()
    dominio_medicao = (request.form.get("dominio_medicao") or "").strip()
    dominio_lab = (request.form.get("dominio_lab") or "").strip()

    if not nome:
        return redirect(url_for("admin_dashboard", erro="Informe o nome da loja."))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM lojas WHERE id=?", (loja_pk,))
    if cursor.fetchone() is None:
        conn.close()
        return redirect(url_for("admin_dashboard", erro="Loja nao encontrada."))

    cursor.execute("SELECT id FROM lojas WHERE loja_id=? AND id<>? LIMIT 1", (loja_id, loja_pk))
    if cursor.fetchone():
        conn.close()
        return redirect(url_for("admin_dashboard", erro=f"O ID {loja_id} ja esta em uso por outra loja."))

    try:
        cursor.execute("""
            UPDATE lojas
            SET loja_id=?, nome=?, cidade=?, status=?, plano=?, vencimento=?,
                dominio_medicao=?, dominio_lab=?
            WHERE id=?
        """, (
            loja_id,
            nome,
            cidade,
            status,
            plano,
            vencimento,
            dominio_medicao,
            dominio_lab,
            loja_pk,
        ))
        cursor.execute("""
            UPDATE licencas
            SET status=?, vence_em=?
            WHERE loja_pk=?
        """, (status, vencimento, loja_pk))
        registrar_evento(cursor, loja_pk, "loja_editada", f"Loja {nome} atualizada no painel admin.")
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        return redirect(url_for("admin_dashboard", erro=f"Nao foi possivel editar a loja: {exc}"))

    conn.close()
    return redirect(url_for("admin_dashboard", msg=f"Loja {nome} atualizada."))


@app.route("/admin/lojas/<int:loja_pk>/status", methods=["POST"])
@requer_admin
def admin_status_loja(loja_pk):
    status = request.form.get("status") or "ativo"
    if status not in {"ativo", "suspenso"}:
        status = "ativo"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE lojas SET status=? WHERE id=?", (status, loja_pk))
    cursor.execute("UPDATE licencas SET status=? WHERE loja_pk=?", (status, loja_pk))
    registrar_evento(cursor, loja_pk, "status", f"Status alterado para {status}.")
    conn.commit()
    conn.close()
    return redirect(url_for("admin_dashboard", msg=f"Status alterado para {status}."))


@app.route("/admin/lojas/<int:loja_pk>/renovar", methods=["POST"])
@requer_admin
def admin_renovar_loja(loja_pk):
    dias = int(request.form.get("dias") or 30)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT vencimento FROM lojas WHERE id=?", (loja_pk,))
    loja = cursor.fetchone()
    base = datetime.now().date()
    vencimento_atual = parse_data(loja.get("vencimento") if loja else None)
    if vencimento_atual and vencimento_atual > base:
        base = vencimento_atual
    novo_vencimento = (base + timedelta(days=dias)).isoformat()

    cursor.execute("""
        UPDATE lojas
        SET status='ativo', vencimento=?
        WHERE id=?
    """, (novo_vencimento, loja_pk))
    cursor.execute("""
        UPDATE licencas
        SET status='ativo', vence_em=?
        WHERE loja_pk=?
    """, (novo_vencimento, loja_pk))
    registrar_evento(cursor, loja_pk, "renovacao", f"Licenca renovada por {dias} dias ate {novo_vencimento}.")
    conn.commit()
    conn.close()
    return redirect(url_for("admin_dashboard", msg=f"Licenca renovada ate {novo_vencimento}."))


@app.route("/api/licenca/verificar", methods=["POST"])
def api_verificar_licenca():
    criar_tabelas_admin()
    dados = request.get_json(silent=True) or {}
    store_id = (dados.get("store_id") or "").strip()
    license_key = (dados.get("license_key") or "").strip()
    machine_id = (dados.get("machine_id") or "").strip()
    app_version = (dados.get("app_version") or "").strip()
    medicoes_hoje = int(dados.get("medicoes_hoje") or 0)
    banco_status = (dados.get("banco_status") or "").strip()

    conn = get_db()
    cursor = conn.cursor()
    loja = buscar_loja_por_id(cursor, store_id, license_key)

    if not loja:
        conn.close()
        return jsonify({
            "status": "invalido",
            "captura_liberada": False,
            "mensagem": "Licenca invalida.",
        }), 403

    resultado = resultado_licenca(loja)
    agora = agora_iso()
    cursor.execute("""
        UPDATE licencas
        SET ultimo_checkin=?, machine_id=?
        WHERE id=?
    """, (agora, machine_id or loja.get("machine_id"), loja.get("licenca_id")))
    cursor.execute("""
        INSERT INTO checkins
        (loja_pk, online, versao, medicoes_hoje, banco_status, data)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (loja.get("id"), 1, app_version, medicoes_hoje, banco_status, agora))

    if not resultado["captura_liberada"]:
        registrar_evento(cursor, loja.get("id"), "licenca_bloqueada", resultado["mensagem"])

    if resultado["status"] == "expirado":
        cursor.execute("UPDATE licencas SET status='expirado' WHERE id=?", (loja.get("licenca_id"),))

    conn.commit()
    conn.close()
    return jsonify(resultado)


@app.route("/api/checkin", methods=["POST"])
def api_checkin():
    return api_verificar_licenca()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5002))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
