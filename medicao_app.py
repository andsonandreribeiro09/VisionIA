import base64
import json
import os
import re
from datetime import datetime

import cv2
import numpy as np
from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from vision_engine import dados_medicao, processar_frame, resetar_medicao
from visionai_shared import (
    aplicar_calibracao_valor,
    calibracao_pronta,
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
        "score_min": env_float("VISIONAI_UI_CAPTURE_SCORE_MIN", 82 if modo_local else 70),
        "reset_score": env_float("VISIONAI_UI_CAPTURE_RESET_SCORE", 60 if modo_local else 45),
        "hold_ms": env_int("VISIONAI_UI_CAPTURE_HOLD_MS", 900 if modo_local else 450),
        "total": env_int("VISIONAI_UI_TOTAL_CAPTURES", 1 if modo_local else 4),
        "cooldown_ms": env_int("VISIONAI_UI_CAPTURE_COOLDOWN_MS", 450 if modo_local else 250),
        "require_stable": os.getenv("VISIONAI_UI_REQUIRE_STABLE", "1" if modo_local else "0") == "1",
        "stable_samples": env_int("VISIONAI_UI_STABLE_SAMPLES", 3 if modo_local else 4),
        "stable_window_ms": env_int("VISIONAI_UI_STABLE_WINDOW_MS", 1400 if modo_local else 2600),
        "max_dp_spread": env_float("VISIONAI_UI_MAX_DP_SPREAD", 1.4 if modo_local else 2.0),
        "max_dp_trend": env_float("VISIONAI_UI_MAX_DP_TREND", 0.55 if modo_local else 1.2),
        "block_dp_margin": env_float("VISIONAI_UI_BLOCK_DP_MARGIN", 0.3 if modo_local else 0),
        "max_capture_gap": env_float("VISIONAI_UI_MAX_CAPTURE_GAP", 1.8 if modo_local else 3.0),
        "incompatible_reset_ms": env_int("VISIONAI_UI_INCOMPATIBLE_RESET_MS", 1600 if modo_local else 2200),
        "geometry_score_min": env_float("VISIONAI_UI_MIN_GEOMETRY_SCORE", 65 if modo_local else 0),
        "min_iris_px": env_float("VISIONAI_MIN_CAPTURE_IRIS_PX", 10.0 if modo_local else 0),
        "max_iris_px": env_float("VISIONAI_MAX_CAPTURE_IRIS_PX", 14.5 if modo_local else 0),
        "ideal_iris_min_px": env_float("VISIONAI_IDEAL_CAPTURE_IRIS_MIN_PX", 11.0 if modo_local else 0),
        "ideal_iris_max_px": env_float("VISIONAI_IDEAL_CAPTURE_IRIS_MAX_PX", 13.9 if modo_local else 0),
        "crop_padding_x": env_float("VISIONAI_UI_CROP_PADDING_X", 1.36),
        "crop_padding_y": env_float("VISIONAI_UI_CROP_PADDING_Y", 1.22),
        "photo_max_width": env_int("VISIONAI_UI_PHOTO_MAX_WIDTH", 720 if modo_local else 960),
        "photo_quality": env_float("VISIONAI_UI_PHOTO_QUALITY", 0.68 if modo_local else 0.78),
        "result_preview_ms": env_int("VISIONAI_RESULT_PREVIEW_MS", 5500 if modo_local else 4200),
    }


def faixa_dp_paciente(paciente):
    sexo = ((paciente or {}).get("sexo") or "outro").lower().strip()
    idade = (paciente or {}).get("idade")

    if idade is None:
        idade = calcular_idade_por_data((paciente or {}).get("data_nascimento"))

    if idade is not None and idade < 18:
        return "crianca", 40, 58, 36, 64

    if sexo == "masculino":
        return "adulto", 62, 70, 58, 78

    if sexo == "feminino":
        return "adulto", 58, 66, 54, 74

    return "adulto", 58, 70, 54, 78


QUALIDADE_CAMPOS = [
    "yaw",
    "pitch",
    "roll",
    "iris_px",
    "distancia_cm",
    "centro_face",
    "centro_face_offset",
    "score_geometrico",
    "ambiente_score",
    "brilho",
    "contraste",
    "nitidez",
]


def qualidade_atual():
    return {campo: dados_medicao.get(campo) for campo in QUALIDADE_CAMPOS}


def numero_opcional(valor):
    try:
        if valor is None or valor == "":
            return None
        return float(valor)
    except (TypeError, ValueError):
        return None


def resumir_qualidade(capturas):
    resumo = {}
    for campo in QUALIDADE_CAMPOS:
        valores = [
            numero_opcional((captura.get("qualidade") or {}).get(campo))
            for captura in capturas
        ]
        valores = [valor for valor in valores if valor is not None]
        if valores:
            resumo[campo] = round(float(np.mean(valores)), 2)
    return resumo


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
    os_teste = [f"{numero:05d}" for numero in range(1166, 1176)]
    return render_template(
        "paciente.html",
        data_exame=datetime.now().strftime("%Y-%m-%d"),
        os_teste=os_teste,
    )


@app.route("/cadastro")
def cadastro():
    return redirect(url_for("paciente"))


@app.route("/salvar_paciente", methods=["POST"])
def salvar_paciente():
    if gravacao_bloqueada_por_banco():
        return mensagem_banco_obrigatorio(), 503

    os_numero = (request.form.get("os_numero") or request.form.get("rg") or "").strip()
    os_numero = re.sub(r"\D+", "", os_numero)
    if not os_numero:
        return redirect(url_for("paciente"), code=303)

    os_numero = os_numero.zfill(5)[-12:]
    nome = (request.form.get("nome") or f"OS {os_numero}").strip()
    rg = (request.form.get("rg") or os_numero).strip()
    data_nascimento = request.form.get("data_nascimento") or "1990-01-01"
    sexo = request.form.get("sexo") or "outro"
    idade = request.form.get("idade", type=int)
    telefone = request.form.get("telefone") or ""
    data_exame = request.form.get("data_exame") or datetime.now().strftime("%Y-%m-%d")

    if idade is None:
        idade = calcular_idade_por_data(data_nascimento) or 0

    conn = get_db()
    cursor = conn.cursor()

    paciente_id = inserir_retornando_id(cursor, """
        INSERT INTO pacientes
        (nome, rg, os_numero, data_nascimento, sexo, idade, telefone, data_exame)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        nome,
        rg,
        os_numero,
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
        "os_numero": os_numero,
        "nome": nome,
        "rg": rg,
        "data_nascimento": data_nascimento,
        "sexo": sexo,
        "idade": idade,
        "telefone": telefone,
        "data_exame": data_exame,
    })

    return redirect(url_for("medicao", paciente_id=paciente_id), code=303)


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
    paciente = None

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

    if paciente:
        faixa, dp_min, dp_max, _, _ = faixa_dp_paciente(paciente)
    elif idade is not None:
        faixa, dp_min, dp_max, _, _ = faixa_dp_paciente({
            "sexo": sexo,
            "idade": idade,
        })

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
        "face_count": dados_medicao.get("face_count", 0),
        "face_ok": dados_medicao.get("face_ok", False),
        "faixa": faixa,
        "idade": idade,
        "sexo": sexo,
        "dp_min": dp_min,
        "dp_max": dp_max,
        "status_dp": status_dp,
        **qualidade_atual(),
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
        "face_count": dados_medicao.get("face_count", 0),
        "face_ok": dados_medicao.get("face_ok", False),
        **qualidade_atual(),
    })


@app.route("/reset_captura_engine", methods=["POST"])
def reset_captura_engine():
    resetar_medicao()
    return {"status": "ok"}


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

    modo_local = os.getenv("VISIONAI_LOCAL_MODE", "0") == "1"
    min_capturas = env_int("VISIONAI_MIN_BATCH_CAPTURES", env_int("VISIONAI_UI_TOTAL_CAPTURES", 1 if modo_local else 4))
    max_erro_lote = env_float("VISIONAI_MAX_BATCH_ERRO_MM", 1.8 if modo_local else 2.0)
    max_desvio_lote = env_float("VISIONAI_MAX_BATCH_STD_MM", 1.0 if modo_local else 1.1)

    if len(medicoes) < min_capturas:
        return {
            "status": "erro",
            "msg": f"Capture pelo menos {min_capturas} leituras estaveis antes de finalizar.",
        }

    conn = get_db()
    cursor = conn.cursor()
    ods = gerar_ods(cursor)

    dps = []
    dnps_e = []
    dnps_d = []
    scores = []
    capturas_csv = []
    imagens_salvas = []
    capturas_preparadas = []

    try:
        for medicao_item in medicoes:
            dp = float(medicao_item["dp"])
            dnp_e = float(medicao_item["dnp_e"])
            dnp_d = float(medicao_item["dnp_d"])
            score = float(medicao_item["score"])
            imagem = medicao_item["imagem"]
            qualidade = {
                campo: numero_opcional((medicao_item.get("qualidade") or {}).get(campo))
                for campo in QUALIDADE_CAMPOS
            }
            qualidade = {campo: valor for campo, valor in qualidade.items() if valor is not None}

            if min(dp, dnp_e, dnp_d, score) <= 0:
                raise ValueError("Medicao invalida")

            capturas_preparadas.append({
                "dp": dp,
                "dnp_e": dnp_e,
                "dnp_d": dnp_d,
                "score": score,
                "imagem": imagem,
                "qualidade": qualidade,
            })

            dps.append(dp)
            dnps_e.append(dnp_e)
            dnps_d.append(dnp_d)
            scores.append(score)
    except (KeyError, TypeError, ValueError):
        conn.close()
        return {"status": "erro", "msg": "Lote de medicoes invalido. Repita a captura."}

    usar_mediana = os.getenv("VISIONAI_USE_MEDIAN_RESULT", "1" if modo_local else "0") == "1"
    media = float(np.median(dps) if usar_mediana else np.mean(dps))
    dnp_e_media = float(np.median(dnps_e) if usar_mediana else np.mean(dnps_e))
    dnp_d_media = float(np.median(dnps_d) if usar_mediana else np.mean(dnps_d))
    score_medio = float(np.mean(scores))
    desvio = float(np.std(dps))
    erro_max = float(max([abs(valor - media) for valor in dps]))
    qualidade_resumo = resumir_qualidade(capturas_preparadas)
    min_score_geometrico = env_float("VISIONAI_MIN_BATCH_GEOMETRY_SCORE", 65 if modo_local else 0)
    score_geometrico = qualidade_resumo.get("score_geometrico")
    min_iris_px = env_float("VISIONAI_MIN_CAPTURE_IRIS_PX", 10.0 if modo_local else 0)
    max_iris_px = env_float("VISIONAI_MAX_CAPTURE_IRIS_PX", 14.5 if modo_local else 0)
    iris_px_lote = [
        numero_opcional((item.get("qualidade") or {}).get("iris_px"))
        for item in capturas_preparadas
    ]
    iris_px_lote = [valor for valor in iris_px_lote if valor is not None]
    iris_min = min(iris_px_lote) if iris_px_lote else None
    iris_max = max(iris_px_lote) if iris_px_lote else None

    if min_score_geometrico > 0 and score_geometrico is not None and score_geometrico < min_score_geometrico:
        conn.close()
        return {
            "status": "erro",
            "msg": (
                "A geometria da captura ficou baixa. "
                "Refaca com apenas o paciente no quadro, rosto centralizado e cabeca reta."
            ),
            "score_geometrico": round(score_geometrico, 1),
        }

    if min_iris_px > 0 and iris_min is not None and iris_min < min_iris_px:
        conn.close()
        return {
            "status": "erro",
            "msg": "O rosto ficou longe da camera. Aproxime um pouco e refaca.",
            "iris_px": round(iris_min, 1),
            "iris_px_min": round(min_iris_px, 1),
        }

    if max_iris_px > 0 and iris_max is not None and iris_max > max_iris_px:
        conn.close()
        return {
            "status": "erro",
            "msg": (
                "O rosto ficou muito perto da camera. "
                "Afaste um pouco o tablet e refaca."
            ),
            "iris_px": round(iris_max, 1),
            "iris_px_max": round(max_iris_px, 1),
        }

    if erro_max > max_erro_lote or desvio > max_desvio_lote:
        conn.close()
        return {
            "status": "erro",
            "msg": (
                "As leituras variaram demais. "
                "Refaca a medicao com o paciente parado e rosto centralizado."
            ),
            "erro_max": round(erro_max, 2),
            "desvio": round(desvio, 2),
        }

    cursor.execute("SELECT * FROM pacientes WHERE id=?", (paciente_id,))
    paciente_calibracao = cursor.fetchone()
    if not paciente_calibracao:
        conn.close()
        return {"status": "erro", "msg": "Paciente nao encontrado. Cadastre novamente."}

    sexo_calibracao, faixa_calibracao = perfil_calibracao_paciente(paciente_calibracao)
    calibracao = obter_calibracao_facial(cursor, sexo_calibracao, faixa_calibracao)
    usar_calibracao = calibracao_pronta(
        calibracao,
        env_int("VISIONAI_MIN_CALIBRATION_SAMPLES", 3),
        env_float("VISIONAI_MAX_CALIBRATION_FACTOR_DELTA", 0.08),
        env_float("VISIONAI_MAX_CALIBRATION_ERROR_MM", 1.2),
    )

    dp_final = aplicar_calibracao_valor(media, calibracao.get("fator_dp"), usar_calibracao)
    dnp_e_final = aplicar_calibracao_valor(dnp_e_media, calibracao.get("fator_dnp_e"), usar_calibracao)
    dnp_d_final = aplicar_calibracao_valor(dnp_d_media, calibracao.get("fator_dnp_d"), usar_calibracao)

    _, dp_min_ideal, dp_max_ideal, dp_min_seguro, dp_max_seguro = faixa_dp_paciente(paciente_calibracao)
    dp_fora_ideal = not (dp_min_ideal <= dp_final <= dp_max_ideal)
    dnp_diferenca = abs(dnp_e_final - dnp_d_final)
    yaw_medio = qualidade_resumo.get("yaw")
    yaw_abs = abs(float(yaw_medio)) if yaw_medio is not None else 0
    max_dnp_diferenca = env_float("VISIONAI_MAX_DNP_DIFF_MM", 5.0)
    max_yaw_aprovacao = env_float("VISIONAI_MAX_APPROVAL_YAW", 4.5)
    revisar_assimetria = dnp_diferenca > max_dnp_diferenca
    revisar_pose = yaw_abs > max_yaw_aprovacao
    validar_faixa = os.getenv("VISIONAI_VALIDATE_DP_RANGE", "1" if modo_local else "0") == "1"
    if validar_faixa and not (dp_min_seguro <= dp_final <= dp_max_seguro):
        conn.close()
        return {
            "status": "erro",
            "msg": (
                f"DP fora da faixa segura ({dp_final:.1f} mm). "
                "Refaca a medicao com o rosto centralizado e distancia correta."
            ),
            "dp": round(dp_final, 2),
            "dp_original": round(media, 2),
            "dp_min": dp_min_ideal,
            "dp_max": dp_max_ideal,
        }

    os.makedirs("static/fotos", exist_ok=True)

    for medicao_item in capturas_preparadas:
        img_data = base64.b64decode(medicao_item["imagem"].split(",", 1)[1])
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        caminho = f"static/fotos/paciente_{paciente_id}_{timestamp}.jpg"

        with open(caminho, "wb") as arquivo:
            arquivo.write(img_data)

        dp = medicao_item["dp"]
        dnp_e = medicao_item["dnp_e"]
        dnp_d = medicao_item["dnp_d"]
        score = medicao_item["score"]
        imagens_salvas.append(caminho)
        capturas_csv.append({
            "dp": dp,
            "dnp_e": dnp_e,
            "dnp_d": dnp_d,
            "score": score,
            "qualidade": medicao_item.get("qualidade") or {},
            "foto": caminho,
        })

    calibracao_aplicada = {
        "sexo": sexo_calibracao,
        "faixa": faixa_calibracao,
        "amostras": calibracao.get("amostras", 0),
        "fator_dp": round(float(calibracao.get("fator_dp") or 1), 5),
        "fator_dnp_e": round(float(calibracao.get("fator_dnp_e") or 1), 5),
        "fator_dnp_d": round(float(calibracao.get("fator_dnp_d") or 1), 5),
        "aplicada": usar_calibracao,
        "dp_original": round(media, 2),
        "dnp_e_original": round(dnp_e_media, 2),
        "dnp_d_original": round(dnp_d_media, 2),
    }

    if erro_max > 2:
        status = "REPROVADO"
    elif dp_fora_ideal or revisar_assimetria or revisar_pose:
        status = "REVISAR"
    else:
        status = "APROVADO"
    validacao = {
        "media": round(media, 2),
        "desvio": round(desvio, 3),
        "erro_max": round(erro_max, 2),
        "metodo": "mediana" if usar_mediana else "media",
        "qualidade": qualidade_resumo,
        "dnp_diferenca": round(dnp_diferenca, 2),
        "yaw_abs": round(yaw_abs, 2),
        "revisar_assimetria": revisar_assimetria,
        "revisar_pose": revisar_pose,
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
