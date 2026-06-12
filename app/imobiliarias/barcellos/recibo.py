# ---------------------------------------------------------------------------
# Extração de taxas — RECIBO
# ---------------------------------------------------------------------------
import re

from app.imobiliarias.barcellos.normalizar_taxas import _normalizar_taxa


def _extrair_taxas_recibo(texto):
    linhas      = texto.strip().split('\n')
    texto_taxas = ''
    lendo       = False
    parcelas_re = re.compile(r'(\d{1,2})\s*/\s*(\d{1,2})')

    for linha in linhas:
        linha = linha.strip()
        if linha.upper() == 'TAXAS':
            lendo = True
            continue
        if lendo and (linha.startswith('MENSAGENS') or linha.startswith('DEMONSTRATIVO')):
            break
        if lendo:
            texto_taxas += ' ' + linha

    texto_taxas = re.sub(r'\([^)]*\)', '', texto_taxas)
    taxas = []

    for nome, valor in re.findall(r'([A-ZÀ-Úa-zà-ú\s/0-9-]+?)\s+(\d+(?:[.,]\d{2}))', texto_taxas):
        nome = nome.strip().replace('FDO', 'FUNDO')
        nome = re.sub(r'\s+', ' ', nome)


        parcela_atual = total_parcelas = 1
        pm = parcelas_re.search(nome)
        if pm:
            parcela_atual  = int(pm.group(1))
            total_parcelas = int(pm.group(2))
            nome = parcelas_re.sub('', nome).strip()

        taxas.append({
            'taxa': _normalizar_taxa(nome),                                   
            'valor': valor.replace('.', ','),
            'parcela_atual': parcela_atual,
            'total_parcelas': total_parcelas,
        })
    return taxas