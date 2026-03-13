import sqlite3

def conectar():

    conn = sqlite3.connect("visionai.db", check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pacientes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT,
        idade INTEGER,
        data_exame TEXT
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
        tipo_grau TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pedidos(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paciente_id INTEGER,
        armacao TEXT,
        dp REAL,
        dnp_dir REAL,
        dnp_esq REAL
    )
    """)

    conn.commit()

    return conn