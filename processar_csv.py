import sys
import os
import argparse
import pandas as pd
import re
import logging

# Configuração de logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Ajusta o sys.path para importar os módulos da aplicação
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from business.esteira import (
    baixar_doe,
    extrair_texto_bruto_decreto,
    verificar_decreto_primeira_pagina,
    limpar_texto_pagina_um,
    limpar_texto_demais_paginas,
    separar_decreto_dos_anexos,
    processar_texto_com_llm
)

def extrair_numero_decreto(id_str):
    """Extrai o número do decreto a partir da string de id (ex: 'DECRETO Nº32.284')."""
    if pd.isna(id_str):
        return None
    match = re.search(r"N[°ºoO\.]*\s*([\d\.]+)", str(id_str), re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def obter_data_doc(url_alvo):
    """Extrai a data do documento a partir da URL para a geração do ID."""
    match_data = re.search(r"(\d{8})", url_alvo)
    if match_data:
        data_bruta = match_data.group(1)
        return f"{data_bruta[6:]}{data_bruta[4:6]}{data_bruta[:4]}"
    return None

def processar_arquivo_csv(input_csv, output_csv="resultado.csv", modelo_llm="gemini-2.5-flash"):
    logger.info(f"Lendo o arquivo CSV: {input_csv}")
    
    try:
        df = pd.read_csv(input_csv)
    except Exception as e:
        logger.error(f"Erro ao ler o arquivo {input_csv}: {e}")
        return

    # Garante que as colunas 'decreto' e 'anexos' existam
    if 'decreto' not in df.columns:
        df['decreto'] = ""
    if 'anexos' not in df.columns:
        df['anexos'] = ""

    total_registros = len(df)
    logger.info(f"Total de registros a processar: {total_registros}")

    # Processa cada linha
    for index, row in df.iterrows():
        id_str = row.get("id")
        url = row.get("url")
        
        logger.info(f"[{index + 1}/{total_registros}] Processando ID: {id_str} | URL: {url}")
        
        # Pula se a url estiver vazia
        if pd.isna(url) or not str(url).startswith("http"):
            logger.warning(f"URL inválida na linha {index + 1}. Pulando...")
            continue
            
        num_decreto = extrair_numero_decreto(id_str)
        if not num_decreto:
            logger.warning(f"Não foi possível extrair o número do decreto de '{id_str}'. Pulando...")
            continue
            
        # 1. Download
        logger.info(f"[{num_decreto}] Baixando Diário Oficial...")
        arquivo_doe = baixar_doe(url)
        if not arquivo_doe:
            logger.error(f"[{num_decreto}] Falha no download. Pulando...")
            continue
            
        # 2. Extração de texto bruto
        logger.info(f"[{num_decreto}] Extraindo texto bruto...")
        texto_bruto = extrair_texto_bruto_decreto(arquivo_doe, num_decreto)
        if not texto_bruto["sucesso"]:
            logger.error(f"[{num_decreto}] Falha ao extrair texto bruto. Pulando...")
            continue
            
        # 3. Limpeza e separação
        logger.info(f"[{num_decreto}] Limpando texto e separando anexos...")
        is_pagina_um = verificar_decreto_primeira_pagina(arquivo_doe, num_decreto)
        
        if is_pagina_um:
            texto_limpo = limpar_texto_pagina_um(texto_bruto["texto"])
        else:
            texto_limpo = limpar_texto_demais_paginas(texto_bruto["texto"])
            
        decreto_principal, anexos = separar_decreto_dos_anexos(texto_limpo)
        
        # 4. Estruturação com LLM
        data_id_doc = obter_data_doc(url)
        numero_sem_ponto = str(num_decreto).replace(".", "")
        id_documento_gerado = f"1_{numero_sem_ponto}_{data_id_doc}" if data_id_doc else f"1_{numero_sem_ponto}"
        
        logger.info(f"[{num_decreto}] Estruturando Corpo Principal com LLM...")
        decreto_principal_formatado = processar_texto_com_llm(
            "Corpo do Decreto", 
            decreto_principal, 
            modelo_llm, 
            id_usuario="lote_csv",
            id_documento=id_documento_gerado,
            limite_chars=40000
        )
        
        anexos_formatados = ""
        if anexos and anexos.strip():
            logger.info(f"[{num_decreto}] Estruturando Anexos com LLM...")
            anexos_formatados = processar_texto_com_llm(
                "Anexos do Decreto", 
                anexos, 
                modelo_llm, 
                id_usuario="lote_csv",
                id_documento=id_documento_gerado,
                limite_chars=40000
            )
        else:
            logger.info(f"[{num_decreto}] Sem anexos para estruturar.")
            anexos_formatados = "não tem"
            
        # 5. Atualização no DataFrame
        df.at[index, 'decreto'] = decreto_principal_formatado
        df.at[index, 'anexos'] = anexos_formatados
        
        # Salva o arquivo CSV atualizado após cada registro
        df.to_csv(output_csv, index=False)
        logger.info(f"[{num_decreto}] Finalizado. Progresso salvo em '{output_csv}'.\n")
        
    logger.info("Processamento completo!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Processa um CSV de decretos e estrutura os textos.")
    parser.add_argument("input_csv", help="Caminho para o arquivo CSV de entrada.")
    parser.add_argument("--output", default="resultado.csv", help="Caminho para o arquivo CSV de saída (padrão: resultado.csv).")
    parser.add_argument("--modelo", default="gemini-2.5-flash", help="Nome do modelo da LLM a ser utilizado.")
    
    args = parser.parse_args()
    
    processar_arquivo_csv(args.input_csv, args.output, args.modelo)
