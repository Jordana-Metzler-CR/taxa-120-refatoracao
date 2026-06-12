"""
Responsável pela preparação do ambiente antes do lançamento:
  - Abertura e validação do túnel Cloudflare
  - Leitura do inbox de e-mail
  - Separação dos PDFs por página
"""
import requests
from time import sleep

from app.utils.separarPdfs import processar_pdfs
from app.utils.tunel import iniciar_tunel


def preparar_pdfs(cfg, logger) -> tuple:
    """
    Abre o túnel Cloudflare, valida a disponibilidade, lê o inbox
    e separa os PDFs da imobiliária.

    Retorna (processo_tunel, url_publica).
    Levanta Exception se qualquer etapa falhar.
    """
    processo_tunel, url_publica = iniciar_tunel()

    sleep(10)
    for tentativa in range(5):
        try:
            requests.get(url_publica, timeout=5)
            logger.sucesso("Túnel", f"Túnel ativo: {url_publica}")
            break
        except Exception:
            logger.alerta("Túnel", f"Túnel ainda não disponível, tentativa {tentativa + 1}/5...")
            sleep(5)
    else:
        raise Exception("Túnel Cloudflare não ficou disponível após 5 tentativas.")

    resp = requests.get("http://localhost:5001/email/inbox/boletos@creditoreal.com.br/read")
    if resp.status_code == 200:
        logger.sucesso("Leitura de E-mail", "Inbox lida com sucesso.")
    else:
        logger.erro("Leitura de E-mail", f"Erro ao ler inbox. Status: {resp.status_code}")
        raise Exception("Falha na leitura do e-mail.")

    pasta_origem = (
        rf"\\192.168.150.12\dados\CREDITO REAL\SETORES\INFORMATICA\RPA"
        rf"\boletoscreditoreal.com.br\{cfg.CAMINHO_IMOBILIAR}"
    )
    processar_pdfs(pasta_origem, cfg.PASTA_PDFS, logger)

    return processo_tunel, url_publica