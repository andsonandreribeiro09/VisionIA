import json
import os
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from database import sql_medicoes_hoje
from flask import Flask, redirect, render_template, request

from visionai_shared import (
    database_config,
    fator_calibracao_valido,
    get_db,
    is_postgres_cursor,
    limpar_csv_pacientes_medicoes,
    obter_calibracao_facial,
    perfil_calibracao_paciente,
    recalcular_calibracao_facial,
    remover_arquivos_vinculados,
    remover_fotos_pacientes,
    remover_paciente_do_csv,
)


app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))


def redirect_laboratorio(**params):
    query = urlencode({chave: valor for chave, valor in params.items() if valor})
    return redirect(f"/laboratorio?{query}" if query else "/laboratorio")


def parse_data_metricas(valor):
    if not valor:
        return None

    if isinstance(valor, datetime):
        return valor.date()

    if isinstance(valor, date):
        return valor

    texto = str(valor).strip()
    if not texto:
        return None

    texto = texto.replace("T", " ").replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(texto).date()
    except ValueError:
        pass

    for formato in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto[:26], formato).date()
        except ValueError:
            continue

    return None


def status_medicao(registro):
    validacao = {}
    if registro.get("validacao_json"):
        try:
            validacao = json.loads(registro["validacao_json"])
        except json.JSONDecodeError:
            validacao = {}

    return validacao.get("status") or registro.get("status_validacao") or "PENDENTE"


def percentual(valor, total):
    if not total:
        return 0
    return round((valor / total) * 100, 1)


def numero_metricas(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


@app.route("/")
def root():
    return redirect("/laboratorio")


@app.route("/healthz")
def healthz():
    config_banco = database_config()
    return {
        "status": "ok",
        "app": "laboratorio",
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
            "database": config_banco["backend"],
            "database_persistente": config_banco["persistente"],
            "pacientes": pacientes_total,
            "medicoes": medicoes_total,
        }
    except Exception as exc:
        return {
            "status": "error",
            "database": config_banco["backend"],
            "database_persistente": config_banco["persistente"],
            "error": str(exc),
        }, 500


@app.route("/laboratorio")
def laboratorio():
    busca = (request.args.get("q") or "").strip()
    mensagem = request.args.get("msg")
    erro = request.args.get("erro")
    config_banco = database_config()

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS total FROM pacientes")
    total_pacientes = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM medicoes")
    total_medicoes = cursor.fetchone()["total"]

    cursor.execute(sql_medicoes_hoje())
    medicoes_hoje = cursor.fetchone()["total"]

    cursor.execute("SELECT AVG(score) AS media FROM medicoes WHERE score IS NOT NULL")
    score_medio = cursor.fetchone()["media"] or 0

    cursor.execute("""
        SELECT id, nome, rg, telefone, sexo, data_nascimento, idade, data_exame, foto
        FROM pacientes
        ORDER BY id DESC
        LIMIT 300
    """)
    todos_pacientes = cursor.fetchall()

    cursor.execute("""
        SELECT m.*, p.nome, p.rg, p.telefone, p.sexo, p.data_nascimento, p.idade, p.data_exame, p.foto
        FROM medicoes m
        LEFT JOIN pacientes p ON p.id = m.paciente_id
        ORDER BY COALESCE(m.data, '') DESC, m.id DESC
        LIMIT 500
    """)
    todas_medicoes = cursor.fetchall()

    def preparar_registro(registro, tem_medicao):
        item = dict(registro)
        validacao = {}

        if item.get("validacao_json"):
            try:
                validacao = json.loads(item["validacao_json"])
            except json.JSONDecodeError:
                validacao = {}

        item["tem_medicao"] = tem_medicao
        item["status_validacao"] = validacao.get("status", "PENDENTE") if tem_medicao else "SEM MEDIÇÃO"
        item["erro_max"] = validacao.get("erro_max", "")
        item["desvio"] = validacao.get("desvio", "")
        qualidade = validacao.get("qualidade") or {}
        item["score_geometrico"] = qualidade.get("score_geometrico")
        item["ambiente_score"] = qualidade.get("ambiente_score")
        item["yaw"] = qualidade.get("yaw")
        item["pitch"] = qualidade.get("pitch")
        item["roll"] = qualidade.get("roll")
        item["distancia_cm"] = qualidade.get("distancia_cm")
        item["iris_px"] = qualidade.get("iris_px")
        item["centro_face_offset"] = qualidade.get("centro_face_offset")
        item["brilho"] = qualidade.get("brilho")
        item["contraste"] = qualidade.get("contraste")
        item["nitidez"] = qualidade.get("nitidez")
        item["busca_link"] = item.get("ods") or item.get("rg") or item.get("nome") or item.get("paciente_id")
        return item

    medicoes_preparadas = [preparar_registro(m, True) for m in todas_medicoes]
    ultima_medicao_por_paciente = {}
    for medicao in medicoes_preparadas:
        paciente_id = medicao.get("paciente_id")
        if paciente_id and paciente_id not in ultima_medicao_por_paciente:
            ultima_medicao_por_paciente[paciente_id] = medicao

    pacientes_sem_medicao = []
    for paciente in todos_pacientes:
        if paciente["id"] in ultima_medicao_por_paciente:
            continue

        pacientes_sem_medicao.append(preparar_registro({
            "id": None,
            "paciente_id": paciente["id"],
            "ods": None,
            "nome": paciente.get("nome"),
            "rg": paciente.get("rg"),
            "telefone": paciente.get("telefone"),
            "sexo": paciente.get("sexo"),
            "data_nascimento": paciente.get("data_nascimento"),
            "idade": paciente.get("idade"),
            "data_exame": paciente.get("data_exame"),
            "data": paciente.get("data_exame"),
            "foto": paciente.get("foto"),
            "caminho_imagem": paciente.get("foto"),
            "dp": None,
            "dnp_e": None,
            "dnp_d": None,
            "score": None,
            "dp_original": None,
            "dnp_e_original": None,
            "dnp_d_original": None,
            "validacao_json": None,
            "historico_json": None,
        }, False))

    registros_laboratorio = medicoes_preparadas + pacientes_sem_medicao
    aprovadas = sum(1 for m in medicoes_preparadas if m["status_validacao"] == "APROVADO")
    revisar = sum(1 for m in medicoes_preparadas if m["status_validacao"] != "APROVADO")

    resultados = registros_laboratorio
    if busca:
        termo = busca.lower()
        resultados = [
            m for m in registros_laboratorio
            if termo in (m.get("ods") or "").lower()
            or termo in (m.get("nome") or "").lower()
            or termo in (m.get("rg") or "").lower()
            or termo == str(m.get("paciente_id") or "")
        ]

    medicao_selecionada = None
    if busca:
        medicao_selecionada = next(
            (m for m in resultados if (m.get("ods") or "").lower() == busca.lower()),
            resultados[0] if len(resultados) == 1 else None,
        )

    conn.close()

    return render_template(
        "laboratorio.html",
        busca=busca,
        mensagem=mensagem,
        erro=erro,
        resultados=resultados[:80],
        recentes=medicoes_preparadas[:8],
        medicao=medicao_selecionada,
        banco=config_banco,
        stats={
            "total_pacientes": total_pacientes,
            "total_medicoes": total_medicoes,
            "medicoes_hoje": medicoes_hoje,
            "pacientes_sem_medicao": len(pacientes_sem_medicao),
            "aprovadas": aprovadas,
            "revisar": revisar,
            "score_medio": round(score_medio, 1),
        },
    )


@app.route("/laboratorio/metricas")
def laboratorio_metricas():
    config_banco = database_config()
    hoje = datetime.now().date()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    inicio_mes = hoje.replace(day=1)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, nome, rg, telefone, sexo, data_exame
        FROM pacientes
        ORDER BY id DESC
    """)
    pacientes = [dict(p) for p in cursor.fetchall()]

    cursor.execute("""
        SELECT m.*, p.nome, p.rg, p.telefone, p.sexo, p.data_exame
        FROM medicoes m
        LEFT JOIN pacientes p ON p.id = m.paciente_id
        ORDER BY COALESCE(m.data, '') DESC, m.id DESC
    """)
    medicoes = [dict(m) for m in cursor.fetchall()]
    conn.close()

    for paciente in pacientes:
        paciente["data_base"] = parse_data_metricas(paciente.get("data_exame"))

    for medicao in medicoes:
        medicao["data_base"] = parse_data_metricas(medicao.get("data"))
        medicao["status_validacao"] = status_medicao(medicao)

    medidos = {m.get("paciente_id") for m in medicoes if m.get("paciente_id")}
    pacientes_sem_medicao = [p for p in pacientes if p.get("id") not in medidos]

    aprovadas = sum(1 for m in medicoes if m["status_validacao"] == "APROVADO")
    revisar = sum(1 for m in medicoes if m["status_validacao"] != "APROVADO")
    score_valores = [valor for valor in (numero_metricas(m.get("score")) for m in medicoes) if valor is not None]
    score_medio = round(sum(score_valores) / len(score_valores), 1) if score_valores else 0

    def no_periodo(registro, inicio=None, fim=None):
        data_base = registro.get("data_base")
        if not data_base:
            return False
        if inicio and data_base < inicio:
            return False
        if fim and data_base > fim:
            return False
        return True

    periodos_config = [
        ("Hoje", hoje, hoje),
        ("Semana", inicio_semana, hoje),
        ("Mês", inicio_mes, hoje),
        ("Total", None, None),
    ]

    periodos = []
    for nome, inicio, fim in periodos_config:
        pacientes_periodo = [p for p in pacientes if no_periodo(p, inicio, fim)] if inicio else pacientes
        medicoes_periodo = [m for m in medicoes if no_periodo(m, inicio, fim)] if inicio else medicoes
        sem_medicao_periodo = [p for p in pacientes_sem_medicao if no_periodo(p, inicio, fim)] if inicio else pacientes_sem_medicao
        aprovadas_periodo = sum(1 for m in medicoes_periodo if m["status_validacao"] == "APROVADO")
        revisar_periodo = sum(1 for m in medicoes_periodo if m["status_validacao"] != "APROVADO")

        periodos.append({
            "nome": nome,
            "pacientes": len(pacientes_periodo),
            "medicoes": len(medicoes_periodo),
            "aprovadas": aprovadas_periodo,
            "revisar": revisar_periodo,
            "sem_medicao": len(sem_medicao_periodo),
        })

    dias = [hoje - timedelta(days=indice) for indice in range(13, -1, -1)]
    medicoes_por_dia = {dia: 0 for dia in dias}
    pacientes_por_dia = {dia: 0 for dia in dias}

    for medicao in medicoes:
        if medicao.get("data_base") in medicoes_por_dia:
            medicoes_por_dia[medicao["data_base"]] += 1

    for paciente in pacientes:
        if paciente.get("data_base") in pacientes_por_dia:
            pacientes_por_dia[paciente["data_base"]] += 1

    maior_dia = max([1] + list(medicoes_por_dia.values()) + list(pacientes_por_dia.values()))
    grafico_dias = [
        {
            "label": dia.strftime("%d/%m"),
            "medicoes": medicoes_por_dia[dia],
            "pacientes": pacientes_por_dia[dia],
            "altura_medicoes": max(4, percentual(medicoes_por_dia[dia], maior_dia)),
            "altura_pacientes": max(4, percentual(pacientes_por_dia[dia], maior_dia)),
        }
        for dia in dias
    ]

    meses = []
    ano, mes = hoje.year, hoje.month
    for _ in range(6):
        meses.append((ano, mes))
        mes -= 1
        if mes == 0:
            mes = 12
            ano -= 1
    meses.reverse()

    medicoes_por_mes = {f"{ano:04d}-{mes:02d}": 0 for ano, mes in meses}
    for medicao in medicoes:
        data_base = medicao.get("data_base")
        if not data_base:
            continue
        chave = f"{data_base.year:04d}-{data_base.month:02d}"
        if chave in medicoes_por_mes:
            medicoes_por_mes[chave] += 1

    maior_mes = max([1] + list(medicoes_por_mes.values()))
    grafico_meses = [
        {
            "label": f"{mes:02d}/{ano}",
            "valor": medicoes_por_mes[f"{ano:04d}-{mes:02d}"],
            "altura": max(4, percentual(medicoes_por_mes[f"{ano:04d}-{mes:02d}"], maior_mes)),
        }
        for ano, mes in meses
    ]

    total_status = len(medicoes) + len(pacientes_sem_medicao)
    status_barras = [
        {"nome": "Aprovadas", "classe": "ok", "valor": aprovadas, "percentual": percentual(aprovadas, total_status)},
        {"nome": "Revisar", "classe": "warn", "valor": revisar, "percentual": percentual(revisar, total_status)},
        {
            "nome": "Sem medição",
            "classe": "neutral",
            "valor": len(pacientes_sem_medicao),
            "percentual": percentual(len(pacientes_sem_medicao), total_status),
        },
    ]

    return render_template(
        "laboratorio_metricas.html",
        banco=config_banco,
        stats={
            "total_pacientes": len(pacientes),
            "total_medicoes": len(medicoes),
            "medicoes_hoje": periodos[0]["medicoes"],
            "medicoes_semana": periodos[1]["medicoes"],
            "medicoes_mes": periodos[2]["medicoes"],
            "aprovadas": aprovadas,
            "revisar": revisar,
            "sem_medicao": len(pacientes_sem_medicao),
            "score_medio": score_medio,
        },
        periodos=periodos,
        grafico_dias=grafico_dias,
        grafico_meses=grafico_meses,
        status_barras=status_barras,
        ultimas_medicoes=medicoes[:12],
        sem_medicao_recentes=pacientes_sem_medicao[:12],
    )


@app.route("/laboratorio/excluir-paciente", methods=["POST"])
def laboratorio_excluir_paciente():
    paciente_id = request.form.get("paciente_id", type=int)
    confirmacao = (request.form.get("confirmacao") or "").strip()

    if not paciente_id:
        return redirect_laboratorio(erro="Paciente invalido para exclusao.")

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM pacientes WHERE id=?", (paciente_id,))
        paciente = cursor.fetchone()

        if not paciente:
            conn.close()
            return redirect_laboratorio(erro="Paciente nao encontrado.")

        nome = (paciente.get("nome") or "").strip()
        if confirmacao != nome:
            conn.close()
            return redirect_laboratorio(
                q=request.form.get("retorno_q"),
                erro="Para excluir, digite o nome do paciente exatamente como aparece no painel.",
            )

        cursor.execute("""
            SELECT caminho_imagem, foto_captura
            FROM medicoes
            WHERE paciente_id=?
        """, (paciente_id,))
        fotos_medicoes = cursor.fetchall()

        caminhos = [paciente.get("foto")]
        for foto in fotos_medicoes:
            caminhos.extend([foto.get("caminho_imagem"), foto.get("foto_captura")])

        cursor.execute("DELETE FROM calibracao_facial_amostras WHERE paciente_id=?", (paciente_id,))
        cursor.execute("DELETE FROM medicoes WHERE paciente_id=?", (paciente_id,))
        cursor.execute("DELETE FROM pedidos WHERE paciente_id=?", (paciente_id,))
        cursor.execute("DELETE FROM receitas WHERE paciente_id=?", (paciente_id,))
        cursor.execute("DELETE FROM pacientes WHERE id=?", (paciente_id,))
        recalcular_calibracao_facial(cursor)
        conn.commit()

        remover_paciente_do_csv(paciente_id)
        remover_arquivos_vinculados(caminhos)

        conn.close()
        return redirect_laboratorio(msg=f"Paciente {nome} e dados vinculados foram excluidos.")

    except Exception:
        conn.rollback()
        conn.close()
        return redirect_laboratorio(erro="Nao foi possivel excluir o paciente. Tente novamente.")


@app.route("/laboratorio/limpar-banco", methods=["POST"])
def laboratorio_limpar_banco():
    confirmacao = (request.form.get("confirmacao") or "").strip()

    if confirmacao != "LIMPAR BANCO":
        return redirect_laboratorio(erro="Digite LIMPAR BANCO para confirmar a limpeza total.")

    conn = get_db()
    cursor = conn.cursor()

    try:
        if is_postgres_cursor(cursor):
            cursor.execute("""
                TRUNCATE TABLE
                    calibracao_facial_amostras,
                    calibracao_facial,
                    medicoes,
                    pedidos,
                    receitas,
                    pacientes
                RESTART IDENTITY CASCADE
            """)
        else:
            cursor.execute("DELETE FROM calibracao_facial_amostras")
            cursor.execute("DELETE FROM calibracao_facial")
            cursor.execute("DELETE FROM medicoes")
            cursor.execute("DELETE FROM pedidos")
            cursor.execute("DELETE FROM receitas")
            cursor.execute("DELETE FROM pacientes")
            for tabela in [
                "calibracao_facial_amostras",
                "calibracao_facial",
                "medicoes",
                "pedidos",
                "receitas",
                "pacientes",
            ]:
                cursor.execute("DELETE FROM sqlite_sequence WHERE name=?", (tabela,))

        conn.commit()
        conn.close()
        limpar_csv_pacientes_medicoes()
        remover_fotos_pacientes()
        return redirect_laboratorio(msg="Banco limpo. Pacientes, medicoes e calibracoes foram zerados.")

    except Exception:
        conn.rollback()
        conn.close()
        return redirect_laboratorio(erro="Nao foi possivel limpar o banco. Tente novamente.")


@app.route("/laboratorio/calibracao", methods=["GET", "POST"])
def laboratorio_calibracao():
    mensagem = None
    erro = None
    busca = (request.values.get("ods") or "").strip()

    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        try:
            dp_real = float(request.form.get("dp_real", 0) or 0)
            dnp_e_real = float(request.form.get("dnp_e_real", 0) or 0)
            dnp_d_real = float(request.form.get("dnp_d_real", 0) or 0)

            cursor.execute("""
                SELECT m.*, p.nome, p.sexo, p.idade, p.data_nascimento
                FROM medicoes m
                LEFT JOIN pacientes p ON p.id = m.paciente_id
                WHERE m.ods=?
                LIMIT 1
            """, (busca,))
            medicao_post = cursor.fetchone()

            if not medicao_post:
                erro = "ODS nao encontrado."
            else:
                dp_camera = float(medicao_post.get("dp_original") or medicao_post.get("dp") or 0)
                dnp_e_camera = float(medicao_post.get("dnp_e_original") or medicao_post.get("dnp_e") or 0)
                dnp_d_camera = float(medicao_post.get("dnp_d_original") or medicao_post.get("dnp_d") or 0)

                if min(dp_real, dnp_e_real, dnp_d_real, dp_camera, dnp_e_camera, dnp_d_camera) <= 0:
                    erro = "Preencha medidas reais validas para DP, DNP E e DNP D."
                else:
                    fator_dp = dp_real / dp_camera
                    fator_dnp_e = dnp_e_real / dnp_e_camera
                    fator_dnp_d = dnp_d_real / dnp_d_camera

                    sexo, faixa = perfil_calibracao_paciente(medicao_post)
                    usar_no_fator = all(fator_calibracao_valido(f) for f in [fator_dp, fator_dnp_e, fator_dnp_d])
                    usada_no_fator = 1 if usar_no_fator else 0
                    status_amostra = "usada" if usar_no_fator else "historico"
                    motivo_amostra = "" if usar_no_fator else "fora_margem_segura"

                    erro_dp = abs(dp_real - dp_camera)
                    erro_dnp_e = abs(dnp_e_real - dnp_e_camera)
                    erro_dnp_d = abs(dnp_d_real - dnp_d_camera)
                    erro_max = max(erro_dp, erro_dnp_e, erro_dnp_d)

                    if usar_no_fator:
                        cursor.execute("""
                            UPDATE calibracao_facial_amostras
                            SET usada_no_fator=0,
                                status='substituida',
                                motivo='substituida_por_nova_amostra'
                            WHERE medicao_id=? AND COALESCE(usada_no_fator, 1)=1
                        """, (medicao_post.get("id"),))

                    cursor.execute("""
                        INSERT INTO calibracao_facial_amostras
                        (medicao_id, ods, paciente_id, sexo, faixa,
                         dp_camera, dnp_e_camera, dnp_d_camera,
                         dp_real, dnp_e_real, dnp_d_real,
                         fator_dp, fator_dnp_e, fator_dnp_d,
                         erro_dp, erro_dnp_e, erro_dnp_d, erro_max,
                         usada_no_fator, status, motivo)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        medicao_post.get("id"),
                        medicao_post.get("ods"),
                        medicao_post.get("paciente_id"),
                        sexo,
                        faixa,
                        dp_camera,
                        dnp_e_camera,
                        dnp_d_camera,
                        dp_real,
                        dnp_e_real,
                        dnp_d_real,
                        fator_dp,
                        fator_dnp_e,
                        fator_dnp_d,
                        erro_dp,
                        erro_dnp_e,
                        erro_dnp_d,
                        erro_max,
                        usada_no_fator,
                        status_amostra,
                        motivo_amostra,
                    ))

                    recalcular_calibracao_facial(cursor)
                    atualizada = obter_calibracao_facial(cursor, sexo, faixa)
                    total_ativo = int(atualizada.get("amostras") or 0)

                    cursor.execute("""
                        UPDATE medicoes
                        SET calibracao_json=?
                        WHERE id=?
                    """, (
                        json.dumps({
                            "amostra_manual_salva": True,
                            "usada_no_fator": bool(usada_no_fator),
                            "status": status_amostra,
                            "motivo": motivo_amostra,
                            "dp_real": dp_real,
                            "dnp_e_real": dnp_e_real,
                            "dnp_d_real": dnp_d_real,
                            "fator_dp": fator_dp,
                            "fator_dnp_e": fator_dnp_e,
                            "fator_dnp_d": fator_dnp_d,
                            "erro_max": erro_max,
                            "sexo": sexo,
                            "faixa": faixa,
                        }, ensure_ascii=False),
                        medicao_post.get("id"),
                    ))

                    conn.commit()
                    if usar_no_fator:
                        mensagem = f"Amostra salva no historico e aplicada ao fator ativo de {sexo} / {faixa}. Amostras ativas: {total_ativo}."
                    else:
                        mensagem = "Amostra manual salva no historico de auditoria, mas nao aplicada ao fator ativo por estar fora da margem segura."

        except ValueError:
            erro = "Digite apenas numeros nas medidas reais."

    medicao = None
    if busca:
        cursor.execute("""
            SELECT m.*, p.nome, p.rg, p.sexo, p.idade, p.data_nascimento
            FROM medicoes m
            LEFT JOIN pacientes p ON p.id = m.paciente_id
            WHERE m.ods=?
            LIMIT 1
        """, (busca,))
        medicao = cursor.fetchone()

    cursor.execute("SELECT * FROM calibracao_facial ORDER BY faixa, sexo")
    calibracoes = cursor.fetchall()

    cursor.execute("""
        SELECT *
        FROM calibracao_facial_amostras
        ORDER BY id DESC
        LIMIT 20
    """)
    amostras = cursor.fetchall()

    conn.close()

    return render_template(
        "laboratorio_calibracao.html",
        busca=busca,
        medicao=medicao,
        calibracoes=calibracoes,
        amostras=amostras,
        mensagem=mensagem,
        erro=erro,
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
