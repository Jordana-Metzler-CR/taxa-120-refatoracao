"""
app/service/processador_boleto.py

Contém toda a lógica de lançamento de um único boleto no Imobiliar:
  - Resolução do cod_imovel
  - Validação do condomínio
  - Consulta de contrato
  - Lançamento de cada taxa
  - Exclusão de previstos remanescentes
  - Associação da imagem do boleto
"""
from app.utils.normalizacao import normalizar_valor_monetario
from app.repositories.consultas import buscar_cod_imovel_lancar_taxas
from app.service import imobiliar

_TAXAS_IGNORADAS      = frozenset(['seguro conteudo', 'boleto registrado', 'porte'])
_TAXAS_REVISAO_MANUAL = frozenset(['multa', 'laudo pericial', 'desconto'])


def processar_boleto(boleto, cursor, tabela_taxas, session_id,
                     competencia, url_publica, logger, relatorio,
                     id_administradora=None):
    """
    Lança todas as taxas de um boleto no Imobiliar.

    Fluxo:
      1. Busca cod_imovel em taxa_120_imoveis
      2. Valida presença da taxa de condomínio
      3. Consulta contrato de locação
      4. Lança cada taxa (ignora/revisão manual conforme regras)
      5. Exclui previstos remanescentes
      6. Associa imagem do boleto
    """
    tipo_boleto = "E" if boleto.competencia == "extra" else "N"

    # ── Resolve cod_imovel ──────────────────────────────────────────────────
    cod_raw    = buscar_cod_imovel_lancar_taxas(
        cursor, id_administradora,
        boleto.nome_predio, boleto.endereco_imovel,
        boleto.complemento, boleto.nome_condomino
    )
    cod_imovel = int(cod_raw) if cod_raw else 0

    if cod_imovel == 0:
        msg = f"Necessário lançamento manual: não identificado o código de imóvel para {boleto.nome_boleto}."
        logger.alerta("Lançamento", f"Imóvel não mapeado para {boleto.nome_boleto}. Pulando.")
        relatorio.registrar(
            cod_imovel="NÃO MAPEADO",
            numero_taxa="",
            descricao_taxa=boleto.nome_boleto,
            valor="",
            status="Alerta",
            mensagem=msg,
        )
        return

    # ── Valida taxa de condomínio ────────────────────────────────────────────
    taxas_boleto = sorted(
        boleto.taxas,
        key=lambda t: 0 if "condominio" in t.get("taxa", "").lower() else 1
    )

    if not taxas_boleto or taxas_boleto[0].get("taxa", "").lower() != "condominio":
        msg = f"Revisão manual: não foi encontrada taxa de condomínio para {boleto.nome_boleto}."
        logger.alerta("Lançamento", f"{boleto.nome_boleto} sem taxa de condomínio. Revisão manual.")
        relatorio.registrar(
            cod_imovel=cod_imovel,
            numero_taxa="",
            descricao_taxa="Condomínio",
            valor="",
            status="Alerta",
            mensagem=msg,
        )
        return

    taxas_boleto[0]["valor"] = normalizar_valor_monetario(boleto.valor_total)

    # ── Consulta contrato ────────────────────────────────────────────────────
    resp_contrato = imobiliar.consultaContrato(session_id, cod_imovel)

    if not (resp_contrato["Header"]["Status"] == "Success" and not resp_contrato["Header"]["Error"]):
        msg = f"Contrato não encontrado para o imóvel {cod_imovel}, boleto: {boleto.nome_boleto}."
        logger.erro("Lançamento", msg)
        relatorio.registrar(
            cod_imovel=cod_imovel,
            numero_taxa="", descricao_taxa="", valor="",
            status="Erro", mensagem=msg,
        )
        return

    cod_contrato = resp_contrato["Body"]["CodContratoLoc"]
    logger.sucesso("Lançamento", f"Contrato {cod_contrato} localizado para imóvel {cod_imovel}.")
    relatorio.registrar(
        cod_imovel=cod_imovel,
        numero_taxa="", descricao_taxa="", valor="",
        status="Sucesso", mensagem="Contrato localizado",
    )

    # ── PASSO 1: lança todas as taxas ────────────────────────────────────────
    for taxa in taxas_boleto:
        nome_taxa = taxa.get("taxa", "").lower()

        if nome_taxa in _TAXAS_IGNORADAS:
            logger.sucesso("Lançamento", f"Taxa '{taxa.get('taxa')}' ignorada por regra de negócio.")
            relatorio.registrar(
                cod_imovel=cod_imovel,
                numero_taxa="",
                descricao_taxa=taxa.get("taxa", ""),
                valor=taxa.get("valor", ""),
                status="Sucesso",
                mensagem="Taxa não lançada por regra de negócio.",
            )
            continue

        if nome_taxa in _TAXAS_REVISAO_MANUAL:
            logger.sucesso("Lançamento", f"Taxa '{taxa.get('taxa')}' requer lançamento manual.")
            relatorio.registrar(
                cod_imovel=cod_imovel,
                numero_taxa="",
                descricao_taxa=taxa.get("taxa", ""),
                valor=taxa.get("valor", ""),
                status="Sucesso",
                mensagem=f"Taxa '{taxa.get('taxa')}' no boleto {boleto.nome_boleto}: lançamento manual.",
            )
            continue

        taxa["valor"] = float(
            str(taxa["valor"]).replace(".", "").replace(",", ".").replace("R$ ", "")
        )

        cod_taxa = next(
            (str(db[0]) for db in tabela_taxas if db[1].strip() == taxa.get("taxa", "").strip()),
            None
        )
        if not cod_taxa:
            msg = f"Taxa '{taxa.get('taxa')}' não encontrada no banco. Informe ao setor de TI."
            logger.erro("Lançamento", f"Taxa '{taxa.get('taxa')}' não encontrada na tabela.")
            relatorio.registrar(
                cod_imovel=cod_imovel,
                numero_taxa="",
                descricao_taxa=taxa.get("taxa", ""),
                valor=taxa["valor"],
                status="Erro",
                mensagem=msg,
            )
            continue

        prop_loc = "L" if int(cod_taxa) <= 499 else "P"

        imobiliar._incluir_lancamento(
            session_id, cod_taxa, cod_imovel, cod_contrato,
            competencia, tipo_boleto, taxa, taxa["valor"],
            boleto, prop_loc, logger, relatorio
        )

    # ── PASSO 2: exclui previstos remanescentes ──────────────────────────────
    resp_prev  = imobiliar.ConsultarPrevisto(session_id, cod_imovel, competencia, cod_contrato)
    lista_prev = resp_prev["Body"].get("Lista", [])
    imobiliar._excluir_previstos(
        session_id, lista_prev, resp_prev,
        cod_imovel, cod_contrato, competencia, tipo_boleto,
        boleto, logger
    )

    # ── PASSO 3: associa imagem do boleto ────────────────────────────────────
    imobiliar._associar_imagem(
        session_id, cod_imovel, competencia,
        url_publica, boleto, logger, relatorio
    )