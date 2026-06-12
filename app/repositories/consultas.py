"""
app/repositories/taxa_queries.py

Todas as queries das tabelas taxa_120_* em um único lugar.
Os serviços importam daqui — nenhum deles precisa escrever SQL.

Convenção de nomes:
  buscar_*    → SELECT (retorna dado ou None/lista)
  inserir_*   → INSERT
  atualizar_* → UPDATE
  upsert_*    → INSERT ou UPDATE conforme existência do registro
"""
from __future__ import annotations
import pandas as pd


# ──────────────────────────────────────────────────────────────────────────────
# taxa_120_administradoras
# ──────────────────────────────────────────────────────────────────────────────

def buscar_id_administradora(cursor, cnpj: str) -> int | None:
    """Retorna o id da administradora pelo CNPJ, ou None se não existir."""
    cursor.execute(
        "SELECT id FROM taxa_120_administradoras WHERE cnpj = %s",
        (cnpj,)
    )
    row = cursor.fetchone()
    return row[0] if row else None


# ──────────────────────────────────────────────────────────────────────────────
# taxa_120_taxas
# ──────────────────────────────────────────────────────────────────────────────

def buscar_tabela_taxas(cursor, cnpj: str) -> list[tuple]:
    """
    Retorna lista de (taxa_id, descricao_taxa) para a administradora do CNPJ.
    Usada em lancar_taxas para resolver o cod_taxa de cada linha do boleto.
    """
    cursor.execute(
        """
        SELECT t.taxa_id, t.descricao_taxa
        FROM taxa_120_taxas t
        INNER JOIN taxa_120_administradoras a ON t.id_administradora = a.id
        WHERE a.cnpj = %s
        """,
        (cnpj,)
    )
    return cursor.fetchall()


# ──────────────────────────────────────────────────────────────────────────────
# taxa_120_imoveis
# ──────────────────────────────────────────────────────────────────────────────

def buscar_cod_imovel_de_para(cursor, nome_predio: str, endereco_imovel: str,
                               complemento: str, nome_condomino: str,
                               id_adm: int) -> tuple | None:
    """
    Usada em de_para para verificar se o imóvel já tem mapeamento salvo.
    Retorna a tupla bruta (cod_imovel,) ou None — consistente com o upsert_imovel
    que salva endereco como '' quando None.
    """
    cursor.execute(
        """
        SELECT cod_imovel FROM taxa_120_imoveis
        WHERE condominio      = %s
          AND endereco        = %s
          AND complemento     = %s
          AND nome_locador    = %s
          AND id_administradora = %s
        LIMIT 1
        """,
        (nome_predio, endereco_imovel or "",
         complemento, nome_condomino, id_adm)
    )
    return cursor.fetchone()


def buscar_cod_imovel_lancar_taxas(cursor, id_administradora: int,
                                    condominio: str, endereco: str,
                                    complemento: str, nome_locador: str) -> float | None:
    """
    Usada em lancar_taxas para recuperar o cod_imovel antes de lançar as taxas.
    Retorna o valor escalar ou None — usa or '' igual ao upsert_imovel.
    """
    cursor.execute(
        """
        SELECT cod_imovel FROM taxa_120_imoveis
        WHERE id_administradora = %s
          AND condominio         = %s
          AND endereco           = %s
          AND complemento        = %s
          AND nome_locador       = %s
        LIMIT 1
        """,
        (id_administradora, condominio, endereco or "",
         complemento, nome_locador)
    )
    row = cursor.fetchone()
    return row[0] if row else None


def buscar_imovel_por_cod(cursor, cod_imovel: float) -> bool:
    """Verifica se já existe um registro para o cod_imovel. Retorna True/False."""
    cursor.execute(
        "SELECT id FROM taxa_120_imoveis WHERE cod_imovel = %s",
        (cod_imovel,)
    )
    return cursor.fetchone() is not None


def inserir_imovel(cursor, id_administradora: int, cod_imovel: float,
                   boleto, documento_locador: str) -> None:
    cursor.execute(
        """
        INSERT INTO taxa_120_imoveis
            (id_administradora, cod_imovel, condominio, endereco,
             complemento, nome_locador, documento_locador)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (id_administradora, cod_imovel, boleto.nome_predio,
         boleto.endereco_imovel or "", boleto.complemento,
         boleto.nome_condomino, documento_locador)
    )


def atualizar_imovel(cursor, cod_imovel: float, boleto,
                     documento_locador: str) -> None:
    cursor.execute(
        """
        UPDATE taxa_120_imoveis
        SET condominio        = %s,
            endereco          = %s,
            complemento       = %s,
            nome_locador      = %s,
            documento_locador = %s
        WHERE cod_imovel = %s
        """,
        (boleto.nome_predio, boleto.endereco_imovel or "",
         boleto.complemento, boleto.nome_condomino,
         documento_locador, cod_imovel)
    )


def upsert_imovel(cursor, id_administradora: int, cod_imovel: float,
                  boleto, documento_locador: str) -> None:
    """INSERT ou UPDATE conforme a existência do cod_imovel."""
    if buscar_imovel_por_cod(cursor, cod_imovel):
        atualizar_imovel(cursor, cod_imovel, boleto, documento_locador)
    else:
        inserir_imovel(cursor, id_administradora, cod_imovel, boleto, documento_locador)


# ──────────────────────────────────────────────────────────────────────────────
# taxa_120_boletos
# ──────────────────────────────────────────────────────────────────────────────

def inserir_boleto(cursor, nome_boleto: str, cod_imovel: float,
                   competencia: str) -> None:
    cursor.execute(
        """
        INSERT INTO taxa_120_boletos (nome_boleto, cod_imovel, competencia)
        VALUES (%s, %s, %s)
        """,
        (nome_boleto, cod_imovel, competencia)
    )


# ──────────────────────────────────────────────────────────────────────────────
# logs_taxa_120
# ──────────────────────────────────────────────────────────────────────────────

def buscar_logs(conn) -> pd.DataFrame:
    """
    Retorna DataFrame com todos os logs do dia atual.
    Usado em dispararEmail para gerar o relatório técnico.
    """
    return pd.read_sql(
        "SELECT * FROM logs_taxa_120 WHERE data_e_horario::date = CURRENT_DATE;",
        conn
    )