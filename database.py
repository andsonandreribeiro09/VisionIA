import os
import sqlite3
from datetime import datetime

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # Keeps local SQLite dev working before dependencies are installed.
    psycopg = None
    dict_row = None


POSTGRES_PREFIXES = ("postgres://", "postgresql://")


def postgres_disponivel():
    database_url = os.getenv("DATABASE_URL", "").strip()
    return database_url.lower().startswith(POSTGRES_PREFIXES)


def postgres_obrigatorio():
    return os.getenv("VISIONAI_REQUIRE_DATABASE_URL", "0") == "1"


def postgres_obrigatorio_ausente():
    return postgres_obrigatorio() and not postgres_disponivel()


def database_backend():
    return "postgresql" if postgres_disponivel() else "sqlite"


def database_config():
    if postgres_disponivel():
        return {
            "backend": "postgresql",
            "persistente": True,
            "label": "PostgreSQL Render",
            "bloquear_gravacao": False,
        }

    return {
        "backend": "sqlite",
        "persistente": False,
        "label": "PostgreSQL nao configurado" if postgres_obrigatorio_ausente() else "SQLite local",
        "bloquear_gravacao": postgres_obrigatorio_ausente(),
    }


def is_postgres_connection(conn):
    return isinstance(conn, PostgresConnection)


def is_postgres_cursor(cursor):
    return isinstance(cursor, PostgresCursor)


def adaptar_sql_postgres(sql):
    return (
        sql.replace("datetime('now')", "CURRENT_TIMESTAMP")
        .replace("date('now')", "CURRENT_DATE")
        .replace("?", "%s")
    )


class PostgresCursor:
    backend = "postgres"

    def __init__(self, cursor):
        self._cursor = cursor
        self.lastrowid = None

    def execute(self, sql, params=None):
        self._cursor.execute(adaptar_sql_postgres(sql), params)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def description(self):
        return self._cursor.description

    def close(self):
        return self._cursor.close()

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class PostgresConnection:
    backend = "postgres"

    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return PostgresCursor(self._conn.cursor())

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


def conectar():
    if postgres_disponivel():
        return conectar_postgres()
    return conectar_sqlite()


def conectar_sqlite():
    db_path = os.getenv("VISIONAI_DB_PATH", "visionai.db")
    db_dir = os.path.dirname(db_path)

    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    preparar_banco(conn, "sqlite")
    return conn


def conectar_postgres():
    if psycopg is None:
        raise RuntimeError("Instale psycopg[binary] para usar o PostgreSQL.")

    raw_conn = psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)
    conn = PostgresConnection(raw_conn)
    preparar_banco(conn, "postgres")
    return conn


def sql_medicoes_hoje():
    if postgres_disponivel():
        return """
            SELECT COUNT(*) AS total
            FROM medicoes
            WHERE LEFT(COALESCE(NULLIF(data, ''), CURRENT_DATE::text), 10) = TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD')
        """

    return """
        SELECT COUNT(*) AS total
        FROM medicoes
        WHERE date(COALESCE(data, 'now')) = date('now')
    """


def inserir_retornando_id(cursor, sql, params):
    if is_postgres_cursor(cursor):
        cursor.execute(f"{sql.strip()} RETURNING id", params)
        row = cursor.fetchone()
        return row["id"]

    cursor.execute(sql, params)
    return cursor.lastrowid


def preparar_banco(conn, backend):
    cursor = conn.cursor()

    if backend == "postgres":
        criar_tabelas_postgres(cursor)
    else:
        criar_tabelas_sqlite(cursor)

    migrar_colunas(cursor, backend)
    preencher_ods_faltantes(cursor)
    criar_indices(cursor)
    conn.commit()


def criar_tabelas_sqlite(cursor):
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pacientes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT,
        idade INTEGER,
        telefone TEXT,
        data_exame TEXT,
        foto TEXT,
        rg TEXT,
        data_nascimento TEXT,
        sexo TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS receitas(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paciente_id INTEGER,
        od_esf REAL,
        od_cil REAL,
        od_eixo INTEGER,
        oe_esf REAL,
        oe_cil REAL,
        oe_eixo INTEGER,
        adicao REAL,
        tipo_grau TEXT,
        data_criacao TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (paciente_id) REFERENCES pacientes(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pedidos(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paciente_id INTEGER,
        armacao INTEGER,
        dp REAL,
        dnp_dir REAL,
        dnp_esq REAL,
        FOREIGN KEY (paciente_id) REFERENCES pacientes(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS armacoes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        marca TEXT,
        modelo TEXT,
        material TEXT,
        tamanho INTEGER,
        valor REAL,
        imagem TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS medicoes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paciente_id INTEGER,
        ods TEXT,
        dp REAL,
        dnp_e REAL,
        dnp_d REAL,
        score REAL,
        data TEXT DEFAULT CURRENT_TIMESTAMP,
        validacao_json TEXT,
        historico_json TEXT,
        foto_captura TEXT,
        caminho_imagem TEXT,
        dp_original REAL,
        dnp_e_original REAL,
        dnp_d_original REAL,
        calibracao_json TEXT,
        FOREIGN KEY (paciente_id) REFERENCES pacientes(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS calibracao_facial(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sexo TEXT NOT NULL,
        faixa TEXT NOT NULL,
        fator_dp REAL DEFAULT 1,
        fator_dnp_e REAL DEFAULT 1,
        fator_dnp_d REAL DEFAULT 1,
        amostras INTEGER DEFAULT 0,
        erro_medio REAL DEFAULT 0,
        atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(sexo, faixa)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS calibracao_facial_amostras(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        medicao_id INTEGER,
        ods TEXT,
        paciente_id INTEGER,
        sexo TEXT,
        faixa TEXT,
        dp_camera REAL,
        dnp_e_camera REAL,
        dnp_d_camera REAL,
        dp_real REAL,
        dnp_e_real REAL,
        dnp_d_real REAL,
        fator_dp REAL,
        fator_dnp_e REAL,
        fator_dnp_d REAL,
        erro_dp REAL,
        erro_dnp_e REAL,
        erro_dnp_d REAL,
        criado_em TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)


def criar_tabelas_postgres(cursor):
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pacientes(
        id SERIAL PRIMARY KEY,
        nome TEXT,
        idade INTEGER,
        telefone TEXT,
        data_exame TEXT,
        foto TEXT,
        rg TEXT,
        data_nascimento TEXT,
        sexo TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS receitas(
        id SERIAL PRIMARY KEY,
        paciente_id INTEGER REFERENCES pacientes(id),
        od_esf REAL,
        od_cil REAL,
        od_eixo INTEGER,
        oe_esf REAL,
        oe_cil REAL,
        oe_eixo INTEGER,
        adicao REAL,
        tipo_grau TEXT,
        data_criacao TEXT DEFAULT (CURRENT_TIMESTAMP::text)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pedidos(
        id SERIAL PRIMARY KEY,
        paciente_id INTEGER REFERENCES pacientes(id),
        armacao INTEGER,
        dp REAL,
        dnp_dir REAL,
        dnp_esq REAL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS armacoes(
        id SERIAL PRIMARY KEY,
        marca TEXT,
        modelo TEXT,
        material TEXT,
        tamanho INTEGER,
        valor REAL,
        imagem TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS medicoes(
        id SERIAL PRIMARY KEY,
        paciente_id INTEGER REFERENCES pacientes(id),
        ods TEXT,
        dp REAL,
        dnp_e REAL,
        dnp_d REAL,
        score REAL,
        data TEXT DEFAULT (CURRENT_TIMESTAMP::text),
        validacao_json TEXT,
        historico_json TEXT,
        foto_captura TEXT,
        caminho_imagem TEXT,
        dp_original REAL,
        dnp_e_original REAL,
        dnp_d_original REAL,
        calibracao_json TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS calibracao_facial(
        id SERIAL PRIMARY KEY,
        sexo TEXT NOT NULL,
        faixa TEXT NOT NULL,
        fator_dp REAL DEFAULT 1,
        fator_dnp_e REAL DEFAULT 1,
        fator_dnp_d REAL DEFAULT 1,
        amostras INTEGER DEFAULT 0,
        erro_medio REAL DEFAULT 0,
        atualizado_em TEXT DEFAULT (CURRENT_TIMESTAMP::text),
        UNIQUE(sexo, faixa)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS calibracao_facial_amostras(
        id SERIAL PRIMARY KEY,
        medicao_id INTEGER,
        ods TEXT,
        paciente_id INTEGER,
        sexo TEXT,
        faixa TEXT,
        dp_camera REAL,
        dnp_e_camera REAL,
        dnp_d_camera REAL,
        dp_real REAL,
        dnp_e_real REAL,
        dnp_d_real REAL,
        fator_dp REAL,
        fator_dnp_e REAL,
        fator_dnp_d REAL,
        erro_dp REAL,
        erro_dnp_e REAL,
        erro_dnp_d REAL,
        criado_em TEXT DEFAULT (CURRENT_TIMESTAMP::text)
    )
    """)


def colunas_tabela(cursor, backend, tabela):
    if backend == "postgres":
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=?
        """, (tabela,))
        return {row["column_name"] for row in cursor.fetchall()}

    cursor.execute(f"PRAGMA table_info({tabela})")
    return {col[1] for col in cursor.fetchall()}


def migrar_colunas(cursor, backend):
    colunas_pacientes = colunas_tabela(cursor, backend, "pacientes")
    for nome, tipo in [
        ("foto", "TEXT"),
        ("rg", "TEXT"),
        ("data_nascimento", "TEXT"),
        ("sexo", "TEXT"),
    ]:
        if nome not in colunas_pacientes:
            cursor.execute(f"ALTER TABLE pacientes ADD COLUMN {nome} {tipo}")

    colunas_receitas = colunas_tabela(cursor, backend, "receitas")
    for nome, tipo in [
        ("tipo_grau", "TEXT"),
        ("data_criacao", "TEXT"),
    ]:
        if nome not in colunas_receitas:
            cursor.execute(f"ALTER TABLE receitas ADD COLUMN {nome} {tipo}")

    colunas_medicoes = colunas_tabela(cursor, backend, "medicoes")
    for nome, tipo in [
        ("validacao_json", "TEXT"),
        ("historico_json", "TEXT"),
        ("foto_captura", "TEXT"),
        ("caminho_imagem", "TEXT"),
        ("score", "REAL"),
        ("data", "TEXT"),
        ("ods", "TEXT"),
        ("dp_original", "REAL"),
        ("dnp_e_original", "REAL"),
        ("dnp_d_original", "REAL"),
        ("calibracao_json", "TEXT"),
    ]:
        if nome not in colunas_medicoes:
            cursor.execute(f"ALTER TABLE medicoes ADD COLUMN {nome} {tipo}")


def preencher_ods_faltantes(cursor):
    cursor.execute("""
        SELECT id, data
        FROM medicoes
        WHERE ods IS NULL OR ods = ''
        ORDER BY COALESCE(data, ''), id
    """)
    medicoes_sem_ods = cursor.fetchall()
    proximos_ods = {}

    def proximo_ods(ano):
        if ano not in proximos_ods:
            cursor.execute("""
                SELECT ods
                FROM medicoes
                WHERE ods LIKE ?
                ORDER BY ods DESC
                LIMIT 1
            """, (f"ODS-{ano}-%",))
            ultimo = cursor.fetchone()
            numero = 1

            if ultimo and ultimo["ods"]:
                try:
                    numero = int(ultimo["ods"].split("-")[-1]) + 1
                except (ValueError, IndexError):
                    numero = 1

            proximos_ods[ano] = numero

        while True:
            ods = f"ODS-{ano}-{proximos_ods[ano]:06d}"
            proximos_ods[ano] += 1
            cursor.execute("SELECT 1 FROM medicoes WHERE ods=? LIMIT 1", (ods,))
            if cursor.fetchone() is None:
                return ods

    for medicao in medicoes_sem_ods:
        data = medicao["data"] or ""
        ano = data[:4] if len(data) >= 4 and data[:4].isdigit() else str(datetime.now().year)
        cursor.execute(
            "UPDATE medicoes SET ods=? WHERE id=?",
            (proximo_ods(ano), medicao["id"])
        )


def criar_indices(cursor):
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_medicoes_paciente
    ON medicoes(paciente_id)
    """)

    cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_medicoes_ods
    ON medicoes(ods)
    WHERE ods IS NOT NULL
    """)
