import os
import sqlite3

from database import conectar, postgres_disponivel


TABELAS = [
    "pacientes",
    "receitas",
    "pedidos",
    "armacoes",
    "medicoes",
    "calibracao_facial",
    "calibracao_facial_amostras",
]


def quote_ident(nome):
    return '"' + nome.replace('"', '""') + '"'


def sqlite_colunas(cursor, tabela):
    cursor.execute(f"PRAGMA table_info({quote_ident(tabela)})")
    return [row["name"] for row in cursor.fetchall()]


def postgres_colunas(cursor, tabela):
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=?
        ORDER BY ordinal_position
    """, (tabela,))
    return [row["column_name"] for row in cursor.fetchall()]


def copiar_tabela(sqlite_cursor, postgres_cursor, tabela):
    origem_colunas = sqlite_colunas(sqlite_cursor, tabela)
    destino_colunas = postgres_colunas(postgres_cursor, tabela)
    colunas = [coluna for coluna in origem_colunas if coluna in destino_colunas]

    if not colunas:
        return 0

    sqlite_cursor.execute(f"SELECT {', '.join(quote_ident(c) for c in colunas)} FROM {quote_ident(tabela)}")
    linhas = sqlite_cursor.fetchall()

    if not linhas:
        return 0

    placeholders = ", ".join("?" for _ in colunas)
    colunas_sql = ", ".join(quote_ident(coluna) for coluna in colunas)
    update_cols = [coluna for coluna in colunas if coluna != "id"]

    if update_cols:
        conflito = "DO UPDATE SET " + ", ".join(
            f"{quote_ident(coluna)}=EXCLUDED.{quote_ident(coluna)}"
            for coluna in update_cols
        )
    else:
        conflito = "DO NOTHING"

    sql = f"""
        INSERT INTO {quote_ident(tabela)} ({colunas_sql})
        VALUES ({placeholders})
        ON CONFLICT (id) {conflito}
    """

    for linha in linhas:
        postgres_cursor.execute(sql, tuple(linha[coluna] for coluna in colunas))

    return len(linhas)


def reajustar_sequence(cursor, tabela):
    cursor.execute(f"""
        SELECT setval(
            pg_get_serial_sequence('{tabela}', 'id'),
            COALESCE((SELECT MAX(id) FROM {quote_ident(tabela)}), 1),
            (SELECT MAX(id) IS NOT NULL FROM {quote_ident(tabela)})
        )
    """)


def main():
    if not postgres_disponivel():
        raise SystemExit("Defina DATABASE_URL com a External Database URL do Render antes de rodar.")

    sqlite_path = os.getenv("SQLITE_DB_PATH") or os.getenv("VISIONAI_DB_PATH") or "visionai.db"
    if not os.path.exists(sqlite_path):
        raise SystemExit(f"Banco SQLite nao encontrado: {sqlite_path}")

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    postgres_conn = conectar()
    postgres_cursor = postgres_conn.cursor()

    try:
        total = 0
        for tabela in TABELAS:
            copiados = copiar_tabela(sqlite_cursor, postgres_cursor, tabela)
            total += copiados
            print(f"{tabela}: {copiados} registro(s) copiado(s)")

        for tabela in TABELAS:
            reajustar_sequence(postgres_cursor, tabela)

        postgres_conn.commit()
        print(f"Migracao finalizada: {total} registro(s) enviados ao PostgreSQL.")
    except Exception:
        postgres_conn.rollback()
        raise
    finally:
        sqlite_conn.close()
        postgres_conn.close()


if __name__ == "__main__":
    main()
