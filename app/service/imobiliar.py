import requests
from dotenv import load_dotenv
from app.config import env
from urllib.parse import quote

URL = env("URL_IMOBILIAR")

session_id = None

def _extrair_erro(resp: dict) -> str:
    erros = resp.get('Body', {}).get('Erros', [])
    if isinstance(erros, list) and erros:
        return erros[0].get("Mensagem", "Erro desconhecido.")
    if isinstance(erros, dict):
        return erros.get("Mensagem", "Erro desconhecido.")
    return "Erro desconhecido."


def login(logger=None):
    response = requests.post(
        URL,
        json={
            "Header": {"Action": "LOGIN"},
            "Body": {
                "IMOB_ID": "CREDREAL",
                "USER_ID": env("USER_IMOBILIAR"),
                "USER_PASS": env("PASS_IMOBILIAR"),
            },
        },
    )
    responseJson = response.json()
    session_id = responseJson["Header"]["SessionId"]

    if responseJson['Header']['Status'] == 'Success' and not responseJson['Header']['Error']:
        if logger:
            logger.sucesso("Login Imobiliar", "Login realizado com sucesso.")
    else:
        if logger:
            logger.erro("Login Imobiliar", "Falha no login.")
        raise Exception("Falha no login do Imobiliar.")

    return session_id

def logout(session_id, logger=None):
    responseJson = requests.post(
        URL,
        json={
            "Header": {"SessionId": session_id, "Action": "LOGOUT"},
            "Body": {}
        }
    ).json() 

    if responseJson['Header']['Status'] == 'Success' and not responseJson['Header']['Error']:
        if logger:
            logger.sucesso("Logout Imobiliar", "Logout realizado com sucesso.")
    else:
        if logger:
            logger.erro("Logout Imobiliar", "Erro ao fazer logout.")

    return responseJson


def consultaContrato(session_id, cod_imovel):
        resp_contrato = requests.post(URL, json={
        "Header": {"SessionId": session_id, "Action": "LOCACAO_CONTRATO_IMOVEL_CONSULTAR"},
        "Body":   {"CodImovel": cod_imovel}
    }).json()
        return resp_contrato

def ConsultarPrevisto(session_id, cod_imovel, competencia, cod_contrato):
        resp_prev = requests.post(URL, json={
        "Header": {"SessionId": session_id, "Action": "LOCACAO_LANCTO_COND_CONSULTAR"},
        "Body":   {"CodImovel": cod_imovel, "Competencia": competencia,
                   "CodContratoLoc": cod_contrato}
    }).json()
        return resp_prev


# ---------------------------------------------------------------------------
# Funções de lançamento
# ---------------------------------------------------------------------------
def _excluir_previstos(session_id, lista_prev, resp_prev,
                       cod_imovel, cod_contrato, competencia,
                       tipo_boleto, boleto, logger):
    """Exclui todos os itens que ainda estão como previstos (PrevisaoReal == 'P')."""
    for item in lista_prev:
        if item.get('PrevisaoReal') != 'P':
            continue

        resp = requests.post(URL, json={
            "Header": {"SessionId": session_id, "Action": "LOCACAO_LANCTO_COND_EXCLUIR"},
            "Body": {
                "NumeroLancto":     resp_prev['Body']['NumeroLancto'],
                "NumeroLanctoItem": item['NumeroLanctoItem'],
                "CodImovel":        cod_imovel,
                "Competencia":      competencia,
                "CodContratoLoc":   cod_contrato,
                "TipoBoleto":       tipo_boleto,
                "DataVencimento":   boleto.vencimento,
            }
        }).json()
        print(resp)

        cod_taxa_item = item.get('CodTaxa', item.get('NumeroLanctoItem', '?'))
        if resp['Header']['Status'] == 'Success' and not resp['Header']['Error']:
            logger.sucesso("Exclusão", f"Imóvel {cod_imovel} — previsão da taxa {cod_taxa_item} excluída.")
        else:
            logger.erro("Exclusão", f"Erro ao excluir previsão da taxa {cod_taxa_item}: {_extrair_erro(resp)}")


def _incluir_lancamento(session_id, cod_taxa, cod_imovel, cod_contrato,
                        competencia, tipo_boleto, taxa, valor,
                        boleto, prop_loc, logger, relatorio):
    resp = requests.post(URL, json={
        "Header": {"SessionId": session_id, "Action": "LOCACAO_LANCTO_COND_INCLUIR"},
        "Body": {
            "TestaAditivoLocacao":          'N',
            "LancarContaCorrenteLocacao":   'S',
            "CompetenciaLocacao":           competencia,
            "TipoBoleto":                   tipo_boleto,
            "CodImovel":                    cod_imovel,
            "CodContratoLoc":               cod_contrato,
            "Competencia":                  competencia,
            "Complemento":                  boleto.complemento,
            "CodTaxa":                      cod_taxa,
            "CobrarLocatarioProprietario":  prop_loc,
            "TotalParcelas":                taxa.get("total_parcelas"),
            "NumeroParcela":                taxa.get("parcela_atual"),
            "ValorReal":                    valor,
            "DataVencimento":               boleto.vencimento,
            "CodBarras":                    boleto.codigo_barras,
        }
    }).json()

    if resp['Header']['Status'] == 'Success' and not resp['Header']['Error']:
        logger.sucesso("Lançamento", f"Imóvel {cod_imovel} — taxa {cod_taxa} lançada.")
        relatorio.registrar(
            cod_imovel=cod_imovel,
            numero_taxa=cod_taxa,
            descricao_taxa=taxa.get("taxa", ""),
            valor=valor,
            status="Sucesso",
            mensagem=f"Taxa {cod_taxa} lançada com sucesso.",
        )
    else:
        logger.erro("Lançamento", f"Erro ao lançar taxa {cod_taxa}: {_extrair_erro(resp)}")
        relatorio.registrar(
            cod_imovel=cod_imovel,
            numero_taxa=cod_taxa,
            descricao_taxa=taxa.get("taxa", ""),
            valor=valor,
            status="Erro",
            mensagem=f"{_extrair_erro(resp)}.",
        )


def _associar_imagem(session_id, cod_imovel, competencia, url_publica, boleto, logger, relatorio):
    resp = requests.post(URL, json={
        "Header": {"SessionId": session_id, "Action": "CTAPAG_LANCAMENTO_PESQUISAR"},
        "Body": {"TipoPesquisa": "I", "CodImovel": cod_imovel,
                 "TipoPeriodo": "C", "Competencia": competencia, "PrevisaoReal": "R"}
    }).json()

    lancamentos    = resp.get("Body", {}).get("Lancamentos", [])
    num_lancto_120 = next((l["NumeroLancto"] for l in lancamentos if l.get("CodTaxa") == 120), None)

    if not num_lancto_120:
        msg_nova = f"Não foi possível associar imagem ao imóvel {cod_imovel}, confira o e-mail para mais informações."
        logger.erro("Imagem", f"Imóvel {cod_imovel} sem lançamento de taxa 120. Imagem não associada.")
        relatorio.registrar(
            cod_imovel=cod_imovel,
            numero_taxa="",
            descricao_taxa="",
            valor="",
            processo="ASSOCIAÇÃO DE IMAGEM",
            status="Erro",
            mensagem=msg_nova,
        )
        return

    nome_url   = quote(boleto.nome_boleto)
    url_imagem = f"{url_publica}/taxa-120/arquivo/{nome_url}"

    # Valida acesso ao arquivo sem estourar exceção
    try:
        acessivel = requests.get(url_imagem, timeout=10).status_code == 200
    except Exception:
        acessivel = False

    if not acessivel:
        msg = f"Arquivo não acessível: {boleto.nome_boleto}"
        logger.erro("Imagem", msg)
        relatorio.registrar(
            cod_imovel=cod_imovel,
            numero_taxa="",
            descricao_taxa="",
            valor="",
            processo="ASSOCIAÇÃO DE IMAGEM",
            status="Erro",
            mensagem=msg,
        )
        return

    resp_img = requests.post(URL, json={
        "Header": {"SessionId": session_id, "Action": "CTAPAG_LANCAMENTO_ADICIONAR_IMAGEM"},
        "Body": {"NumeroLancto": num_lancto_120, "UrlImagem": url_imagem}
    }).json()

    if resp_img['Header']['Status'] == 'Success' and not resp_img['Header']['Error']:
        msg = f"Boleto {boleto.nome_boleto} associado ao lançamento {num_lancto_120}."
        logger.sucesso("Imagem", msg)
        relatorio.registrar(
            cod_imovel=cod_imovel,
            numero_taxa="",
            descricao_taxa="",
            valor="",
            processo="ASSOCIAÇÃO DE IMAGEM",
            status="Sucesso",
            mensagem=msg,
        )
    else:
        msg = f"Erro ao associar imagem: {_extrair_erro(resp_img)}"
        logger.erro("Imagem", msg)
        relatorio.registrar(
            cod_imovel=cod_imovel,
            numero_taxa="",
            descricao_taxa="",
            valor="",
            processo="ASSOCIAÇÃO DE IMAGEM",
            status="Erro",
            mensagem=msg,
        )