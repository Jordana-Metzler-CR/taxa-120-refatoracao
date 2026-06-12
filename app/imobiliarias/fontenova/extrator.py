"""
Extração de dados dos PDFs da Fonte Nova.

A Fonte Nova gera PDFs em dois layouts distintos:

  - LAYOUT ANTIGO (virtualimobi)
  - LAYOUT NOVO (recibo pagador)

A função extrair_boleto() detecta o layout automaticamente e
despacha para o parser correto.
"""

import re
import shutil
from pathlib import Path
import pdfplumber
import pytesseract
from app.imobiliarias.fontenova.normalizar_taxas import _NORMALIZACOES_TAXA, _normalizar_taxa, _safe_search
from app.imobiliarias.fontenova.recibo_pagador import _extrair_campos_layout_novo, _extrair_taxas_layout_novo
from app.imobiliarias.fontenova.virtualimobi import _extrair_campos_layout_antigo, _extrair_taxas_layout_antigo

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

from app.classes.boleto import Boleto
from app.imobiliarias.fontenova.config import PASTA_PROCESSADOS
from app.utils.formatarCodigoBarras import extrai_valor_codigo_barras, extrai_vencimento, linha_digitavel_para_codigo_barras


# ---------------------------------------------------------------------------
# Extração de campos por layout
# ---------------------------------------------------------------------------
def _detectar_layout(texto: str) -> str:
    if re.search(r'RECIBO DO PAGADOR', texto, re.IGNORECASE):
        return 'novo'
    return 'antigo'


def _extrair_texto_pdf(caminho: Path, logger) -> str:
    """
    Tenta extrair texto via pdfplumber. Se o texto for vazio ou muito curto
    (PDF vetorial sem texto extraível), renderiza a página como imagem usando
    o próprio pdfplumber e aplica OCR com Tesseract.
    Não depende de Poppler — apenas pdfplumber + pytesseract.
    """
    with pdfplumber.open(caminho) as pdf:
        texto = "\n".join(page.extract_text() or "" for page in pdf.pages)

        if len(texto.strip()) > 100:
            return texto

        logger.sucesso("Extração dos Dados", "PDF sem texto — aplicando OCR.")
        paginas_ocr = []
        for page in pdf.pages:
            pil_img = page.to_image(resolution=200).original
            paginas_ocr.append(pytesseract.image_to_string(pil_img, lang='por', config="--psm 6"))
        return "\n".join(paginas_ocr)
# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------
def extrair_boleto(caminho_pdf: Path, logger) -> Boleto:
    """
    Lê um PDF da Fonte Nova, detecta o layout automaticamente e
    retorna um Boleto com todos os campos extraídos.
    Se o PDF for escaneado (sem texto), aplica OCR automaticamente.
    Move o arquivo para PASTA_PROCESSADOS ao final.
    """
    caminho_pdf  = Path(caminho_pdf)
    nome_arquivo = caminho_pdf.name
    logger.sucesso("Extração dos Dados", f"Iniciando extração do boleto {nome_arquivo}")

    texto  = _extrair_texto_pdf(caminho_pdf, logger)
    layout = _detectar_layout(texto)
    logger.sucesso("Extração dos Dados", f"Layout detectado: {layout}")

    if layout == 'novo':
        campos = _extrair_campos_layout_novo(texto)
        taxas  = _extrair_taxas_layout_novo(texto)
    else:
        campos = _extrair_campos_layout_antigo(texto)
        taxas  = _extrair_taxas_layout_antigo(texto)

    cnpj_imob = _safe_search(
        r'FONTE\s+NOV\s*A\s+IMOVEIS\s+(?:L\s*TDA|LTDA)\s*(?:CNPJ\s*:)?\s*[-–]?\s*'
        r'(\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2})',
        texto)
    if cnpj_imob:
        cnpj_imob = re.sub(r'\D', '', cnpj_imob)

    # Tenta código de barras direto (47 dígitos) — layout antigo
    codigo_barras = _safe_search(r'(\d{47})', texto)
    # Tenta linha digitável — layout novo
    linha_dig = _safe_search(
        r'(\d{5}\.\d{5}\s+\d{5}\.\d{6}\s+\d{5}\.\d{6}\s+\d{1}\s+\d{14})',
        texto)
    
    if linha_dig:
        compt = extrai_vencimento(linha_dig)
        clean_codigo = re.sub(r'\D', '', linha_dig)
        valor_bruto = extrai_valor_codigo_barras(clean_codigo)
        try:
            codigo_barras = linha_digitavel_para_codigo_barras(linha_dig)
        except Exception:
            codigo_barras = None

    valor_total   =  valor_bruto
    if taxas:
        for t in taxas:
            t['taxa'] = _normalizar_taxa(t['taxa']) 
            logger.sucesso("Extração dos Dados", f"Taxa encontrada: {t.get('taxa')} — Valor: {t.get('valor')}")
    else:
        logger.erro("Extração dos Dados", "Nenhuma taxa encontrada no boleto Fonte Nova.")

    campos_validacao = {
        "CNPJ": cnpj_imob, "Competência": compt,
        "Código de Barras": codigo_barras, "Nome do Prédio": campos['nome_predio'],
        "Vencimento": compt, "Complemento": campos['complemento'],
        "Nome Condômino": campos['nome_cond'], "Documento Condômino": campos['documento'],
        "Valor Total": valor_total, "Taxas": taxas,
    }
    faltando = [c for c, v in campos_validacao.items() if not v]
    if faltando:
        logger.erro("Extração dos Dados",
                    f"'{nome_arquivo}' — campos faltando: {', '.join(faltando)}")
    else:
        logger.sucesso("Extração dos Dados", f"'{nome_arquivo}' extraído com sucesso.")

    shutil.move(str(caminho_pdf), str(PASTA_PROCESSADOS / nome_arquivo))

    return Boleto(nome_arquivo, cnpj_imob, campos['endereco'], campos['complemento'],
                  taxas, valor_total, compt, codigo_barras,
                  campos['nome_predio'], campos['nome_cond'], campos['documento'],
                  compt)