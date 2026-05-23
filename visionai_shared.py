import csv
import json
import os
from datetime import datetime
from pathlib import Path

from database import (
    conectar,
    database_config,
    inserir_retornando_id,
    is_postgres_connection,
    is_postgres_cursor,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv("VISIONAI_DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)

CSV_PACIENTES_MEDICOES = os.path.join(DATA_DIR, "pacientes_medicoes.csv")
CSV_COLUNAS = [
    "paciente_id",
    "ods",
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
    if os.getenv("VISIONAI_DEBUG", "0") == "1":
        print(*args)


def get_db():
    conn = conectar()
    if not is_postgres_connection(conn):
        conn.row_factory = lambda cursor, row: {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
    return conn


def gravacao_bloqueada_por_banco():
    return database_config().get("bloquear_gravacao", False)


def mensagem_banco_obrigatorio():
    return (
        "Banco PostgreSQL nao configurado no Render. "
        "Configure DATABASE_URL no Web Service antes de cadastrar pacientes."
    )


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
    linhas = ler_linhas_csv()
    atualizada = False

    for linha in linhas:
        if linha.get("paciente_id") == paciente_id:
            linha.update({chave: valor for chave, valor in dados.items() if valor is not None})
            atualizada = True
            break

    if not atualizada:
        nova = {"paciente_id": paciente_id}
        nova.update(dados)
        linhas.append(nova)

    escrever_linhas_csv(linhas)


def remover_paciente_do_csv(paciente_id):
    paciente_id = str(paciente_id)
    linhas = [linha for linha in ler_linhas_csv() if linha.get("paciente_id") != paciente_id]
    escrever_linhas_csv(linhas)


def limpar_csv_pacientes_medicoes():
    escrever_linhas_csv([])


def carregar_paciente(paciente_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pacientes WHERE id=?", (paciente_id,))
    paciente = cursor.fetchone()
    conn.close()
    return paciente


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


def remover_arquivos_vinculados(caminhos):
    for caminho in caminhos:
        if not caminho:
            continue
        try:
            path = Path(caminho)
            if not path.is_absolute():
                path = Path(BASE_DIR) / path
            if path.exists() and path.is_file():
                path.unlink()
        except OSError:
            pass


def remover_fotos_pacientes():
    fotos_dir = Path(BASE_DIR) / "static" / "fotos"
    if not fotos_dir.exists():
        return

    for arquivo in fotos_dir.glob("paciente_*"):
        if arquivo.is_file():
            arquivo.unlink(missing_ok=True)


def gerar_ods(cursor):
    ano = datetime.now().year
    prefixo = f"ODS-{ano}-"

    cursor.execute("""
        SELECT ods
        FROM medicoes
        WHERE ods LIKE ?
        ORDER BY ods DESC
        LIMIT 1
    """, (f"{prefixo}%",))

    ultimo = cursor.fetchone()
    proximo = 1

    if ultimo and ultimo.get("ods"):
        try:
            proximo = int(ultimo["ods"].split("-")[-1]) + 1
        except (ValueError, IndexError):
            proximo = 1

    while True:
        ods = f"{prefixo}{proximo:06d}"
        cursor.execute("SELECT 1 FROM medicoes WHERE ods=? LIMIT 1", (ods,))
        if cursor.fetchone() is None:
            return ods
        proximo += 1


def calcular_idade_por_data(data_nascimento):
    if not data_nascimento:
        return None

    try:
        nascimento = datetime.strptime(data_nascimento, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None

    hoje = datetime.now()
    idade = hoje.year - nascimento.year
    if (hoje.month, hoje.day) < (nascimento.month, nascimento.day):
        idade -= 1
    return idade


def perfil_calibracao_paciente(paciente):
    sexo = ((paciente or {}).get("sexo") or "outro").lower().strip()
    idade = (paciente or {}).get("idade")

    if idade is None:
        idade = calcular_idade_por_data((paciente or {}).get("data_nascimento"))

    faixa = "crianca" if idade is not None and idade < 18 else "adulto"
    return sexo, faixa


def obter_calibracao_facial(cursor, sexo, faixa):
    cursor.execute("""
        SELECT *
        FROM calibracao_facial
        WHERE sexo=? AND faixa=?
        LIMIT 1
    """, (sexo, faixa))
    calibracao = cursor.fetchone()

    if not calibracao:
        return {
            "sexo": sexo,
            "faixa": faixa,
            "fator_dp": 1.0,
            "fator_dnp_e": 1.0,
            "fator_dnp_d": 1.0,
            "amostras": 0,
            "erro_medio": 0,
        }

    return calibracao


def fator_calibracao_aplicavel(fator, limite_delta=0.08):
    try:
        fator = float(fator or 1)
    except (TypeError, ValueError):
        return False
    return (1 - limite_delta) <= fator <= (1 + limite_delta)


def calibracao_pronta(calibracao, min_amostras=3, limite_delta=0.08, max_erro_medio=1.2):
    try:
        amostras = int((calibracao or {}).get("amostras") or 0)
        erro_medio = float((calibracao or {}).get("erro_medio") or 0)
    except (TypeError, ValueError):
        return False

    fatores = [
        (calibracao or {}).get("fator_dp"),
        (calibracao or {}).get("fator_dnp_e"),
        (calibracao or {}).get("fator_dnp_d"),
    ]

    return (
        amostras >= min_amostras
        and erro_medio <= max_erro_medio
        and all(fator_calibracao_aplicavel(fator, limite_delta) for fator in fatores)
    )


def aplicar_calibracao_valor(valor, fator, usar=True):
    fator_final = float(fator or 1) if usar else 1.0
    return round(float(valor or 0) * fator_final, 2)


def fator_calibracao_valido(fator):
    return 0.90 <= fator <= 1.10


def recalcular_calibracao_facial(cursor):
    cursor.execute("SELECT * FROM calibracao_facial_amostras ORDER BY id")
    amostras = cursor.fetchall()

    grupos = {}
    for amostra in amostras:
        chave = (amostra.get("sexo") or "outro", amostra.get("faixa") or "adulto")
        grupos.setdefault(chave, []).append(amostra)

    cursor.execute("DELETE FROM calibracao_facial")

    for (sexo, faixa), itens in grupos.items():
        if not itens:
            continue

        total = len(itens)
        fator_dp = sum(float(item.get("fator_dp") or 1) for item in itens) / total
        fator_dnp_e = sum(float(item.get("fator_dnp_e") or 1) for item in itens) / total
        fator_dnp_d = sum(float(item.get("fator_dnp_d") or 1) for item in itens) / total
        erro_medio = sum(
            max(
                float(item.get("erro_dp") or 0),
                float(item.get("erro_dnp_e") or 0),
                float(item.get("erro_dnp_d") or 0),
            )
            for item in itens
        ) / total

        cursor.execute("""
            INSERT INTO calibracao_facial
            (sexo, faixa, fator_dp, fator_dnp_e, fator_dnp_d, amostras, erro_medio, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            sexo,
            faixa,
            fator_dp,
            fator_dnp_e,
            fator_dnp_d,
            total,
            round(erro_medio, 3),
        ))


__all__ = [
    "DATA_DIR",
    "BASE_DIR",
    "aplicar_calibracao_valor",
    "calibracao_pronta",
    "calcular_idade_por_data",
    "carregar_paciente",
    "database_config",
    "debug_log",
    "fator_calibracao_valido",
    "gerar_ods",
    "get_db",
    "gravacao_bloqueada_por_banco",
    "inserir_retornando_id",
    "is_postgres_cursor",
    "limpar_csv_pacientes_medicoes",
    "mensagem_banco_obrigatorio",
    "obter_calibracao_facial",
    "perfil_calibracao_paciente",
    "recalcular_calibracao_facial",
    "registrar_medicao_no_csv",
    "registrar_paciente_no_csv",
    "remover_arquivos_vinculados",
    "remover_fotos_pacientes",
    "remover_paciente_do_csv",
]
