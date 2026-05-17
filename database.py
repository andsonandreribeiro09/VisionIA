import sqlite3

def conectar():

    conn = sqlite3.connect("visionai.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # =====================================================
    # 🧑‍⚕️ PACIENTES
    # =====================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pacientes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT,
        idade INTEGER,
        telefone TEXT,
        data_exame TEXT,
        foto TEXT
    )
    """)

    # =====================================================
    # 👓 RECEITAS
    # =====================================================
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

    # =====================================================
    # 🛒 PEDIDOS
    # =====================================================
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

    # =====================================================
    # 🕶️ ARMAÇÕES
    # =====================================================
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

    # =====================================================
    # 📊 MEDIÇÕES (CORE 🔥)
    # =====================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS medicoes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paciente_id INTEGER,
        dp REAL,
        dnp_e REAL,
        dnp_d REAL,
        score REAL,
        data TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (paciente_id) REFERENCES pacientes(id)
    )
    """)

    # =====================================================
    # 🔄 MIGRAÇÕES SEGURAS
    # =====================================================

    # ---------- PACIENTES ----------
    cursor.execute("PRAGMA table_info(pacientes)")
    colunas = [col[1] for col in cursor.fetchall()]

    if "foto" not in colunas:
        cursor.execute("ALTER TABLE pacientes ADD COLUMN foto TEXT")

    if "rg" not in colunas:
        cursor.execute("ALTER TABLE pacientes ADD COLUMN rg TEXT")

    if "data_nascimento" not in colunas:
        cursor.execute("ALTER TABLE pacientes ADD COLUMN data_nascimento TEXT")

    if "sexo" not in colunas:
        cursor.execute("ALTER TABLE pacientes ADD COLUMN sexo TEXT")

    # ---------- MEDICOES ----------
    cursor.execute("PRAGMA table_info(medicoes)")
    colunas = [col[1] for col in cursor.fetchall()]

    if "validacao_json" not in colunas:
        cursor.execute("ALTER TABLE medicoes ADD COLUMN validacao_json TEXT")

    if "historico_json" not in colunas:
        cursor.execute("ALTER TABLE medicoes ADD COLUMN historico_json TEXT")

    if "foto_captura" not in colunas:
        cursor.execute("ALTER TABLE medicoes ADD COLUMN foto_captura TEXT")

    if "caminho_imagem" not in colunas:
        cursor.execute("ALTER TABLE medicoes ADD COLUMN caminho_imagem TEXT")

    if "score" not in colunas:
        cursor.execute("ALTER TABLE medicoes ADD COLUMN score REAL")

    if "data" not in colunas:
        cursor.execute("ALTER TABLE medicoes ADD COLUMN data TEXT")

    # =====================================================
    # ⚡ ÍNDICES (PERFORMANCE)
    # =====================================================
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_medicoes_paciente
    ON medicoes(paciente_id)
    """)

    # =====================================================
    # 💾 FINALIZA
    # =====================================================
    conn.commit()

    return conn