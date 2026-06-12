"""
Orquestrador do fluxo de lançamento de taxas.
Etapas:
  1. _preparar_pdfs()      → app/service/tunel.py
  2. registrar_relacao_de_para() → app/service/de_para.py
  3. _abrir_banco()        → conexão + queries iniciais
  4. login + loop + logout → app/service/imobiliar.py
       processar_boleto()  → app/service/processar_boleto.py
  5. _finalizar_relatorio() → gerar excel + enviar e-mail
"""
from datetime import datetime

from app.config import env
from app.core.logger_service import LoggerService
from app.repositories.db_logger import DBLogger
from app.imobiliarias import registry
from app.service.de_para import registrar_relacao_de_para
from app.service.tunel import preparar_pdfs
from app.service.processar_boleto import processar_boleto
from app.service import imobiliar
from app.utils.dispararEmail import enviarEmailRelatorio
from app.utils.normalizacao import normalizar_competencia
from app.utils.relatorio import RelatorioOperacional
from app.repositories.conexao import conectar_banco
from app.repositories.consultas import buscar_tabela_taxas, buscar_id_administradora


# ---------------------------------------------------------------------------
# Orquestrador
# ---------------------------------------------------------------------------
def _criar_logger():
    db_logger = DBLogger(
        host=env("DB_HOST"), port=env("DB_PORT"),
        dbname=env("DB_BANCO"), user=env("DB_USER"), password=env("DB_SENHA")
    )
    return LoggerService(db_logger)


def _abrir_banco(cnpj: str) -> tuple:
    """Abre conexão e busca dados iniciais. Retorna (conn, cursor, tabela_taxas, id_administradora)."""
    conn   = conectar_banco()
    cursor = conn.cursor()
    return conn, cursor, buscar_tabela_taxas(cursor, cnpj), buscar_id_administradora(cursor, cnpj)


def _finalizar_relatorio(cfg, relatorio: RelatorioOperacional, logger) -> None:
    arquivo = f"relatorio_taxa120_{datetime.now().strftime('%Y%m%d')}.xlsx"
    relatorio.gerar_excel(arquivo)
    enviarEmailRelatorio(cfg.NOME, arquivo)
    logger.sucesso("Relatório", f"Relatório '{arquivo}' gerado e enviado.")


# ---------------------------------------------------------------------------
# Ponto de entrada público
# ---------------------------------------------------------------------------
def lancar_taxas_imobiliar(cnpj: str):
    imob      = registry.get(cnpj)
    cfg       = imob["config"]
    logger    = _criar_logger()
    relatorio = RelatorioOperacional()

    processo_tunel = None
    conn           = None
    cursor         = None

    try:
        # 1. Infraestrutura
        processo_tunel, url_publica = preparar_pdfs(cfg, logger)

        # 2. DE-PARA
        boletos = registrar_relacao_de_para(cnpj, logger)
        if not boletos:
            logger.alerta("Lançamento", "Nenhum boleto para lançar.")
            return

        # 3. Banco
        conn, cursor, tabela_taxas, id_administradora = _abrir_banco(cnpj)

        # 4. Imobiliar — login + loop + logout
        session_id = imobiliar.login(logger)

        for boleto in boletos:
            competencia = normalizar_competencia(boleto.vencimento)
            if not competencia:
                logger.erro(
                    "Lançamento",
                    f"Competência não encontrada no boleto {boleto.nome_boleto}. Pulando."
                )
                continue

            processar_boleto(
                boleto, cursor, tabela_taxas, session_id,
                competencia, url_publica, logger, relatorio, id_administradora
            )

        imobiliar.logout(session_id, logger)
        logger.sucesso("Lançamento", f"Fluxo finalizado com sucesso às {datetime.now()}")

        # 5. Relatório
        _finalizar_relatorio(cfg, relatorio, logger)

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        if processo_tunel:
            processo_tunel.terminate()