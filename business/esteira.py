import os
import re
import json
import time
import requests
from datetime import datetime
import fitz
import urllib3
from dotenv import load_dotenv
from business.minio_business import enviar_imagens_minio
from doe.esteira_doe import salvar_no_banco, salvar_anexos_no_banco, criar_lote_decretos, atualizar_total_decretos_lote, marcar_lote_vazio_processado
import google.generativeai as genai
import logging

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuração de Logs LLM
URL_LOGS = os.getenv("URL_LOGS", "http://18.206.213.53:8005/logs_processamento")

def enviar_log_llm(id_documento, modelo, tokens_entrada, tokens_saida, total_tokens, prompt, response_text, rotina, usuario, id_prompt):
    """
    Envia as estatísticas de uso da LLM para a API central de logs.
    Utiliza timeout curto e trata exceções para não travar a esteira principal.
    """
    if not URL_LOGS:
        return
        
    payload = {
        "id_documento": str(id_documento),
        "modelo": str(modelo),
        "tokens_entrada": tokens_entrada,
        "tokens_saida": tokens_saida,
        "total_tokens": total_tokens,
        "prompt": prompt,
        "response": response_text,
        "rotina": rotina,
        "usuario": usuario,
        "id_prompt": id_prompt
    }
    
    try:
        response_api = requests.post(URL_LOGS, json=payload, timeout=5)
        if response_api.status_code not in [200, 201]:
            logger.warning(f"Erro ao salvar log da LLM: HTTP {response_api.status_code} - {response_api.text}")
    except Exception as e:
        logger.warning(f"Falha na comunicação com a API de logs da LLM: {e}")

try:
    # Carrega as variáveis do arquivo .env (se existir)
    load_dotenv()

    # Autenticação Gemini
    GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
    if not GOOGLE_API_KEY:
        raise ValueError("A variável de ambiente 'GOOGLE_API_KEY' não foi encontrada.")
    genai.configure(api_key=GOOGLE_API_KEY)

    # Validação de Modelo
    modelos_validos = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    nome_modelo_escolhido = next((m for m in ["models/gemini-1.5-flash", "models/gemini-1.5-pro"] if m in modelos_validos), modelos_validos[0])

    print(f"Setup concluído! Modelo Gemini ativado: {nome_modelo_escolhido}")

except Exception as e:
    raise RuntimeError("Erro fatal: Verifique se a variável 'GOOGLE_API_KEY' está configurada corretamente.") from e

# Configuração básica do logger para a API
logger = logging.getLogger("ExtratorDOE")
logger.setLevel(logging.INFO)
# Configura o formato da mensagem: [DATA HORA] [NÍVEL] Mensagem
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
if not logger.handlers:
    logger.addHandler(handler)

def baixar_doe(url: str, max_tentativas: int = 3) -> bytes:
    """
    Realiza o download de um PDF do Diário Oficial.
    Possui sistema de tentativas (retry) para lidar com instabilidades do servidor,
    mas aborta imediatamente em caso de erro 404 (página não encontrada).
    """
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for tentativa in range(max_tentativas):
        try:
            resposta = requests.get(url, verify=False, timeout=30, headers=headers)
            
            # Se for 404, não adianta tentar de novo, o caderno realmente não existe
            if resposta.status_code == 404:
                return None
                
            resposta.raise_for_status()
            return resposta.content

        except requests.exceptions.RequestException as e:
            # Se for a última tentativa, desiste
            if tentativa == max_tentativas - 1:
                return None
            # Se não for, espera 2 segundos e tenta novamente
            time.sleep(2)
            
    return None

def is_linha_anterior_valida(linha: str) -> bool:
    if not linha: return False
    linha_upper = linha.upper()
    return (
        linha_upper == "PODER EXECUTIVO" or 
        linha_upper == "PODER EXECUTIVO (CONTINUAÇÃO)" or
        bool(re.match(r"^[\s\*]{3,}$", linha)) or
        "DIÁRIO OFICIAL" in linha_upper or
        "SÉRIE" in linha_upper or
        "FORTALEZA" in linha_upper or
        "ANO" in linha_upper or
        linha_upper.isdigit()
    )

def listar_decretos_doe(pdf_bytes: bytes, estado_inicial_executivo: bool = False) -> dict:
    """
    Lê o PDF da memória e extrai os decretos publicados.
    Aplica regras rigorosas para evitar falsos positivos:
    1. Apenas dentro da seção PODER EXECUTIVO (termina em GOVERNADORIA).
    Retorna uma lista de dicionários contendo a assinatura do decreto e a página.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    decretos_encontrados = []

    padrao_regex = r"^\s*DECRETO\s*N[°ºoO\.]*\s*[\d\.]+(?:\/\d{4})?\s*,?\s*de\s+\d{1,2}\s*,?\s*de\s+[a-zA-ZçÇ]+(?:\s+de)?\s+\d{4}\.?\s*$"
    molde_decreto = re.compile(padrao_regex, re.IGNORECASE)

    dentro_do_poder_executivo = estado_inicial_executivo
    governadoria_fechou = False
    linha_anterior_valida = ""
    pag_1_termina_com_asteriscos = False
    ultima_linha_pag_1 = ""

    for num_pagina in range(len(doc)):
        pagina = doc.load_page(num_pagina)
        texto_pagina = pagina.get_text("text")

        primeiro_decreto_da_pagina = True

        for linha in texto_pagina.splitlines():
            linha_limpa = linha.strip()
            
            if not linha_limpa:
                continue
                
            if num_pagina == 0:
                ultima_linha_pag_1 = linha_limpa
                
            linha_upper = linha_limpa.upper()

            # Controle da Seção Principal
            if linha_upper == "PODER EXECUTIVO" or linha_upper == "PODER EXECUTIVO (CONTINUAÇÃO)":
                dentro_do_poder_executivo = True
            elif linha_upper == "GOVERNADORIA" and dentro_do_poder_executivo:
                # O Diário Oficial tradicionalmente separa a Governadoria
                dentro_do_poder_executivo = False
                governadoria_fechou = True
            
            if dentro_do_poder_executivo:
                if molde_decreto.match(linha_limpa):
                    # Validação de Falso Positivo: Exige PODER EXECUTIVO, asteriscos ou cabeçalho
                    valido = is_linha_anterior_valida(linha_anterior_valida)
                    
                    if not valido and num_pagina == 1 and primeiro_decreto_da_pagina and pag_1_termina_com_asteriscos:
                        valido = True
                        
                    if valido:
                        decretos_encontrados.append({
                            "decreto": " ".join(linha_limpa.split()),
                            "pagina": num_pagina + 1
                        })
                        primeiro_decreto_da_pagina = False
            
            linha_anterior_valida = linha_limpa

        if num_pagina == 0:
            pag_1_termina_com_asteriscos = bool(re.match(r"^[\s\*]{3,}$", ultima_linha_pag_1))

    doc.close()
    return {
        "decretos": decretos_encontrados,
        "governadoria_fechou": governadoria_fechou,
        "estado_final_executivo": dentro_do_poder_executivo
    }

def contem_decreto_doe(pdf_bytes: bytes, numero_decreto: str) -> bool:
    """
    Verifica se um decreto específico consta no PDF carregado em memória.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    numero_limpo = str(numero_decreto).replace(".", "")
    regex_numero = r"\.?".join(list(numero_limpo))

    padrao_regex = rf"^\s*DECRETO\s*N[°ºoO\.]*\s*{regex_numero}(?:\/\d{{4}})?\s*,?\s*de\s+\d{{1,2}}\s*,?\s*de\s+[a-zA-ZçÇ]+(?:\s+de)?\s+\d{{4}}\.?\s*$"
    molde_decreto_especifico = re.compile(padrao_regex, re.IGNORECASE)
    
    padrao_qualquer_decreto = r"^\s*DECRETO\s*N[°ºoO\.]*\s*[\d\.]+(?:\/\d{4})?\s*,?\s*de\s+\d{1,2}\s*,?\s*de\s+[a-zA-ZçÇ]+(?:\s+de)?\s+\d{4}\.?\s*$"
    molde_qualquer_decreto = re.compile(padrao_qualquer_decreto, re.IGNORECASE)

    linha_anterior_valida = ""
    pag_1_termina_com_asteriscos = False
    ultima_linha_pag_1 = ""

    for num_pagina in range(len(doc)):
        pagina = doc.load_page(num_pagina)
        texto_pagina = pagina.get_text("text")
        
        primeiro_decreto_da_pagina = True

        for linha in texto_pagina.splitlines():
            linha_limpa = linha.strip()
            if not linha_limpa: continue
            
            if num_pagina == 0:
                ultima_linha_pag_1 = linha_limpa
            
            if molde_qualquer_decreto.match(linha_limpa):
                if molde_decreto_especifico.match(linha_limpa):
                    valido = is_linha_anterior_valida(linha_anterior_valida)
                    
                    if not valido and num_pagina == 1 and primeiro_decreto_da_pagina and pag_1_termina_com_asteriscos:
                        valido = True
                        
                    if valido:
                        doc.close()
                        return True
                        
                primeiro_decreto_da_pagina = False
            
            linha_anterior_valida = linha_limpa
            
        if num_pagina == 0:
            pag_1_termina_com_asteriscos = bool(re.match(r"^[\s\*]{3,}$", ultima_linha_pag_1))

    doc.close()
    return False

def verificar_decreto_primeira_pagina(pdf_bytes: bytes, numero_decreto: str) -> bool:
    """
    Verifica se um decreto específico inicia na primeira página do Diário Oficial.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    numero_limpo = str(numero_decreto).replace(".", "")
    regex_numero = r"\.?".join(list(numero_limpo))

    padrao_regex = rf"^\s*DECRETO\s*N[°ºoO\.]*\s*{regex_numero}(?:\/\d{{4}})?\s*,?\s*de\s+\d{{1,2}}\s*,?\s*de\s+[a-zA-ZçÇ]+(?:\s+de)?\s+\d{{4}}\.?\s*$"
    molde_decreto = re.compile(padrao_regex, re.IGNORECASE)

    # Verifica apenas a primeira página (índice 0) para máxima performance
    if len(doc) > 0:
        pagina = doc.load_page(0)
        texto_pagina = pagina.get_text("text")

        for linha in texto_pagina.splitlines():
            if molde_decreto.match(linha):
                doc.close()
                return True

    doc.close()
    return False

def extrair_texto_bruto_decreto(pdf_bytes, numero_decreto):
    """
    Extrai o texto e as imagens de um decreto específico lendo o PDF da memória.
    Caso possua imagens, salva os arquivos localmente em formato PNG.
    Retorna um dicionário com o status da operação, lista de imagens e o texto extraído.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    numero_limpo = str(numero_decreto).replace(".", "")
    regex_numero = r"\.?".join(list(numero_limpo))

    padrao_inicio = rf"^\s*DECRETO\s*N[°ºoO\.]*\s*{regex_numero}(?:\/\d{{4}})?\s*,?\s*de\s+\d{{1,2}}\s*,?\s*de\s+[a-zA-ZçÇ]+(?:\s+de)?\s+\d{{4}}\.?\s*$"
    molde_inicio = re.compile(padrao_inicio, re.IGNORECASE)
    
    padrao_qualquer_decreto = r"^\s*DECRETO\s*N[°ºoO\.]*\s*[\d\.]+(?:\/\d{4})?\s*,?\s*de\s+\d{1,2}\s*,?\s*de\s+[a-zA-ZçÇ]+(?:\s+de)?\s+\d{4}\.?\s*$"
    molde_qualquer_decreto = re.compile(padrao_qualquer_decreto, re.IGNORECASE)
    
    molde_fim_asteriscos = re.compile(r"^[\s\*]{3,}$")

    dentro_do_decreto = False
    texto_extraido = []
    imagens_encontradas = []
    linha_anterior_valida = ""
    pag_1_termina_com_asteriscos = False
    ultima_linha_pag_1 = ""

    for num_pagina in range(len(doc)):
        pagina = doc.load_page(num_pagina)
        lista_imagens = pagina.get_images(full=True)
        img_index = 0
        
        primeiro_decreto_da_pagina = True

        blocos = pagina.get_text("dict")["blocks"]

        for bloco in blocos:
            tipo_bloco = bloco.get("type", 0)

            if tipo_bloco == 1:
                if dentro_do_decreto and img_index < len(lista_imagens):
                    xref = lista_imagens[img_index][0]
                    texto_extraido.append(f"<fig_{numero_limpo}_{xref}>")
                    imagens_encontradas.append(xref)

                img_index += 1
                continue

            if tipo_bloco == 0:
                texto_bloco = ""
                for linha in bloco.get("lines", []):
                    for span in linha.get("spans", []):
                        texto_bloco += span.get("text", "")
                    texto_bloco += "\n"

                linhas_texto = texto_bloco.split('\n')

                for linha_texto in linhas_texto:
                    linha_limpa = linha_texto.strip()
                    if not linha_limpa:
                        continue
                        
                    if num_pagina == 0:
                        ultima_linha_pag_1 = linha_limpa

                    if not dentro_do_decreto:
                        if molde_qualquer_decreto.match(linha_limpa):
                            if molde_inicio.match(linha_limpa):
                                valido = is_linha_anterior_valida(linha_anterior_valida)
                                
                                if not valido and num_pagina == 1 and primeiro_decreto_da_pagina and pag_1_termina_com_asteriscos:
                                    valido = True
                                    
                                if valido:
                                    dentro_do_decreto = True
                                    texto_extraido.append(linha_limpa)
                            primeiro_decreto_da_pagina = False
                    else:
                        # Lógica original devidamente restaurada!
                        if molde_fim_asteriscos.match(linha_limpa) or linha_limpa == "GOVERNADORIA":
                            dentro_do_decreto = False
                            break

                        texto_extraido.append(linha_limpa)
                    
                    linha_anterior_valida = linha_limpa

            if not dentro_do_decreto and len(texto_extraido) > 0:
                break
                
        if num_pagina == 0:
            pag_1_termina_com_asteriscos = bool(re.match(r"^[\s\*]{3,}$", ultima_linha_pag_1))

        if not dentro_do_decreto and len(texto_extraido) > 0:
            break

    if imagens_encontradas:
        pasta_destino = "imagens_decretos"
        if not os.path.exists(pasta_destino):
            os.makedirs(pasta_destino)

        for xref in set(imagens_encontradas):
            try:
                pix = fitz.Pixmap(doc, xref)
                # Converte cores inadequadas para web (ex: CMYK) para o padrão RGB
                if pix.n - pix.alpha > 3:
                    pix = fitz.Pixmap(fitz.csRGB, pix)

                caminho_imagem = os.path.join(pasta_destino, f"fig_{numero_limpo}_{xref}.png")
                pix.save(caminho_imagem)
            except Exception:
                pass

    doc.close()

    if not texto_extraido:
        return {"sucesso": False, "mensagem": "Decreto não encontrado no arquivo."}

    texto_final = "\n".join(texto_extraido)

    return {
        "sucesso": True,
        "tem_figuras": len(imagens_encontradas) > 0,
        "xrefs_figuras": imagens_encontradas,
        "texto": texto_final
    }

def limpar_texto_pagina_um(texto_bruto):
    """
    Remove os cabeçalhos do Diário Oficial e a lista de secretariado do texto bruto.
    A exclusão do secretariado é engatilhada na página 2 e desativada automaticamente
    ao detectar o início do conteúdo real do documento.
    """
    linhas = texto_bruto.split('\n')
    linhas_limpas = []

    limpando_secretariado = False
    buffer_linhas = []

    for linha in linhas:
        linha_limpa = linha.strip()
        linha_upper = linha_limpa.upper()

        # --- 1. LÓGICA DE LIMPEZA DOS CABEÇALHOS ---
        tem_diario = "DIÁRIO OFICIAL" in linha_upper
        tem_outros = "SÉRIE" in linha_upper or "ANO" in linha_upper or "FORTALEZA" in linha_upper

        if tem_diario and tem_outros:
            if len(linhas_limpas) > 0 and linhas_limpas[-1].strip().isdigit():
                linhas_limpas.pop()
            continue

        # --- 2. LÓGICA DO SECRETARIADO ---
        if linha_limpa in ["Governador", "GOVERNADOR"]:
            limpando_secretariado = True
            buffer_linhas = []
            continue

        if limpando_secretariado:
            if not linha_limpa:
                continue

            quebrou_padrao = False
            ultimo_char = linha_limpa[-1] if linha_limpa else ""

            # Condições de quebra: Ponto final, números, balas ou inícios óbvios de atos normativos
            if ultimo_char == '.':
                quebrou_padrao = True
            elif any(c.isdigit() for c in linha_limpa):
                quebrou_padrao = True
            elif linha_limpa.startswith(('•', '-')):
                quebrou_padrao = True
            elif re.match(r'^[IVXLC]+\s*-', linha_upper):
                quebrou_padrao = True
            elif linha_upper in ["PODER EXECUTIVO", "GOVERNADORIA"] or \
                 linha_upper.startswith("DECRETO") or \
                 linha_upper.startswith("LEI ") or \
                 linha_upper.startswith("PORTARIA"):
                quebrou_padrao = True

            if not quebrou_padrao:
                if linha_limpa.isupper():
                    # Linhas maiúsculas indicam nomes/cargos. Descarta o que estava retido.
                    buffer_linhas = []
                    continue
                else:
                    # Retém temporariamente linhas não-maiúsculas (possíveis nomes de órgãos)
                    buffer_linhas.append(linha)
                    continue

            # O padrão do secretariado foi quebrado. Desliga a flag de limpeza.
            limpando_secretariado = False

            # Devolve ao texto as linhas que foram retidas indevidamente no buffer
            if buffer_linhas:
                linhas_limpas.extend(buffer_linhas)
                buffer_linhas = []

            linhas_limpas.append(linha)
            continue

        # --- 3. FORA DO SECRETARIADO, APENAS SALVA A LINHA ---
        linhas_limpas.append(linha)

    return "\n".join(linhas_limpas)

def limpar_texto_demais_paginas(texto_bruto):
    """
    Remove os cabeçalhos padrão do Diário Oficial e os números de página isolados
    do texto bruto extraído, preservando o restante do conteúdo.
    """
    linhas = texto_bruto.split('\n')
    linhas_limpas = []

    for linha in linhas:
        linha_limpa = linha.strip()
        linha_upper = linha_limpa.upper()

        # --- 1. IDENTIFICAÇÃO DO CABEÇALHO ---
        # Exige "DIÁRIO OFICIAL" e um termo secundário para evitar falsos positivos
        tem_diario = "DIÁRIO OFICIAL" in linha_upper
        tem_outros = "SÉRIE" in linha_upper or "ANO" in linha_upper or "FORTALEZA" in linha_upper

        if tem_diario and tem_outros:

            # --- 2. REMOÇÃO DO NÚMERO DA PÁGINA ---
            # Caso a linha anterior guardada seja apenas um dígito numérico, ela é descartada
            if len(linhas_limpas) > 0 and linhas_limpas[-1].strip().isdigit():
                linhas_limpas.pop()

            # Ignora a linha atual (o texto do cabeçalho em si)
            continue

        # --- 3. PRESERVAÇÃO DO CONTEÚDO ---
        linhas_limpas.append(linha)

    # Transforma a lista de frases de volta em um texto único e contínuo
    texto_final = "\n".join(linhas_limpas)

    return texto_final

def separar_decreto_dos_anexos(texto: str) -> tuple[str, str]:
    """
    Divide o texto de um decreto em duas partes: o corpo principal e os anexos (se existirem).
    Utiliza a assinatura do governador(a) como ponto de ancoragem para evitar falsos positivos
    nas menções a anexos no início do documento.
    Retorna uma tupla contendo (corpo_do_decreto, texto_dos_anexos).
    """
    # --- 1. VALIDAÇÃO DE TAMANHO ---
    # Textos curtos não possuem anexos estruturados. Retorno rápido por eficiência.
    if len(texto) < 500:
        return texto.strip(), "Sem anexos"

    # --- 2. DEFINIÇÃO DO PONTO DE ÂNCORA ---
    # Busca a assinatura oficial (Governador ou Governadora) para demarcar o fim do corpo principal.
    regex_assinatura = r"GOVERNADOR[A]?\s+DO\s+ESTADO\s+DO\s+CEARÁ"
    matches_assinatura = list(re.finditer(regex_assinatura, texto, re.IGNORECASE))

    # Se encontrar a assinatura, a varredura por anexos começará logo após ela.
    # Caso não encontre, inicia a busca a partir dos 40% finais do texto como margem de segurança.
    ponto_ancora = matches_assinatura[-1].end() if matches_assinatura else int(len(texto) * 0.4)

    # --- 3. IDENTIFICAÇÃO DO ANEXO ---
    # Molde Regex: compila os padrões que indicam o início de anexos, quadros ou convênios.
    padrao_anexo = re.compile(
        r"^\s*(ANEXO\s+I\b|ANEXO\s+[ÚU]NICO|ANEXO\s+D[AO]\s+DECRETO|ANEXO\s+A\b|ANEXO\s+\(A\)|ANEXO\s+DO\s+CR[ÉE]DITO|ANEXO\s+DA\s+LEI|QUADRO\s+RESUMO|QUADRO\s+DE\s+CARGOS|SISTEMA\s+OR[ÇC]AMENT[AÁ]RIO\s+E\s+FINANCEIRO|CONV[ÊE]NIO\s+ICMS\s+N[º°o.]?\s*\d+,\s*DE\s+\d{1,2}\s+DE\s+[A-ZÇç]+\s+DE\s+\d{4}|AJUSTE\s+SINIEF)",
        re.MULTILINE | re.IGNORECASE
    )

    # Procura pelo padrão do anexo estritamente após o ponto de âncora
    match_anexo = padrao_anexo.search(texto, ponto_ancora)

    # --- 4. CORTES E RETORNO ---
    if match_anexo:
        idx_corte = match_anexo.start()
        corpo_decreto = texto[:idx_corte].strip()
        texto_anexo = texto[idx_corte:].strip()

        return corpo_decreto, texto_anexo

    # Caso a busca não detecte anexos, retorna o texto integral como corpo principal
    return texto.strip(), "Sem anexos"

def identificar_tabelas_llm(texto: str, nome_modelo: str, id_usuario: str, id_documento: str, rotina: str, id_prompt: str) -> list:
    """
    Envia um trecho de texto para a LLM identificar estruturas tabulares achatadas.
    Retorna uma lista de dicionários contendo o texto bruto e a tabela reconstruída em Markdown.
    Realiza até 3 tentativas de requisição para tolerância a falhas (retries).
    """
    model = genai.GenerativeModel(nome_modelo)

    prompt = f"""
    Você é um Engenheiro de Dados especialista em reconstrução de layouts de documentos oficiais e governamentais.

    ###CONTEXTO:
    Ao extrair texto de PDFs, tabelas reais frequentemente perdem a grade visual e viram "textos achatados".
    Nestas tabelas hierárquicas (comuns em orçamentos e créditos suplementares), o extrator lê primeiro "Linhas Agrupadoras" (ex: Órgão) com apenas Nome e Valor, e depois "Linhas de Detalhe".

    ###A SUA MISSÃO:
    Identifique ESTRUTURAS TABULARES ocultas no texto e reconstrua-as perfeitamente em Markdown.

    REGRAS DE EXTRAÇÃO E PRESERVAÇÃO (CRÍTICO) 
    1. CORTE CIRÚRGICO: Inicie a extração para o campo `texto_original` EXATAMENTE no início dos cabeçalhos das colunas (ex: "ORGÃO/ UO/ PROGRAMA...", "ÓRGÃO SIGLA ORIGEM...").
    2. NÃO ENGULA TEXTO: NUNCA inclua os títulos gerais dos anexos, subtítulos ou texto explicativo que antecedem as colunas da tabela no campo `texto_original`. Deixe que eles permaneçam intactos fora da área que será substituída. O seu trabalho é APENAS estruturar a grelha.
    3. PROIBIDO CONCATENAR: NUNCA junte níveis hierárquicos diferentes numa única célula usando barras (/).
    4. LINHAS INDEPENDENTES: Cada nível orçamental DEVE ser uma linha separada na tabela Markdown.
    5. COLUNAS VAZIAS: Se uma linha tem apenas um Nome à esquerda e um Valor à direita, mantenha as colunas intermédias vazias (|||) e posicione o Valor na última coluna.

    ###PROIBIÇÕES ABSOLUTAS (FALSOS POSITIVOS)
    NÃO extraia organogramas ("Art. 1º", incisos I, II, 4.1), memoriais descritivos ou listas de texto corrido. Retorne vazio se achar apenas isso.

    ###TAREFA:
    1. Reconstrua os blocos de dados em formato Markdown perfeito (`| Coluna 1 | Coluna 2 |`).
    2. O campo 'texto_original' DEVE conter EXATAMENTE o trecho bruto usado para montar a tabela, da PRIMEIRA PALAVRA DO CABEÇALHO DA TABELA até o último número/total.

    ###EXEMPLOS:
    A seguir, estão demonstrações de trechos de textos que são considerados tabulares:

    Exemplo 1:
        ÓRGÃO
        SIGLA
        ORIGEM
        APLICAÇÃO
        COMPANHIA DE GESTÃO DOS RECURSOS HÍDRICOS DO CEARÁ
        COGERH
        -
        29.731.605,97
        1. 700.2200082 - Outras Transferências de Convênios ou Instrumentos Congêneres da União - Excesso
        29.731.605,97
        -
        TOTAL
        29.731.605,97
        29.731.605,97

    Exemplo 2:
        ORGÃO/ UO/ PROGRAMA DE TRABALHO
        REGIÃO
        GRUPO DE DESPESA
        FONTE
        ID. USO
        VALOR
        29200004 - COMPANHIA DE GESTÃO DOS RECURSOS HÍDRICOS DO CEARÁ
        29.731.605,97
        29200004 - COMPANHIA DE GESTÃO DOS RECURSOS HÍDRICOS DO CEARÁ
        29.731.605,97
        18.125.341 - PLANEJAMENTO E GESTÃO PARTICIPATIVA DOS RECURSOS HÍDRICOS.
        14062 - Aquisição de Equipamentos para as Áreas de Fiscalização do Uso dos Recursos Hídricos
        423.920,72
        15 - ESTADO DO CEARÁ
        INVESTIMENTOS
        1.700.2200082
        1
        423.920,72
        18.544.342 - OFERTA HÍDRICA PARA MÚLTIPLOS USOS.
        14001 - Instalação de Macromedidores
        11.368.140,02
        03 - GRANDE FORTALEZA
        INVESTIMENTOS
        1.700.2200082
        1
        11.368.140,02
        18.544.342 - OFERTA HÍDRICA PARA MÚLTIPLOS USOS.
        14002 - Revitalização das Estruturas dos Canais
        2.003.385,12
        03 - GRANDE FORTALEZA
        INVESTIMENTOS
        1.700.2200082
        1
        2.003.385,12
        18.544.342 - OFERTA HÍDRICA PARA MÚLTIPLOS USOS.
        14004 - Revitalização de Estações de Bombeamento
        2.910.225,59
        03 - GRANDE FORTALEZA
        INVESTIMENTOS
        1.700.2200082
        1
        2.910.225,59
        18.544.342 - OFERTA HÍDRICA PARA MÚLTIPLOS USOS.
        14006 - Recuperação das Barragens Monitoradas
        25.934,52
        03 - GRANDE FORTALEZA
        INVESTIMENTOS
        1.700.2200082
        1
        25.934,52
        18.544.342 - OFERTA HÍDRICA PARA MÚLTIPLOS USOS.
        14006 - Recuperação das Barragens Monitoradas
        13.000.000,00
        15 - ESTADO DO CEARÁ
        INVESTIMENTOS
        1.700.2200082
        1
        13.000.000,00
        TOTAL DO ANEXO I - SUPLEMENTAÇÃO DAS INDIRETAS
        29.731.605,97

    Exemplo 3:
        ÓRGÃO
        SIGLA
        ORIGEM
        APLICAÇÃO
        TRIBUNAL DE JUSTIÇA
        TJ
        106.792,00
        106.792,00
        SECRETARIA DA INFRAESTRUTURA
        SEINFRA
        0,00
        6.544.173,92
        DEPARTAMENTO ESTADUAL DE TRÂNSITO
        DETRAN
        2.610.343,21
        2.610.343,21
        ACADEMIA ESTADUAL DE SEGURANÇA PÚBLICA DO CEARÁ
        AESP
        0,00
        1.662.445,56
        FUNDO DE SEGURANÇA PÚBLICA E DEFESA SOCIAL DO ESTADO DO CEARÁ
        FSPDS
        0,00
        570.000,00
        PROCURADORIA GERAL DO ESTADO
        PGE
        135.000,00
        0,00
        FUNDO PENITENCIÁRIO DO ESTADO DO CEARÁ
        FUNPEN
        6.301,75
        6.301,75
        SECRETARIA DA FAZENDA
        SEFAZ
        7.500.000,00
        7.500.000,00
        SECRETARIA DO DESENVOLVIMENTO AGRÁRIO
        SDA
        100.000,00
        100.000,00
        INSTITUTO DE DESENVOLVIMENTO AGRÁRIO DO CEARÁ
        IDACE
        1.199.795,70
        1.199.795,70
        SECRETARIA DA EDUCAÇÃO
        SEDUC
        6.000.000,00
        8.000.000,00
        FUNDO ESTADUAL DE SAÚDE
        FUNDES
        14.784.723,91
        26.320.500,57
        FUNDO ESTADUAL DA CULTURA
        FEC
        1.400.000,00
        1.400.000,00
        SECRETARIA DA CIÊNCIA, TECNOLOGIA E EDUCAÇÃO SUPERIOR
        SECITECE
        0,00
        43.615,31

    Exemplo 4:
        ÓRGÃO
        SIGLA
        ORIGEM
        APLICAÇÃO
        FUNDAÇÃO UNIVERSIDADE VALE DO ACARAÚ
        UVA
        2.510.000,00
        0,00
        FUNDAÇÃO UNIVERSIDADE REGIONAL DO CARIRI
        URCA
        500.000,00
        500.000,00
        SECRETARIA DO TURISMO
        SETUR
        150.029,91
        867.345,08
        SUPERINTENDÊNCIA DE OBRAS PÚBLICAS
        SOP
        300.000,00
        30.000.000,00
        SECRETARIA DO PLANEJAMENTO E GESTÃO
        SEPLAG
        479.928,81
        0,00
        FUNDO FINANCEIRO - FUNAPREV
        FUNAPREV
        1.500.000,00
        1.500.000,00
        FUNDO FINANCEIRO - PREVMILITAR
        PREVMILITAR
        0,00
        22.000.000,00
        SECRETARIA DA PROTEÇÃO SOCIAL
        SPS
        1.405.948,43
        1.624.877,24
        SUPERINTENDÊNCIA DO SISTEMA ESTADUAL DE ATENDIMENTO SÓCIOEDUCATIVO
        SEAS
        17.334,84
        17.334,84
        AGÊNCIA DE DEFESA AGROPECUÁRIA DO ESTADO DO CEARÁ
        ADAGRI
        82.000,00
        82.000,00
        SUPERINTENDÊNCIA ESTADUAL DO MEIO AMBIENTE
        SEMACE
        45.200,00
        45.200,00
        SECRETARIA DOS DIREITOS HUMANOS
        SEDIH
        715.000,00
        0,00
        CONSELHO ESTADUAL DE EDUCAÇÃO
        CEE
        40.000,00
        40.000,00
        1.500.9100000 - Recursos não Vinculados de Impostos - Excesso
        44.303.576,54
        2.500.9100000 - Recursos não Vinculados de Impostos - Superávit
        2.315,17
        2.605.9200000 - Assistência Financeira da União Destinada à Complementação ao Pagamento dos Pisos Salariais para Profissionais da Enfermagem. - Fundes - Superávit
        100.000,00
        1.700.2200082 - Convênios com Órgãos Federais -SSPDS - Excesso
        128.000,00
        1.715.9200000 - Transferências Destinadas ao Setor Cultural - LC Nº 195/2022 - Art. 5º - Audiovisual - FEC - Excesso
        44.680,76
        1.754.3220067 - Operações de Crédito Externas ‑ Tesouro/MLW- SECITECE -Excesso
        27.273.393,35
        1.803.1200003 - Recursos Provenientes da Contribuição Social - PREVMILITAR - Excesso
        22.000.000,00
        TOTAL
        148.772.051,01
        148.772.051,01

    Exemplo 5:
        INSTITUIÇÃO
        TITULAR
        SUPLENTE
        Secretária da Educação - SEDUC
        Lúcia Maria Gomes
        Joizia Lima Cavalcante Rêgo
        Secretária da Fazenda - SEFAZ
        Talvani Rabelo Aguiar
        Tiberio Cesar Queiroz Sampaio
        Secretária do Planejamento e Gestão - SEPLAG
        Jackeline Sales de Melo
        Luciana Capistrano da Fonsêca Moura
        Conselho Estadual de Educação
        Raimunda Aurila Maia Freire
        Gabriel Félix e Silva
        Conselho Estadual de Educação
        Maria Joyce Maia Costa Carneiro
        Francisco Hermínio de Souza Júnior
        Poder Executivo Municipal - APRECE
        Luciana Gomes Marinho
        Caio Lincoln Sabino Fernandes
        Poder Executivo Municipal - APRECE
        Ana Vládia Cosmo Santos
        Lincoln Diniz Oliveira
        União Nacional dos Dirgentes Municipais da Educação_UNDIME
        Francisco Gustavo Brito Rego
        Raniere Pereira Rovere
        Sindicato dos servidores públicos lotados nas Secretarias de
        Educação e Cultura do Estado do Ceará - APEOC
        José Helano Maia
        Francisco Reginaldo Ferreira Pinheiro
        Pais de Alunos da Educação Pública
        Solange Rocha da Silva
        Francisca Camila Nascimento de Castro
        Pais de Alunos da Educação Pública
        Raimunda Pereira de Souza
        Ana Sheila Nogueira de Sousa
        Estudantes da Educação Básica
        Pedro Lucas Guimarães Rodrigues
        Kawendel Irineu de Andrade
        Estudantes da Educação Pública
        Gabriel Nepomuceno Frota
        José Mateus de Araújo Silva
        Organização da Sociedade Civil
        Francisca Daniely Barbosa Bezerra Silva Ana Keila Mota de Souza
        Organização da Sociedade Civil
        Adriana de Sousa Almeida
        Daniela Ferreira da Silva
        Escolas Indígenas
        Fabio Alves
        Antônia Leidiane Nascimento Costa
        Quilombolas
        Francisco Márcio dos Santos
        Antonia Érica Melo...

    Exemplo 6:
        ÓRGÃO
        SIGLA
        ANULAÇÃO (A)
        SUPLEMENTAÇÃO (B)
        TRIBUNAL DE JUSTIÇA
        TJ
        997.943,65
        997.943,65
        FUNDO ESPECIAL DE REAPARELHAMENTO E MODERNIZAÇÃO DO PODER JUDICIÁRIO
        FERMOJU
        1.615.000,00
        1.615.000,00
        FUNDO ESTADUAL DE SEGURANÇA DOS MAGISTRADOS
        FUNSEG
        1.177.221,00
        1.177.221,00
        DEPARTAMENTO ESTADUAL DE TRÂNSITO
        DETRAN
        28.881.701,20
        28.881.701,20
        SECRETARIA DA SEGURANÇA PÚBLICA E DEFESA SOCIAL
        SSPDS
        140.000,00
        140.000,00
        POLÍCIA CIVIL
        PC
        26.672,50
        26.672,50
        CORPO DE BOMBEIROS MILITAR DO ESTADO DO CEARÁ
        CBMCE
        400.000,00
        400.000,00
        FUNDO DE SEGURANÇA PÚBLICA E DEFESA SOCIAL DO ESTADO DO CEARÁ
        FSPDS
        675.774,00
        1.125.774,00
        SECRETARIA DA ADMINISTRAÇÃO PENITENCIÁRIA E RESSOCIALIZAÇÃO
        SAP
        60.000,00
        60.000,00
        SECRETARIA DO DESENVOLVIMENTO AGRÁRIO
        SDA
        963.620,61
        15.875.523,59
        SECRETARIA DA EDUCAÇÃO
        SEDUC
        10.000,00
        36.710.000,00
        FUNDO ESTADUAL DE SAÚDE
        FUNDES
        12.882.977,78
        16.023.714,55
        SECRETARIA DA CULTURA
        SECULT
        77.000,00
        77.000,00
        SECRETARIA DOS RECURSOS HÍDRICOS
        SRH
        3.350.000,00
        9.393.399,00
        CASA CIVIL
        CASA CIVIL
        2.137.000,00
        18.128.225,00
        SECRETARIA DA CIÊNCIA, TECNOLOGIA E EDUCAÇÃO SUPERIOR
        SECITECE
        997.320,00
        997.320,00
        FUNDAÇÃO UNIVERSIDADE ESTADUAL DO CEARÁ
        FUNECE
        220.000,00
        5.894.431,57
        FUNDAÇÃO CEARENSE DE APOIO AO DESENVOLVIMENTO CIENTÍFICO E TECNOLÓGICO
        FUNCAP
        24.693,72
        24.693,72
        NÚCLEO DE TECNOLOGIA E QUALIDADE INDUSTRIAL DO CEARÁ
        NUTEC
        297.235,02
        297.235,02
        SECRETARIA DO TURISMO
        SETUR
        199.430,05
        199.430,05
        ENCARGOS GERAIS DO ESTADO
        EGE
        22.308.969,24
        18.861.309,21
        SECRETARIA DO ESPORTE
        SESPORTE
        0,00
        676.000,00
        SECRETARIA DAS CIDADES
        SCIDADES
        5.519.857,60
        5.519.857,60
        SUPERINTENDÊNCIA DE OBRAS PÚBLICAS
        SOP
        100.000,00
        0,00
        FUNDO ESTADUAL DE SANEAMENTO BÁSICO
        FESB
        771.200,00
        771.200,00
        SECRETARIA DO PLANEJAMENTO E GESTÃO
        SEPLAG
        4.655.150,70
        2.702.651,35
        ESCOLA DE GESTÃO PÚBLICA DO ESTADO DO CEARÁ
        ESP
        113.003,00
        113.003,00
        INSTITUTO DE SAÚDE DOS SERVIDORES DO ESTADO DO CEARÁ
        ISSEC
        10.000,00
        10.000,00
        INSTITUTO DE PESQUISA E ESTRATÉGIA ECONÔMICA DO CEARÁ
        IPECE
        229.000,00
        229.000,00
        FUNDO FINANCEIRO - FUNAPREV
        FUNAPREV
        0,00
        25.234.830,96
        FUNDO FINANCEIRO - PREVMILITAR
        PREVMILITAR
        0,00
        22.330.000,00
        SECRETARIA DA PROTEÇÃO SOCIAL
        SPS
        450.000,00
        5.953.279,88
        SUPERINTENDÊNCIA DO SISTEMA ESTADUAL DE ATENDIMENTO SÓCIOEDUCATIVO
        SEAS
        0,00
        982.426,91
        CONTROLADORIA GERAL DE DISCIPLINA DOS ORGÃOS DE SEGURANÇA PÚBLICA E SISTEMA PENITENCIÁRIO
        CGD
        295.000,00
        295.000,00
        SECRETARIA DO DESENVOLVIMENTO ECONÔMICO
        SDE
        590.000,00
        1.148.700,78
        SECRETARIA DO MEIO AMBIENTE E MUDANÇA DO CLIMA
        SEMA
        116.500,00
        16.500,00
        SUPERINTENDÊNCIA ESTADUAL DO MEIO AMBIENTE
        SEMACE
        0,00
        5.485.273,01
        SECRETARIA DAS MULHERES
        SEM
        4.000.000,00
        0,00
        SECRETARIA DOS DIREITOS HUMANOS
        SEDIH
        2.920.000,00
        2.720.000,00
        SECRETARIA DA JUVENTUDE
        SEJUV
        100.000,00
        0,00
        SECRETARIA DA ARTICULAÇÃO POLÍTICA
        SEAPO
        150.000,00
        0,00
        SECRETARIA DAS RELAÇÕES INTERNACIONAIS
        SRI
        150.000,00
        0,00
        SECRETARIA DA IGUALDADE RACIAL
        SEIR
        100.000,00
        0,00
        1.500.9100000 - Recursos não Vinculados de Impostos - Excesso
        88.551.776,35
        2.501.1200070 - Recursos Diretamente Arrecadados - Superávit
        346,38
        1.544.9200000 - Recursos de Precatórios do Fundef - Excesso - SEDUC
        27.700.000,00
        1.550.9200000 - Transferência do Salário‑Educação - Excesso - SEDUC
        5.000.000,00
        1.599.9200000 - Outros Recursos Vinculados à Educação -Excesso - FUNECE
        4.496.610,00
        2.659.9200000 - Outros Recursos Vinculados à Saúde- Superávit - FUNDES
        1.690.736,77
        2.713.9200000 - Transferências Fundo a Fundo de Recursos do Fundo de Segurança Pública ‑ Superávit -FSPDS
        450.000,00
        2.700.2200082 - Convênios com Órgãos Federais - Superávit - Superávit - SEMACE
        5.484.926,63
        2.754.3220059 - Operações de Crédito Externas ‑ Tesouro/BID - Superávit - SEPLAG
        7.651,35
        TOTAL
        231.094.317,55
        231.094.317,55
    Exemplo 7:
        ORGÃO/ UO/ PROGRAMA DE TRABALHO
        REGIÃO
        GRUPO DE DESPESA
        FONTE
        ID. USO
        VALOR
        43200007 - SUPERINTENDÊNCIA DE OBRAS PÚBLICAS
        1.870.000,00
        43200007 - SUPERINTENDÊNCIA DE OBRAS PÚBLICAS
        1.870.000,00
        26.782.261 - INFRAESTRUTURA E LOGÍSTICA.
        11628 - Avaliação, Desapropriação de Imóveis e Licenças Ambientais para Obras Rodoviárias do Estado do Ceará
        1.870.000,00
        15 - ESTADO DO CEARÁ
        INVESTIMENTOS
        1.500.9100000
        0
        1.870.000,00
        TOTAL DO ANEXO I - SUPLEMENTAÇÃO DAS INDIRETAS
        1.870.000,00

    ###FORMATO DE SAÍDA EXIGIDO (JSON Lista):
    [
      {{
        "texto_original": "CABEÇALHO_BRUTO\nDADO1\n100.000,00",
        "tabela_estruturada": "| Cabeçalho | Valor |\n|---|---|\n| DADO 1 | 100.000,00 |"
      }}
    ]

    Se não houver NENHUMA tabela de cruzamento de dados, retorne apenas [].

    ###TEXTO PARA ANÁLISE:
    ---
    {texto}
    ---
    """

    for tentativa in range(3):
        try:
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            
            # Extrai contagem de tokens para o Log
            try:
                tokens_in = response.usage_metadata.prompt_token_count
                tokens_out = response.usage_metadata.candidates_token_count
                tokens_total = response.usage_metadata.total_token_count
                
                enviar_log_llm(
                    id_documento=id_documento,
                    modelo=nome_modelo,
                    tokens_entrada=tokens_in,
                    tokens_saida=tokens_out,
                    total_tokens=tokens_total,
                    prompt=prompt,
                    response_text=response.text,
                    rotina=rotina,
                    usuario=id_usuario,
                    id_prompt=id_prompt
                )
            except Exception as e:
                logger.warning(f"Não foi possível extrair os tokens de uso: {e}")

            return json.loads(response.text)
        except Exception:
            time.sleep(1)

    return []

def substituir_tabelas_robusto(texto_original_completo: str, tabelas_json: list) -> str:
    """
    Substitui os blocos de texto bruto pelas tabelas estruturadas em Markdown geradas pela LLM.
    Utiliza um mapeamento de caracteres não-brancos para garantir a substituição correta
    mesmo que haja divergências de espaços ou quebras de linha entre o original e a resposta da IA.
    """
    if not tabelas_json:
        return texto_original_completo

    texto_final = texto_original_completo

    for item in tabelas_json:
        trecho_llm = item.get('texto_original', '')
        titulo = item.get('titulo_tabela', '').strip()
        tabela_md = item.get('tabela_estruturada', '').strip()

        if not trecho_llm or not tabela_md:
            continue

        # --- 1. CRIAÇÃO DO MAPA DE ÍNDICES ---
        # Filtra os espaços em branco criando um esqueleto do texto original
        # e armazena os índices reais para mapeamento posterior.
        esqueleto_txt = []
        mapa_indices = []
        for i, char in enumerate(texto_final):
            if not char.isspace():
                esqueleto_txt.append(char)
                mapa_indices.append(i)

        str_esqueleto_txt = "".join(esqueleto_txt)
        esqueleto_llm = "".join(trecho_llm.split())

        # --- 2. BUSCA E SUBSTITUIÇÃO ---
        idx = str_esqueleto_txt.find(esqueleto_llm)

        if idx != -1:
            idx_real_inicio = mapa_indices[idx]
            idx_real_fim = mapa_indices[idx + len(esqueleto_llm) - 1] + 1

            bloco_novo = "\n\n"
            if titulo:
                bloco_novo += f"{titulo}\n"
            bloco_novo += f"<tabela>\n{tabela_md}\n</tabela>\n\n"

            # Fatiamento e injeção da nova tabela estruturada
            texto_final = texto_final[:idx_real_inicio] + bloco_novo + texto_final[idx_real_fim:]

    return texto_final

def processar_texto_com_llm(nome_parte: str, texto: str, modelo: str, id_usuario: str, id_documento: str, limite_chars: int = 40000) -> str:
    """
    Orquestra o envio do texto para análise da LLM e a posterior injeção das tabelas.
    Ignora a requisição e retorna o texto original caso o tamanho ultrapasse o limite
    (proteção contra estouro de tokens e custos desnecessários).
    """
    tamanho_texto = len(texto)

    if tamanho_texto == 0:
        return texto

    # Evita chamadas custosas à API se o texto for demasiadamente longo
    if tamanho_texto > limite_chars:
        return texto

    # Delega a identificação para o modelo
    lista_substituicoes = identificar_tabelas_llm(
        texto, 
        modelo, 
        id_usuario=id_usuario, 
        id_documento=id_documento, 
        rotina=f"Identificação de Tabelas - {nome_parte}", 
        id_prompt="4"
    )

    # Injeta o Markdown se houver tabelas encontradas
    if lista_substituicoes:
        return substituir_tabelas_robusto(texto, lista_substituicoes)

    return texto

def extrair_metadados_com_llm(texto_decreto: str, nome_modelo: str, id_usuario: str, id_documento: str) -> dict:
    """
    Usa a LLM para ler o decreto e extrair os metadados dinâmicos do texto.
    Força a saída em formato JSON estrito para integração segura na API.
    """
    model = genai.GenerativeModel(nome_modelo)

    prompt = f"""
    Você é um assistente jurídico especializado em Diários Oficiais.
    Extraia os metadados do texto do decreto abaixo e retorne ESTRITAMENTE um arquivo JSON válido.

    ### REGRAS PARA AS CHAVES DO JSON:
    - "id": string com a identificação do decreto (Ex: "DECRETO Nº 36.879").
    - "nup": lista de strings com os números de NUPs citados. Ex: ["10001.013770/2025-22"].
    - "pi_entes_programas": lista de strings com os órgãos do estado/secretarias relacionados ao teor do decreto.
    - "pi_pessoas_fisicas": lista de strings com nomes de pessoas físicas relacionadas ao teor (PROIBIDO incluir o Governador ou Secretários que apenas assinam o documento no final).
    - "pi_pessoas_juridicas": lista de strings com empresas ou instituições jurídicas (e CNPJs, se houver) citadas no teor.
    - "pi_municipios": lista de strings com os municípios citados no documento.
    - "responsaveis": lista de strings com os nomes das autoridades que assinam o decreto no final (Ex: Governador, Secretários).

    Se alguma informação não for encontrada no texto, retorne uma lista vazia [] ou null.

    ### TEXTO DO DECRETO:
    ---
    {texto_decreto}
    ---
    """

    for tentativa in range(3):
        try:
            response = model.generate_content(
                prompt,
                # Garante que a IA não mande Markdown ou texto solto, apenas o JSON puro
                generation_config={"response_mime_type": "application/json"}
            )
            
            # Extrai contagem de tokens para o Log
            try:
                tokens_in = response.usage_metadata.prompt_token_count
                tokens_out = response.usage_metadata.candidates_token_count
                tokens_total = response.usage_metadata.total_token_count
                
                enviar_log_llm(
                    id_documento=id_documento,
                    modelo=nome_modelo,
                    tokens_entrada=tokens_in,
                    tokens_saida=tokens_out,
                    total_tokens=tokens_total,
                    prompt=prompt,
                    response_text=response.text,
                    rotina="Extração de Metadados",
                    usuario=id_usuario,
                    id_prompt="5"
                )
            except Exception as e:
                logger.warning(f"Não foi possível extrair os tokens de uso (metadados): {e}")

            return json.loads(response.text)
        except Exception:
            time.sleep(1)

    # Retorno de segurança em caso de falha absoluta
    return {
        "id": None, "nup": [], "pi_entes_programas": [],
        "pi_pessoas_fisicas": [], "pi_pessoas_juridicas": [],
        "pi_municipios": [], "responsaveis": []
    }

#***************************************************************************

    match_data = re.search(r"(\d{8})", url_alvo)
    data_diario_formatada = None
    data_id_doc = None
    if match_data:
        data_bruta = match_data.group(1)
        data_diario_formatada = f"{data_bruta[6:]}/{data_bruta[4:6]}/{data_bruta[:4]}"
        data_id_doc = f"{data_bruta[6:]}{data_bruta[4:6]}{data_bruta[:4]}"

    logger.info("Procurando a página exata do decreto...")
    lista_decretos = listar_decretos_doe(arquivo_doe)["decretos"]
    pagina_doe = None
    numero_limpo_alvo = str(numero_alvo).replace(".", "")

    for item in lista_decretos:
        assinatura = item["decreto"]
        match_numero = re.search(r"N[°ºoO\.]*\s*([\d\.]+)", assinatura, re.IGNORECASE)
        if match_numero:
            num_encontrado = match_numero.group(1).strip().replace(".", "")
            if num_encontrado == numero_limpo_alvo:
                pagina_doe = item["pagina"]
                break

    if not pagina_doe:
        logger.warning(f"O Decreto {numero_alvo} não foi encontrado neste documento.")
        return {"sucesso": False, "mensagem": f"Decreto Nº {numero_alvo} não encontrado na URL fornecida."}

    logger.info(f"Iniciando extração (Encontrado na Página {pagina_doe})...")
    texto_bruto = extrair_texto_bruto_decreto(arquivo_doe, numero_alvo)

    if not texto_bruto["sucesso"]:
        logger.error("Falha ao extrair texto bruto.")
        return {"sucesso": False, "mensagem": "Falha na extração de texto."}

    logger.info("Verificando imagens no MinIO...")
    links_imagens = []
    if texto_bruto.get("tem_figuras"):
        links_imagens = enviar_imagens_minio(numero_alvo, texto_bruto["xrefs_figuras"], logger)

    is_pagina_um = verificar_decreto_primeira_pagina(arquivo_doe, numero_alvo)

    logger.info("Limpando sujeiras e separando anexos...")
    if is_pagina_um:
        texto_limpo = limpar_texto_pagina_um(texto_bruto["texto"])
    else:
        texto_limpo = limpar_texto_demais_paginas(texto_bruto["texto"])

    decreto_principal, anexos = separar_decreto_dos_anexos(texto_limpo)

    logger.info("Analisando tabelas do corpo principal e anexos...")
    decreto_principal_formatado = processar_texto_com_llm("Corpo do Decreto", decreto_principal, nome_modelo_escolhido, limite_chars=40000)
    anexos_formatados = processar_texto_com_llm("Anexos do Decreto", anexos, nome_modelo_escolhido, limite_chars=10000)

    logger.info("Extraindo metadados inteligentes...")
    metadados_llm = extrair_metadados_com_llm(decreto_principal, nome_modelo_escolhido)

    url_direta = f"{url_alvo}#page={pagina_doe}"
    timestamp_atual = str(datetime.now())
    numero_sem_ponto = str(numero_alvo).replace(".", "")

    metadados_completos = {
        "id_nome_decreto": f"DECRETO Nº {numero_alvo}",
        "nup": metadados_llm.get("nup", []),
        "viproc": None,
        "pagina": str(pagina_doe),
        "orgao_entidade_esfera": "PODER EXECUTIVO",
        "pi_entes_programas": metadados_llm.get("pi_entes_programas", []),
        "pi_pessoas_fisicas": metadados_llm.get("pi_pessoas_fisicas", []),
        "pi_pessoas_juridicas": metadados_llm.get("pi_pessoas_juridicas", []),
        "pi_municipios": metadados_llm.get("pi_municipios", []),
        "responsaveis": metadados_llm.get("responsaveis", []),
        "data_diario": data_diario_formatada,
        "url": url_direta,
        "arquivo_origem": url_alvo,
        "id_tipo": 1,
        "id_documento": f"1_{numero_sem_ponto}_{data_id_doc}",
        "processado": False,
        "data_criacao": timestamp_atual,
        "links_imagens": links_imagens
    }

    pacote_do_decreto = {
        "metadados": metadados_completos,
        "textos": {
            "original": decreto_principal_formatado,
            "anexos": anexos_formatados
        }
    }

    logger.info(f"Decreto {numero_alvo} finalizado com sucesso!")

    return {
        "sucesso": True,
        "total_decretos": 1,
        "dados": [pacote_do_decreto]
    }
#***************************************************************************

    match_data = re.search(r"(\d{8})", url_alvo)
    data_diario_formatada = None
    data_id_doc = None
    if match_data:
        data_bruta = match_data.group(1)
        data_diario_formatada = f"{data_bruta[6:]}/{data_bruta[4:6]}/{data_bruta[:4]}"
        data_id_doc = f"{data_bruta[6:]}{data_bruta[4:6]}{data_bruta[:4]}"

    logger.info("Lendo o PDF e listando decretos publicados...")
    lista_decretos = listar_decretos_doe(arquivo_doe)["decretos"]
    total_decretos = len(lista_decretos)

    if total_decretos == 0:
        logger.warning("Nenhum decreto encontrado neste Diário Oficial. Abortando extração.")
        return {
            "sucesso": True,
            "total_decretos": 0,
            "dados": []
        }

    logger.info(f"Encontrado(s) {total_decretos} decreto(s)! Iniciando processamento em lote...")

    resultados_finais = []

    for index, item in enumerate(lista_decretos, start=1):
        assinatura = item["decreto"]
        pagina_doe = item["pagina"]

        match_numero = re.search(r"N[°ºoO\.]*\s*([\d\.]+)", assinatura, re.IGNORECASE)

        if not match_numero:
            continue

        num_decreto = match_numero.group(1).strip()

        logger.info(f"[{index}/{total_decretos}] Processando Decreto Nº {num_decreto}...")

        texto_bruto = extrair_texto_bruto_decreto(arquivo_doe, num_decreto)

        if not texto_bruto["sucesso"]:
            logger.warning(f"Falha ao extrair texto bruto do Decreto {num_decreto}. Pulando para o próximo...")
            continue

        links_imagens = []
        if texto_bruto.get("tem_figuras"):
            logger.info(f"[{num_decreto}] Verificando e enviando imagens para o MinIO...")
            links_imagens = enviar_imagens_minio(num_decreto, texto_bruto["xrefs_figuras"], logger)

        is_pagina_um = verificar_decreto_primeira_pagina(arquivo_doe, num_decreto)

        logger.info(f"[{num_decreto}] Limpando sujeiras e separando anexos...")

        if is_pagina_um:
            texto_limpo = limpar_texto_pagina_um(texto_bruto["texto"])
        else:
            texto_limpo = limpar_texto_demais_paginas(texto_bruto["texto"])

        decreto_principal, anexos = separar_decreto_dos_anexos(texto_limpo)

        logger.info(f"[{num_decreto}] Analisando tabelas do corpo principal...")
        decreto_principal_formatado = processar_texto_com_llm("Corpo do Decreto", decreto_principal, nome_modelo_escolhido, limite_chars=40000)

        logger.info(f"[{num_decreto}] Analisando tabelas dos anexos...")
        anexos_formatados = processar_texto_com_llm("Anexos do Decreto", anexos, nome_modelo_escolhido, limite_chars=10000)

        logger.info(f"[{num_decreto}] Extraindo metadados inteligentes...")
        metadados_llm = extrair_metadados_com_llm(decreto_principal, nome_modelo_escolhido)

        url_direta = f"{url_alvo}#page={pagina_doe}"
        timestamp_atual = str(datetime.now())
        numero_sem_ponto = str(num_decreto).replace(".", "")

        metadados_completos = {
            "id_nome_decreto": f"DECRETO Nº {num_decreto}",
            "nup": metadados_llm.get("nup", []),
            "viproc": None,
            "pagina": str(pagina_doe),
            "orgao_entidade_esfera": "PODER EXECUTIVO",
            "pi_entes_programas": metadados_llm.get("pi_entes_programas", []),
            "pi_pessoas_fisicas": metadados_llm.get("pi_pessoas_fisicas", []),
            "pi_pessoas_juridicas": metadados_llm.get("pi_pessoas_juridicas", []),
            "pi_municipios": metadados_llm.get("pi_municipios", []),
            "responsaveis": metadados_llm.get("responsaveis", []),
            "data_diario": data_diario_formatada,
            "url": url_direta,
            "arquivo_origem": url_alvo,
            "id_tipo": 1,
            "id_documento": f"1_{numero_sem_ponto}_{data_id_doc}",
            "processado": False,
            "data_criacao": timestamp_atual,
            "links_imagens": links_imagens
        }

        resultados_finais.append({
            "metadados": metadados_completos,
            "textos": {
                "original": decreto_principal_formatado,
                "anexos": anexos_formatados
            }
        })

        logger.info(f"Decreto {num_decreto} finalizado com sucesso!")

    logger.info(f"Processamento em lote concluído! {len(resultados_finais)} de {total_decretos} decretos extraídos com sucesso.")

    return {
        "sucesso": True,
        "total_decretos": len(resultados_finais),
        "dados": resultados_finais
    }

def processar_diario_em_lote(url_alvo: str, id_lote: int = None, id_usuario: str = None):
    yield json.dumps({"status": "log", "mensagem": "Baixando o Diário Oficial da URL..."}) + "\n"
    logger.info("Baixando o Diário Oficial da URL...")
    arquivo_doe = baixar_doe(url_alvo)

    if not arquivo_doe:
        logger.error("Falha crítica ao baixar o PDF.")
        yield json.dumps({"status": "error", "mensagem": "Falha ao baixar o PDF."}) + "\n"
        return

    match_data = re.search(r"(\d{8})", url_alvo)
    data_diario_formatada = None
    data_id_doc = None
    if match_data:
        data_bruta = match_data.group(1)
        data_diario_formatada = f"{data_bruta[6:]}/{data_bruta[4:6]}/{data_bruta[:4]}"
        data_id_doc = f"{data_bruta[6:]}{data_bruta[4:6]}{data_bruta[:4]}"

    yield json.dumps({"status": "log", "mensagem": "Lendo o PDF e listando decretos publicados..."}) + "\n"
    logger.info("Lendo o PDF e listando decretos publicados...")
    lista_decretos = listar_decretos_doe(arquivo_doe)["decretos"]
    total_decretos = len(lista_decretos)

    if total_decretos == 0:
        logger.warning("Nenhum decreto encontrado neste Diário Oficial. Abortando extração.")
        yield json.dumps({"status": "done", "resultados": {
            "sucesso": True,
            "total_decretos": 0,
            "dados": []
        }}) + "\n"
        return

    
    yield json.dumps({"status": "log", "mensagem": f"Encontrado(s) {total_decretos} decreto(s)! Iniciando processamento em lote..."}) + "\n"
    logger.info(f"Encontrado(s) {total_decretos} decreto(s)! Iniciando processamento em lote...")

    resultados_finais = []

    for index, item in enumerate(lista_decretos, start=1):
        assinatura = item["decreto"]
        pagina_doe = item["pagina"]

        match_numero = re.search(r"N[°ºoO\.]*\s*([\d\.]+)", assinatura, re.IGNORECASE)

        if not match_numero:
            continue

        num_decreto = match_numero.group(1).strip()

        yield json.dumps({"status": "log", "mensagem": f"[{index}/{total_decretos}] Processando Decreto Nº {num_decreto}..."}) + "\n"
        logger.info(f"[{index}/{total_decretos}] Processando Decreto Nº {num_decreto}...")

        texto_bruto = extrair_texto_bruto_decreto(arquivo_doe, num_decreto)

        if not texto_bruto["sucesso"]:
            yield json.dumps({"status": "log", "mensagem": f"Falha ao extrair texto bruto do Decreto {num_decreto}. Pulando..."}) + "\n"
            logger.warning(f"Falha ao extrair texto bruto do Decreto {num_decreto}. Pulando para o próximo...")
            continue

        links_imagens = []
        if texto_bruto.get("tem_figuras"):
            yield json.dumps({"status": "log", "mensagem": f"[{num_decreto}] Verificando e enviando imagens para o MinIO..."}) + "\n"
            logger.info(f"[{num_decreto}] Verificando e enviando imagens para o MinIO...")
            links_imagens = enviar_imagens_minio(num_decreto, texto_bruto["xrefs_figuras"], logger)

        is_pagina_um = verificar_decreto_primeira_pagina(arquivo_doe, num_decreto)

        yield json.dumps({"status": "log", "mensagem": f"[{num_decreto}] Limpando sujeiras e separando anexos..."}) + "\n"
        logger.info(f"[{num_decreto}] Limpando sujeiras e separando anexos...")

        if is_pagina_um:
            texto_limpo = limpar_texto_pagina_um(texto_bruto["texto"])
        else:
            texto_limpo = limpar_texto_demais_paginas(texto_bruto["texto"])

        decreto_principal, anexos = separar_decreto_dos_anexos(texto_limpo)
        
        # Constrói o ID do documento antecipadamente para o Log da LLM
        numero_sem_ponto = str(num_decreto).replace(".", "")
        id_documento_gerado = f"1_{numero_sem_ponto}_{data_id_doc}" if data_id_doc else f"1_{numero_sem_ponto}"

        yield json.dumps({"status": "log", "mensagem": f"[{num_decreto}] Analisando tabelas do corpo principal..."}) + "\n"
        logger.info(f"[{num_decreto}] Analisando tabelas do corpo principal...")
        decreto_principal_formatado = processar_texto_com_llm(
            "Corpo do Decreto", 
            decreto_principal, 
            nome_modelo_escolhido, 
            id_usuario=id_usuario,
            id_documento=id_documento_gerado,
            limite_chars=40000
        )

        yield json.dumps({"status": "log", "mensagem": f"[{num_decreto}] Analisando tabelas dos anexos..."}) + "\n"
        logger.info(f"[{num_decreto}] Analisando tabelas dos anexos...")
        anexos_formatados = processar_texto_com_llm(
            "Anexos do Decreto", 
            anexos, 
            nome_modelo_escolhido, 
            id_usuario=id_usuario,
            id_documento=id_documento_gerado,
            limite_chars=10000
        )

        yield json.dumps({"status": "log", "mensagem": f"[{num_decreto}] Extraindo metadados inteligentes..."}) + "\n"
        logger.info(f"[{num_decreto}] Extraindo metadados inteligentes...")
        metadados_llm = extrair_metadados_com_llm(
            decreto_principal, 
            nome_modelo_escolhido,
            id_usuario=id_usuario,
            id_documento=id_documento_gerado
        )

        url_direta = f"{url_alvo}#page={pagina_doe}"
        timestamp_atual = str(datetime.now())

        metadados_completos = {
            "id_nome_decreto": f"DECRETO Nº {num_decreto}",
            "nup": metadados_llm.get("nup", []),
            "viproc": None,
            "pagina": str(pagina_doe),
            "orgao_entidade_esfera": "PODER EXECUTIVO",
            "pi_entes_programas": metadados_llm.get("pi_entes_programas", []),
            "pi_pessoas_fisicas": metadados_llm.get("pi_pessoas_fisicas", []),
            "pi_pessoas_juridicas": metadados_llm.get("pi_pessoas_juridicas", []),
            "pi_municipios": metadados_llm.get("pi_municipios", []),
            "responsaveis": metadados_llm.get("responsaveis", []),
            "data_diario": data_diario_formatada,
            "url": url_direta,
            "arquivo_origem": str(id_lote) if id_lote else url_alvo,
            "id_tipo": 1,
            "id_documento": id_documento_gerado,
            "processado": False,
            "data_criacao": timestamp_atual,
            "links_imagens": links_imagens
        }

        resultados_finais.append({
            "metadados": metadados_completos,
            "textos": {
                "original": decreto_principal_formatado,
                "anexos": anexos_formatados
            }
        })

        yield json.dumps({"status": "log", "mensagem": f"Decreto {num_decreto} finalizado com sucesso!"}) + "\n"
        logger.info(f"Decreto {num_decreto} finalizado com sucesso!")

    msg_final = f"Processamento em lote concluído! {len(resultados_finais)} de {total_decretos} decretos extraídos com sucesso."
    yield json.dumps({"status": "log", "mensagem": msg_final}) + "\n"
    logger.info(msg_final)

    yield json.dumps({"status": "done", "resultados": {
        "sucesso": True,
        "total_decretos": len(resultados_finais),
        "dados": resultados_finais
    }}) + "\n"

def executar_esteira_publicacao_doe(url_do_diario: str, id_usuario: str):
    yield json.dumps({"status": "log", "mensagem": f"INICIANDO ESTEIRA EM LOTE: {url_do_diario}"}) + "\n"
    logger.info("================================================================")
    logger.info(f"INICIANDO ESTEIRA EM LOTE: {url_do_diario}")
    logger.info("================================================================")

    try:
        id_lote = criar_lote_decretos(url_do_diario, id_usuario)
        yield json.dumps({"status": "log", "mensagem": f"Lote de importação registrado (ID: {id_lote})"}) + "\n"
    except Exception as e:
        yield json.dumps({"status": "error", "mensagem": f"Falha ao registrar lote: {e}"}) + "\n"
        return

    resultado_final = None

    for evento in processar_diario_em_lote(url_do_diario, id_lote, id_usuario):
        try:
            evento_dict = json.loads(evento.strip())
            if evento_dict.get("status") == "done":
                resultado_final = evento_dict.get("resultados")
            else:
                yield evento
        except Exception:
            yield evento

    if resultado_final and resultado_final.get("sucesso"):
        if resultado_final.get("total_decretos") == 0:
            yield json.dumps({"status": "log", "mensagem": "Fluxo interrompido limpo: Não há dados para processar."}) + "\n"
            logger.info("Fluxo interrompido limpo: Não há dados para processar ou salvar no banco.")
            
            # Atualiza o status do lote para processado quando não há decretos
            marcar_lote_vazio_processado(id_lote)
            
            yield json.dumps({"status": "done", "resultado": resultado_final}) + "\n"
            return

        yield json.dumps({"status": "log", "mensagem": f"Extração concluída! Total de decretos: {resultado_final.get('total_decretos')}"}) + "\n"
        logger.info(f"Extração concluída! Total de decretos: {resultado_final.get('total_decretos')}")

        yield json.dumps({"status": "log", "mensagem": "Iniciando gravação em lote no PostgreSQL..."}) + "\n"
        logger.info("Iniciando gravação em lote no PostgreSQL (Desenvolvimento)...")

        try:
            total_inseridos = salvar_no_banco(resultado_final, id_lote)
            salvar_anexos_no_banco(resultado_final, id_lote)
            
            # Atualiza o lote com o total real de decretos salvos (ignorando duplicados)
            atualizar_total_decretos_lote(id_lote, total_inseridos)

            yield json.dumps({"status": "log", "mensagem": f"Todos os dados ({total_inseridos} inseridos novos) e anexos gravados no banco com sucesso!"}) + "\n"
            logger.info("Todos os dados e anexos foram gravados no banco com sucesso!")
            
            yield json.dumps({"status": "done", "resultado": resultado_final}) + "\n"

        except Exception as e:
            msg_erro = f"Lote extraído, mas falhou ao salvar no banco: {e}"
            yield json.dumps({"status": "error", "mensagem": msg_erro}) + "\n"
            logger.error(msg_erro)
    else:
        msg_erro = f"A esteira em lote falhou: {resultado_final.get('mensagem') if resultado_final else 'Erro desconhecido'}"
        yield json.dumps({"status": "error", "mensagem": msg_erro}) + "\n"
        logger.error(msg_erro)

def processar_diario_unico(url_alvo: str, numero_alvo: str, id_usuario: str = None, id_lote: int = None):
    yield json.dumps({"status": "log", "mensagem": f"Iniciando processamento do Decreto {numero_alvo}"}) + "\n"
    logger.info(f"Iniciando processamento do Decreto {numero_alvo}")
    
    yield json.dumps({"status": "log", "mensagem": "Baixando o Diário Oficial da URL..."}) + "\n"
    logger.info("Baixando o Diário Oficial da URL...")

    arquivo_doe = baixar_doe(url_alvo)

    if not arquivo_doe:
        logger.error("Falha crítica ao baixar o PDF.")
        yield json.dumps({"status": "error", "mensagem": "Falha ao baixar o PDF."}) + "\n"
        return

    match_data = re.search(r"(\d{8})", url_alvo)
    data_diario_formatada = None
    data_id_doc = None
    if match_data:
        data_bruta = match_data.group(1)
        data_diario_formatada = f"{data_bruta[6:]}/{data_bruta[4:6]}/{data_bruta[:4]}"
        data_id_doc = f"{data_bruta[6:]}{data_bruta[4:6]}{data_bruta[:4]}"

    yield json.dumps({"status": "log", "mensagem": "Procurando a página exata do decreto..."}) + "\n"
    logger.info("Procurando a página exata do decreto...")
    lista_decretos = listar_decretos_doe(arquivo_doe)["decretos"]
    pagina_doe = None
    numero_limpo_alvo = str(numero_alvo).replace(".", "")

    for item in lista_decretos:
        assinatura = item["decreto"]
        match_numero = re.search(r"N[°ºoO\.]*\s*([\d\.]+)", assinatura, re.IGNORECASE)
        if match_numero:
            num_encontrado = match_numero.group(1).strip().replace(".", "")
            if num_encontrado == numero_limpo_alvo:
                pagina_doe = item["pagina"]
                break

    if not pagina_doe:
        msg = f"Decreto Nº {numero_alvo} não encontrado na URL fornecida."
        logger.warning(msg)
        yield json.dumps({"status": "error", "mensagem": msg}) + "\n"
        return

    yield json.dumps({"status": "log", "mensagem": f"Iniciando extração (Encontrado na Página {pagina_doe})..."}) + "\n"
    logger.info(f"Iniciando extração (Encontrado na Página {pagina_doe})...")
    texto_bruto = extrair_texto_bruto_decreto(arquivo_doe, numero_alvo)

    if not texto_bruto["sucesso"]:
        logger.error("Falha ao extrair texto bruto.")
        yield json.dumps({"status": "error", "mensagem": "Falha na extração de texto."}) + "\n"
        return

    yield json.dumps({"status": "log", "mensagem": "Verificando imagens no MinIO..."}) + "\n"
    logger.info("Verificando imagens no MinIO...")
    links_imagens = []
    if texto_bruto.get("tem_figuras"):
        links_imagens = enviar_imagens_minio(numero_alvo, texto_bruto["xrefs_figuras"], logger)

    is_pagina_um = verificar_decreto_primeira_pagina(arquivo_doe, numero_alvo)

    yield json.dumps({"status": "log", "mensagem": "Limpando sujeiras e separando anexos..."}) + "\n"
    logger.info("Limpando sujeiras e separando anexos...")
    if is_pagina_um:
        texto_limpo = limpar_texto_pagina_um(texto_bruto["texto"])
    else:
        texto_limpo = limpar_texto_demais_paginas(texto_bruto["texto"])

    decreto_principal, anexos = separar_decreto_dos_anexos(texto_limpo)

    # Constrói o ID do documento antecipadamente para o Log da LLM
    numero_sem_ponto = str(numero_alvo).replace(".", "")
    id_documento_gerado = f"1_{numero_sem_ponto}_{data_id_doc}" if data_id_doc else f"1_{numero_sem_ponto}"

    yield json.dumps({"status": "log", "mensagem": "Analisando tabelas do corpo principal e anexos..."}) + "\n"
    logger.info("Analisando tabelas do corpo principal e anexos...")
    decreto_principal_formatado = processar_texto_com_llm(
        "Corpo do Decreto", 
        decreto_principal, 
        nome_modelo_escolhido, 
        id_usuario=id_usuario,
        id_documento=id_documento_gerado,
        limite_chars=40000
    )
    anexos_formatados = processar_texto_com_llm(
        "Anexos do Decreto", 
        anexos, 
        nome_modelo_escolhido, 
        id_usuario=id_usuario,
        id_documento=id_documento_gerado,
        limite_chars=10000
    )

    yield json.dumps({"status": "log", "mensagem": "Extraindo metadados inteligentes..."}) + "\n"
    logger.info("Extraindo metadados inteligentes...")
    metadados_llm = extrair_metadados_com_llm(
        decreto_principal, 
        nome_modelo_escolhido,
        id_usuario=id_usuario,
        id_documento=id_documento_gerado
    )

    url_direta = f"{url_alvo}#page={pagina_doe}"
    timestamp_atual = str(datetime.now())

    metadados_completos = {
        "id_nome_decreto": f"DECRETO Nº {numero_alvo}",
        "nup": metadados_llm.get("nup", []),
        "viproc": None,
        "pagina": str(pagina_doe),
        "orgao_entidade_esfera": "PODER EXECUTIVO",
        "pi_entes_programas": metadados_llm.get("pi_entes_programas", []),
        "pi_pessoas_fisicas": metadados_llm.get("pi_pessoas_fisicas", []),
        "pi_pessoas_juridicas": metadados_llm.get("pi_pessoas_juridicas", []),
        "pi_municipios": metadados_llm.get("pi_municipios", []),
        "responsaveis": metadados_llm.get("responsaveis", []),
        "data_diario": data_diario_formatada,
        "url": url_direta,
        "arquivo_origem": str(id_lote) if id_lote else url_alvo,
        "id_tipo": 1,
        "id_documento": id_documento_gerado,
        "processado": False,
        "data_criacao": timestamp_atual,
        "links_imagens": links_imagens
    }

    pacote_do_decreto = {
        "metadados": metadados_completos,
        "textos": {
            "original": decreto_principal_formatado,
            "anexos": anexos_formatados
        }
    }

    yield json.dumps({"status": "log", "mensagem": f"Decreto {numero_alvo} finalizado com sucesso!"}) + "\n"
    logger.info(f"Decreto {numero_alvo} finalizado com sucesso!")

    yield json.dumps({"status": "done", "resultados": {
        "sucesso": True,
        "total_decretos": 1,
        "dados": [pacote_do_decreto]
    }}) + "\n"

def executar_esteira_decreto_unico(data_do_diario: str, numero_do_decreto: str, id_usuario: str = None):
    from business.varredura_business import montar_url_por_data

    res_url = montar_url_por_data(data_do_diario)
    if not res_url.get("sucesso"):
        yield json.dumps({"status": "error", "mensagem": res_url.get("mensagem")}) + "\n"
        return
    url_do_diario = res_url["url"]

    yield json.dumps({"status": "log", "mensagem": f"INICIANDO ESTEIRA PARA O DECRETO: {numero_do_decreto}"}) + "\n"
    logger.info("================================================================")
    logger.info(f"INICIANDO ESTEIRA PARA O DECRETO: {numero_do_decreto}")
    logger.info(f"🔗 URL MONTADA ({data_do_diario}): {url_do_diario}")
    logger.info("================================================================")

    try:
        id_lote = criar_lote_decretos(url_do_diario, id_usuario or "sistema")
        yield json.dumps({"status": "log", "mensagem": f"Lote de importação registrado (ID: {id_lote})"}) + "\n"
    except Exception as e:
        yield json.dumps({"status": "error", "mensagem": f"Falha ao registrar lote: {e}"}) + "\n"
        return

    resultado_final = None

    for evento in processar_diario_unico(url_do_diario, numero_do_decreto, id_usuario, id_lote=id_lote):
        try:
            evento_dict = json.loads(evento.strip())
            if evento_dict.get("status") == "done":
                resultado_final = evento_dict.get("resultados")
            else:
                yield evento
        except Exception:
            yield evento

    if resultado_final and resultado_final.get("sucesso"):
        yield json.dumps({"status": "log", "mensagem": "Extração concluída com sucesso!"}) + "\n"
        logger.info("Extração concluída com sucesso!")

        yield json.dumps({"status": "log", "mensagem": "Iniciando gravação no PostgreSQL..."}) + "\n"
        logger.info("Iniciando gravação no PostgreSQL (Desenvolvimento)...")

        try:
            total_inseridos = salvar_no_banco(resultado_final, id_lote)
            salvar_anexos_no_banco(resultado_final, id_lote)
            atualizar_total_decretos_lote(id_lote, total_inseridos)

            yield json.dumps({"status": "log", "mensagem": f"Todos os dados ({total_inseridos} inseridos novos) e anexos gravados no banco com sucesso!"}) + "\n"
            logger.info("Todos os dados e anexos foram gravados no banco com sucesso!")
            
            yield json.dumps({"status": "done", "resultado": resultado_final}) + "\n"

        except Exception as e:
            msg_erro = f"Decreto extraído, mas falhou ao salvar no banco: {e}"
            yield json.dumps({"status": "error", "mensagem": msg_erro}) + "\n"
            logger.error(msg_erro)
    else:
        if id_lote:
            marcar_lote_vazio_processado(id_lote)
        msg_erro = f"A esteira falhou: {resultado_final.get('mensagem') if resultado_final else 'Erro desconhecido'}"
        yield json.dumps({"status": "error", "mensagem": msg_erro}) + "\n"
        logger.error(msg_erro)


def executar_multiplos_lotes_doe(urls: list, id_usuario: str):
    """
    Orquestra o processamento completo de múltiplos Diários Oficiais em lote.
    """
    total_urls = len(urls)
    yield json.dumps({"status": "log", "mensagem": f"Iniciando processamento múltiplo de {total_urls} URLs..."}) + "\n"
    logger.info(f"Iniciando processamento múltiplo de {total_urls} URLs...")
    
    resultados_totais = []
    
    for i, url in enumerate(urls, 1):
        yield json.dumps({"status": "log", "mensagem": f"--- Processando URL {i} de {total_urls} ---"}) + "\n"
        logger.info(f"--- Processando URL {i} de {total_urls} ---")
        
        # Consome o gerador da esteira e repassa os eventos
        resultado_lote = None
        for evento_json in executar_esteira_publicacao_doe(url, id_usuario):
            evento = json.loads(evento_json)
            if evento.get("status") == "done":
                resultado_lote = evento.get("resultados")
                # Não repassa o done individual, converte em log para não encerrar o stream
                yield json.dumps({"status": "log", "mensagem": f"Concluído processamento da URL {i}"}) + "\n"
            else:
                yield evento_json
                
        resultados_totais.append({
            "url": url,
            "resultado": resultado_lote
        })
        
    yield json.dumps({"status": "done", "resultados": {
        "sucesso": True,
        "total_urls_processadas": total_urls,
        "detalhes": resultados_totais
    }}) + "\n"
    logger.info("Processamento múltiplo finalizado!")

