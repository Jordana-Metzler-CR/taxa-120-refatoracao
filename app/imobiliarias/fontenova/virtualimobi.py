"""LAYOUT ANTIGO (virtualimobi): tabela de duas colunas lado a lado
    - Cabeçalho: "Histórico Valor Histórico Valor"
    - Taxas intercaladas em duas colunas na mesma linha
"""
import re

from app.imobiliarias.fontenova.normalizar_taxas import _safe_search
from app.imobiliarias.fontenova.normalizar_taxas import _limpar_documento, _normalizar_taxa


# ---------------------------------------------------------------------------
# layout ANTIGO — duas colunas (virtualimobi)
# ---------------------------------------------------------------------------
def _extrair_taxas_layout_antigo(texto: str) -> list:
    """
    Isola o bloco entre 'Histórico Valor Histórico Valor' e 'Total até o vencimento',
    lineariza as duas colunas e consome token a token.
    """
    inicio = re.search(r'Histórico\s+Valor\s+Histórico\s+Valor', texto, re.IGNORECASE)
    fim    = re.search(r'Total\s+até\s+o\s+vencimento', texto, re.IGNORECASE)
    if not inicio or not fim:
        return []

    linha = texto[inicio.end():fim.start()].replace('\n', ' ')

    # Normaliza CONDOMINIO
    linha = re.sub(
        r'(CONDOM[IÍ]NIO)\s*(?:[-–—]\s*)?(?:(?:BLOCO\s+)?[A-Z\.])?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
        r'CONDOMINIO \2',
        linha, flags=re.IGNORECASE
    )
    # GÁS com CONDOMINIO embutido
    linha = re.sub(
        r'G[ÁA]S\s*[-–—]?\s*Leituras:.*?Dt\.?ant:\d{2}/\d{2}/\d{2}\s*'
        r'CONDOM[IÍ]NIO\s*(\d{1,3}(?:\.\d{3})*,\d{2})\s*'
        r'(\d{1,3}(?:\.\d{3})*,\d{2})\s*atual:\d{2}/\d{2}/\d{2}',
        r'CONDOMINIO \1 GÁS \2',
        linha, flags=re.IGNORECASE
    )
    # GÁS
    linha = re.sub(
        r'G[ÁA]S\s*[-–—]?\s*Leituras:.*?atual:\d{2}/\d{2}/\d{2}\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
        r'GÁS \1',
        linha, flags=re.IGNORECASE
    )
    # Valores negativos: (-)100,00 → -100,00
    linha = re.sub(r'\(-\)\s*(\d{1,3}(?:\.\d{3})*,\d{2})', r'-\1', linha)

    tokens     = linha.split()
    valor_re   = re.compile(r'^-?\d{1,3}(?:\.\d{3})*,\d{2}$')
    parcela_re = re.compile(r'^(\d{1,2})/(\d{1,2})$')
    taxas          = []
    nome_atual     = ""
    valor_atual    = None
    parcela_atual  = 1
    total_parcelas = 1
    extraiu        = False

    for token in tokens:
        if not nome_atual:
            nome_atual = token
            continue
        if valor_re.match(token):
            valor_atual = token
            extraiu     = True
            continue
        if parcela_re.match(token):
            pm = parcela_re.match(token)
            if not valor_atual:
                parcela_atual, total_parcelas = int(pm.group(1)), int(pm.group(2))
                extraiu = True
            else:
                parcela_atual, total_parcelas = int(pm.group(1)), int(pm.group(2))
                taxas.append({
                    'taxa': _normalizar_taxa(nome_atual.strip()),
                    'valor': valor_atual.strip(),
                    'parcela_atual': parcela_atual,
                    'total_parcelas': total_parcelas,
                })
                nome_atual = ""; valor_atual = None
                parcela_atual = total_parcelas = 1; extraiu = False
            continue
        if extraiu and valor_atual:
            taxas.append({
                'taxa': _normalizar_taxa(nome_atual.strip()),
                'valor': valor_atual.strip(),
                'parcela_atual': parcela_atual,
                'total_parcelas': total_parcelas,
            })
            nome_atual = token; valor_atual = None
            parcela_atual = total_parcelas = 1; extraiu = False
            continue
        if not extraiu:
            nome_atual += " " + token

    if nome_atual and valor_atual:
        taxas.append({
            'taxa': _normalizar_taxa(nome_atual.strip()),
            'valor': valor_atual.strip(),
            'parcela_atual': parcela_atual,
            'total_parcelas': total_parcelas,
        })
    return taxas

def _extrair_campos_layout_antigo(texto: str) -> dict:
    nome_predio = _safe_search(r'CONDOM[IÍ]NIO\s*[:\-]?\s*\d+\s*-\s*([A-Z.\s]+?)\s*(?:\n|$)', texto)
    endereco    = _safe_search(r'CONDOM[IÍ]NIO[^\r\n]*[\r\n]+([A-ZÁÉÍÓÚÃÕÇ\s,.]+?,\s*\d+)', texto)
    nome_cond   = _safe_search(r'COND[ÔO]MINO\s*[:\-]?\s*[\r\n]*([A-ZÁÉÍÓÚÃÕÇ.\s\/\-]+?)\s*(?:UNIDADE|COMPETÊNCIA|$)', texto)
    complemento = _safe_search(r'UNIDADE\s*:\s*[\r\n]*([A-Z0-9.\s\-]+?)\s*(?:COMPETÊNCIA|$)', texto)
    competencia = _safe_search(r'Compet[eê]ncia\s*[:\-]?\s*(\d{2}\/\d{4})', texto) or 'extra'
    vencimento  = _safe_search(r'Vencimento:\s*(\d{2}/\d{2}/\d{4})', texto)
    documento   = _limpar_documento(_safe_search(r'CPF\/?CNPJ\s*[:\-]?\s*([0-9\s.\-\/\*]+)', texto))
    return dict(nome_predio=nome_predio, endereco=endereco, nome_cond=nome_cond,
                complemento=complemento, competencia=competencia,
                vencimento=vencimento, documento=documento)

