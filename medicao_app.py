import base64
import json
import os
from datetime import datetime

import cv2
import numpy as np
from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from vision_engine import dados_medicao, processar_frame, resetar_medicao
from visionai_shared import (
    aplicar_calibracao_valor,
    calcular_idade_por_data,
    database_config,
    debug_log,
    gerar_ods,
    get_db,
    gravacao_bloqueada_por_banco,
    inserir_retornando_id,
    mensagem_banco_obrigatorio,
    obter_calibracao_facial,
    perfil_calibracao_paciente,
    registrar_medicao_no_csv,
    registrar_paciente_no_csv,
)


app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))


def env_float(nome, padrao):
    try:
        return float(os.getenv(nome, padrao))
    except (TypeError, ValueError):
        return padrao


def env_int(nome, padrao):
    try:
        return int(float(os.getenv(nome, padrao)))
    except (TypeError, ValueError):
        return padrao


def capture_ui_config():
    modo_local = os.getenv("VISIONAI_LOCAL_MODE", "0") == "1"
    return {
        "score_min": env_float("VISIONAI_UI_CAPTURE_SCORE_MIN", 78 if modo_local else 70),
        "reset_score": env_float("VISIONAI_UI_CAPTURE_RESET_SCORE", 55 if modo_local else 45),
        "hold_ms": env_int("VISIONAI_UI_CAPTURE_HOLD_MS", 900 if modo_local else 450),
        "total": env_int("VISIONAI_UI_TOTAL_CAPTURES", 5 if modo_local else 4),
    }


@app.route("/")
def index():
    session.pop("paciente_id", None)
    return render_template("index.html")


@app.route("/healthz")
def healthz():
    config_banco = database_config()
    return {
        "status": "ok",
        "app": "medicao",
        "database": config_banco["backend"],
        "database_persistente": config_banco["persistente"],
    }


@app.route("/db-status")
def db_status():
    config_banco = database_config()

    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS total FROM pacientes")
        pacientes_total = cursor.fetchone()["total"]
        cursor.execute("SELECT COUNT(*) AS total FROM medicoes")
        medicoes_total = cursor.fetchone()["total"]
        conn.close()

        return {
            "status": "ok",
            "app": "medicao",
            "database": config_banco["backend"],
            "database_persistente": config_banco["persistente"],
            "pacientes": pacientes_total,
            "medicoes": medicoes_total,
        }
    except Exception as exc:
        return {
            "status": "error",
            "app": "medicao",
            "database": config_banco["backend"],
            "database_persistente": config_banco["persistente"],
            "error": str(exc),
        }, 500


@app.route("/paciente")
def paciente():
    return render_template("paciente.html")


@app.route("/cadastro")
def cadastro():
    return redirect(url_for("paciente"))


@app.route("/salvar_paciente", methods=["POST"])
def salvar_paciente():
    if gravacao_bloqueada_por_banco():
        return mensagem_banco_obrigatorio(), 503

    nome = request.form["nome"]
    rg = request.form["rg"]
    data_nascimento = request.form["data_nascimento"]
    sexo = request.form["sexo"]
    idade = request.form.get("idade", type=int)
    telefone = request.form["telefone"]
    data_exame = request.form["data_exame"]

    if idade is None:
        idade = calcular_idade_por_data(data_nascimento) or 0

    conn = get_db()
    cursor = conn.cursor()

    paciente_id = inserir_retornando_id(cursor, """
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
        data_exame,
    ))

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

    return redirect(url_for("medicao", paciente_id=paciente_id))


@app.route("/medicao")
@app.route("/medicao/<int:paciente_id>")
def medicao(paciente_id=None):
    paciente_id = paciente_id or request.args.get("paciente_id", type=int) or session.get("paciente_id")

    if not paciente_id:
        return redirect(url_for("paciente"))

    resetar_medicao()

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, nome, sexo, data_nascimento, idade FROM pacientes WHERE id=?", (paciente_id,))
    paciente = cursor.fetchone()
    conn.close()

    if not paciente:
        session.pop("paciente_id", None)
        return redirect(url_for("paciente"))

    session["paciente_id"] = paciente_id
    return render_template(
        "medicao.html",
        paciente=paciente,
        paciente_id=paciente_id,
        capture_config=capture_ui_config(),
    )


@app.route("/dados")
def dados():
    paciente_id = request.args.get("paciente_id")

    faixa = "indefinido"
    dp_min, dp_max = 50, 80
    idade = None
    sexo = "outro"

    if paciente_id:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT sexo, data_nascimento, idade
            FROM pacientes
            WHERE id=?
        """, (paciente_id,))
        paciente = cursor.fetchone()
        conn.close()

        if paciente:
            sexo = (paciente.get("sexo") or "outro").lower().strip()
            idade = paciente.get("idade") or calcular_idade_por_data(paciente.get("data_nascimento"))

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

    dp_atual = dados_medicao.get("dp")
    status_dp = "indefinido"
    if dp_atual is not None:
        if dp_atual < dp_min:
            status_dp = "baixo"
        elif dp_atual > dp_max:
            status_dp = "alto"
        else:
            status_dp = "normal"

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
        "iris_ok": dados_medicao.get("iris_ok", False),
        "olhos_ok": dados_medicao.get("olhos_ok", False),
        "cabeca_ok": dados_medicao.get("cabeca_ok", False),
        "centro_ok": dados_medicao.get("centro_ok", False),
        "dist_ok": dados_medicao.get("dist_ok", False),
        "faixa": faixa,
        "idade": idade,
        "sexo": sexo,
        "dp_min": dp_min,
        "dp_max": dp_max,
        "status_dp": status_dp,
    })


@app.route("/process-frame", methods=["POST"])
def process_frame():
    payload = request.get_json(silent=True) or {}
    data = payload.get("image")
    if not data or "," not in data:
        return jsonify({"status": "erro", "msg": "Frame invalido"}), 400

    try:
        img_data = base64.b64decode(data.split(",", 1)[1])
    except (ValueError, TypeError, base64.binascii.Error):
        return jsonify({"status": "erro", "msg": "Frame invalido"}), 400

    np_arr = np.frombuffer(img_data, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if frame is None:
        return jsonify({"status": "erro", "msg": "Frame invalido"}), 400

    try:
        processar_frame(frame)
    except Exception as exc:
        debug_log("ERRO PROCESS_FRAME:", exc)
        return jsonify({"status": "erro", "msg": "Nao foi possivel processar o frame"}), 500

    return jsonify({
        "status": "ok",
        "dp": dados_medicao.get("dp", 0),
        "dnp_e": dados_medicao.get("dnp_e", 0),
        "dnp_d": dados_medicao.get("dnp_d", 0),
        "score": dados_medicao.get("score", 0),
        "capturado": dados_medicao.get("capturado", False),
        "confiavel": dados_medicao.get("confiavel", False),
        "instrucao": dados_medicao.get("instrucao", ""),
        "iris_px": dados_medicao.get("iris_px"),
        "olhos_ok": dados_medicao.get("olhos_ok", False),
        "cabeca_ok": dados_medicao.get("cabeca_ok", False),
        "centro_ok": dados_medicao.get("centro_ok", False),
        "dist_ok": dados_medicao.get("dist_ok", False),
    })


@app.route("/salvar_lote", methods=["POST"])
def salvar_lote():
    if gravacao_bloqueada_por_banco():
        return {"status": "erro", "msg": mensagem_banco_obrigatorio()}, 503

    dados = request.get_json(silent=True) or {}
    paciente_id = dados.get("paciente_id")
    medicoes = dados.get("medicoes") or []

    if not paciente_id:
        return {"status": "erro", "msg": "Paciente invalido"}

    if not medicoes:
        return {"status": "erro", "msg": "Nenhuma medicao recebida"}

    conn = get_db()
    cursor = conn.cursor()
    ods = gerar_ods(cursor)

    dps = []
    dnps_e = []
    dnps_d = []
    scores = []
    capturas_csv = []
    imagens_salvas = []

    os.makedirs("static/fotos", exist_ok=True)

    for medicao_item in medicoes:
        dp = float(medicao_item["dp"])
        dnp_e = float(medicao_item["dnp_e"])
        dnp_d = float(medicao_item["dnp_d"])
        score = float(medicao_item["score"])
        imagem = medicao_item["imagem"]

        img_data = base64.b64decode(imagem.split(",", 1)[1])
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        caminho = f"static/fotos/paciente_{paciente_id}_{timestamp}.jpg"

        with open(caminho, "wb") as arquivo:
            arquivo.write(img_data)

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

    media = float(np.mean(dps))
    dnp_e_media = float(np.mean(dnps_e))
    dnp_d_media = float(np.mean(dnps_d))
    score_medio = float(np.mean(scores))
    desvio = float(np.std(dps))
    erro_max = float(max([abs(valor - media) for valor in dps]))

    cursor.execute("SELECT * FROM pacientes WHERE id=?", (paciente_id,))
    paciente_calibracao = cursor.fetchone()
    sexo_calibracao, faixa_calibracao = perfil_calibracao_paciente(paciente_calibracao)
    calibracao = obter_calibracao_facial(cursor, sexo_calibracao, faixa_calibracao)

    dp_final = aplicar_calibracao_valor(media, calibracao.get("fator_dp"))
    dnp_e_final = aplicar_calibracao_valor(dnp_e_media, calibracao.get("fator_dnp_e"))
    dnp_d_final = aplicar_calibracao_valor(dnp_d_media, calibracao.get("fator_dnp_d"))

    calibracao_aplicada = {
        "sexo": sexo_calibracao,
        "faixa": faixa_calibracao,
        "amostras": calibracao.get("amostras", 0),
        "fator_dp": round(float(calibracao.get("fator_dp") or 1), 5),
        "fator_dnp_e": round(float(calibracao.get("fator_dnp_e") or 1), 5),
        "fator_dnp_d": round(float(calibracao.get("fator_dnp_d") or 1), 5),
        "dp_original": round(media, 2),
        "dnp_e_original": round(dnp_e_media, 2),
        "dnp_d_original": round(dnp_d_media, 2),
    }

    status = "APROVADO" if erro_max <= 2 else "REPROVADO"
    validacao = {
        "media": round(media, 2),
        "desvio": round(desvio, 3),
        "erro_max": round(erro_max, 2),
        "status": status,
    }

    caminho_final = imagens_salvas[-1]

    cursor.execute("""
        INSERT INTO medicoes
        (paciente_id, ods, dp, dnp_e, dnp_d, score,
         caminho_imagem, validacao_json, historico_json,
         dp_original, dnp_e_original, dnp_d_original, calibracao_json, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (
        paciente_id,
        ods,
        dp_final,
        dnp_e_final,
        dnp_d_final,
        round(score_medio, 2),
        caminho_final,
        json.dumps(validacao),
        json.dumps(dps),
        round(media, 2),
        round(dnp_e_media, 2),
        round(dnp_d_media, 2),
        json.dumps(calibracao_aplicada, ensure_ascii=False),
    ))

    cursor.execute("UPDATE pacientes SET foto=? WHERE id=?", (caminho_final, paciente_id))
    conn.commit()
    conn.close()

    registrar_medicao_no_csv(paciente_id, {
        "ods": ods,
        "medicao_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dp": dp_final,
        "dnp_e": dnp_e_final,
        "dnp_d": dnp_d_final,
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
        "ods": ods,
        "dp_medio": dp_final,
        "dnp_e_media": dnp_e_final,
        "dnp_d_media": dnp_d_final,
        "dp_original": round(media, 2),
        "dnp_e_original": round(dnp_e_media, 2),
        "dnp_d_original": round(dnp_d_media, 2),
        "calibracao": calibracao_aplicada,
        "desvio": round(desvio, 2),
        "erro_max": round(erro_max, 2),
        "status_validacao": status,
    }


@app.route("/reset_medicoes/<int:paciente_id>", methods=["POST"])
def reset_medicoes(paciente_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM medicoes WHERE paciente_id=?", (paciente_id,))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.route("/stop_camera")
def stop_camera():
    return {"status": "ok"}


@app.route("/laboratorio")
def laboratorio_redirect():
    laboratorio_url = os.getenv("VISIONAI_LAB_URL", "").strip()
    if laboratorio_url:
        return redirect(laboratorio_url)
    return "Laboratorio separado. Configure VISIONAI_LAB_URL para redirecionar.", 404


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
