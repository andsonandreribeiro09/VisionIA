import sqlite3

def conectar():

    conn = sqlite3.connect("visionai.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # -------------------------
    # TABELA PACIENTES
    # -------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pacientes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT,
        idade INTEGER,
        telefone TEXT,
        data_exame TEXT
    )
    """)

    # ✅ GARANTE COLUNA FOTO (MIGRAÇÃO SEGURA)
    cursor.execute("PRAGMA table_info(pacientes)")
    colunas = [col[1] for col in cursor.fetchall()]

    if "foto" not in colunas:
        cursor.execute("ALTER TABLE pacientes ADD COLUMN foto TEXT")

    # -------------------------
    # RECEITAS
    # -------------------------
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
        FOREIGN KEY (paciente_id) REFERENCES pacientes(id)
    )
    """)

    # -------------------------
    # PEDIDOS (armação escolhida)
    # -------------------------
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

    # -------------------------
    # ARMAÇÕES
    # -------------------------
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

    # -------------------------
    # MEDIÇÕES (NOVO 🔥)
    # -------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS medicoes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paciente_id INTEGER,
        dp REAL,
        dnp_e REAL,
        dnp_d REAL,
        score REAL,
        data TEXT,
        FOREIGN KEY (paciente_id) REFERENCES pacientes(id)
    )
    """)

    conn.commit()

    return conn