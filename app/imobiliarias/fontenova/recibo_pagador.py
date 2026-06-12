"""  LAYOUT NOVO (recibo): coluna única, uma taxa por linha
    - Cabeçalho: "RECIBO DO PAGADOR"
    - Cada linha: NOME_TAXA [parcela] valor
"""

import re
from click import Path
import pdfplumber
from pytesseract import pytesseract
from app.imobiliarias.fontenova.normalizar_taxas import _safe_search
from app.imobiliarias.fontenova.normalizar_taxas import _limpar_documento, _normalizar_taxa



# ---------------------------------------------------------------------------
# layout NOVO — coluna única, uma taxa por linha
# ---------------------------------------------------------------------------

def _extrair_taxas_layout_novo(texto: str) -> list:
    """
    Lê linha a linha entre 'Demonstrativo da cobrança' e 'Total até o vencimento'.
    Cada linha tem: NOME_TAXA [parcela] valor
    O GÁS ocupa uma linha inteira com a descrição de leitura.
    """
    
    
    inicio = re.search(r'Demonstrativo da cobran', texto, re.IGNORECASE)
    fim = re.search(r'Total\s+até\s+o\s+vencimento', texto, re.IGNORECASE)
    if not fim:
        fim = re.search(r'Valor\s+do\s+desconto\s+até\s+o\s+vencimento', texto, re.IGNORECASE)
    if not inicio or not fim:
        return []


    bloco  = texto[inicio.end():fim.start()]
    linhas = [l.strip() for l in bloco.split('\n') if l.strip()]

    valor_re   = re.compile(r'(\d{1,3}(?:\.\d{3})*,\d{2})$')
    parcela_re = re.compile(r'(\d{1,2})/(\d{1,2})')
    gas_re     = re.compile(
        r'G[ÁA]S\s*[-–]?\s*Leituras:.*?atual:\s*\d{2}/\d{2}/\d{2}\s+(\d{1,3}(?:\.\d{3})*,\d{2})',
        re.IGNORECASE
    )

    taxas = []
    for linha in linhas:
        # GÁS com descrição longa
        m_gas = gas_re.search(linha)
        if m_gas:
            taxas.append({
                'taxa': 'GÁS',
                'valor': m_gas.group(1),
                'parcela_atual': 1,
                'total_parcelas': 1,
            })
            continue

        # Linha normal: termina com valor numérico
        m_val = valor_re.search(linha)
        if not m_val:
            continue

        valor = m_val.group(1)
        nome  = linha[:m_val.start()].strip()

        # Parcela embutida no nome (ex: "SEG. INCENDIO 05/6" ou "REFORMA FACHADA 1/60")
        parcela_atual = total_parcelas = 1
        m_par = parcela_re.search(nome)
        if m_par:
            parcela_atual  = int(m_par.group(1))
            total_parcelas = int(m_par.group(2))
            nome = nome[:m_par.start()].strip()

        if not nome:
            continue
        taxas.append({
            'taxa': _normalizar_taxa(nome),
            'valor': valor,
            'parcela_atual': parcela_atual,
            'total_parcelas': total_parcelas,
        })
    return taxas

def _extrair_campos_layout_novo(texto: str) -> dict:
    # nome_predio: para antes de VENCIMENTO ou V E N C I M E N T O ou \n
    nome_predio = _safe_search(
        r'Condom[íi]nio\s*:\s*\d+\s*-\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇa-záéíóúâêôãõç.\s]+?)'
        r'(?:\s+V(?:\s+E\s+N\s+C\s+I\s+M\s+E\s+N\s+T\s+O|ENCIMENTO)|\n)',
        texto)
    endereco    = _safe_search(
        r'Condom[íi]nio\s*:[^\n]+\n([A-ZÁÉÍÓÚÂÊÔÃÕÇa-záéíóúâêôãõç\s,.]+?,\s*\d+)',
        texto)
    # Condômino: pega tudo após o ":" até fim de linha (sem exigir data na mesma linha)
    nome_cond   = _safe_search(
        r'Cond[oô]mino\s*:\s*(.+?)(?:\s+\d{2}/\d{2}/\d{4})?\s*$',
        texto, flags=re.IGNORECASE | re.MULTILINE)
    complemento = _safe_search( r'Unidade\s*[:\-]?\s*([A-Za-z0-9 ]+?)\s*Compet\.', texto)
    competencia = _safe_search(r'Compet[êe]ncia\s*:\s*(\d{2}/\d{4})', texto) or 'extra'
    # Vencimento: tenta na linha do pagamento, depois na Unidade, depois em qualquer linha após Condômino
    vencimento  = _safe_search(r'PAGAMENTO EM[^\n]+\n(\d{2}/\d{2}/\d{4})', texto)
    if not vencimento:
        vencimento = _safe_search(r'Unidade\s*:[^\n]+(\d{2}/\d{2}/\d{4})', texto)
    if not vencimento:
        vencimento = _safe_search(r'Cond[oô]mino\s*:[^\n]+(\d{2}/\d{2}/\d{4})', texto)
    # Documento vem no rodapé: "NOME CPF/CNPJ:xxx"
    documento   = _limpar_documento(_safe_search(r'CPF/CNPJ:\s*([0-9\*\.\-\/]+)', texto))
    return dict(nome_predio=nome_predio, endereco=endereco, nome_cond=nome_cond,
                complemento=complemento, competencia=competencia,
                vencimento=vencimento, documento=documento)


