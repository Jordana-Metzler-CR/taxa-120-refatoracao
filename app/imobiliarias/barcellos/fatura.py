# ---------------------------------------------------------------------------
# Extração de taxas — FATURA
# ---------------------------------------------------------------------------
import re

from app.imobiliarias.barcellos.normalizar_taxas import _normalizar_taxa



def _extrair_taxas_fatura(texto):
    linhas     = texto.split('\n')
    taxas      = []
    lendo      = False
    valor_re   = re.compile(r'(\d{1,3}(?:\.\d{3})*,\d{2})')
    parcelas_re = re.compile(r'(\d{1,2})/(\d{1,2})$')

    for linha in linhas:
        linha = linha.strip()
        if not lendo:
            if re.search(r'Descrição\s+Valor', linha):
                lendo = True
            continue
        if re.match(r'^TOTAL', linha):
            break

        matches = list(valor_re.finditer(linha))
        if not matches:
            continue

        ultimo = matches[-1]
        valor  = ultimo.group(1)
        nome   = linha[:ultimo.start()].strip()

        parcela_atual = total_parcelas = 1
        pm = parcelas_re.search(nome)
        if pm:
            parcela_atual  = int(pm.group(1))
            total_parcelas = int(pm.group(2))
            nome = parcelas_re.sub('', nome).strip()

        taxas.append({
            'taxa': _normalizar_taxa(nome),                    
            'valor': valor,
            'parcela_atual': parcela_atual,
            'total_parcelas': total_parcelas,
        })
    return taxas

