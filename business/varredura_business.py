import logging
import requests
import urllib3
import json
from datetime import datetime, timedelta

from .esteira import baixar_doe, listar_decretos_doe

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger("ExtratorDOE")

def gerar_urls_por_periodo(data_inicio: str, data_fim: str) -> list:
    formato_entrada = "%d/%m/%Y"
    urls_geradas = []
    try:
        data_inicial_dt = datetime.strptime(data_inicio, formato_entrada)
        data_final_dt = datetime.strptime(data_fim, formato_entrada)

        if data_inicial_dt > data_final_dt:
            logger.error("A data inicial não pode ser maior que a data final.")
            return []

        delta_dias = (data_final_dt - data_inicial_dt).days

        for i in range(delta_dias + 1):
            data_atual = data_inicial_dt + timedelta(days=i)
            data_formatada_url = data_atual.strftime("%Y%m%d")
            url = f"https://imagens.seplag.ce.gov.br/PDF/{data_formatada_url}/do{data_formatada_url}p01.pdf"
            urls_geradas.append(url)

        return urls_geradas
    except ValueError as e:
        logger.error(f"Erro de formatação de data: {e}")
        return []

def orquestrar_varredura(data_inicio: str, data_fim: str):
    logger.info(f"Iniciando varredura entre {data_inicio} e {data_fim}...")
    
    urls_brutas = gerar_urls_por_periodo(data_inicio, data_fim)
    if not urls_brutas:
        return {"sucesso": False, "mensagem": "Nenhuma URL pôde ser gerada ou datas inválidas."}
        
    logger.info(f"Fase 2: Testando a existência de {len(urls_brutas)} URLs geradas...")
    
    urls_validas = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
    sessao = requests.Session()
    for url in urls_brutas:
        url_teste = url.replace("http://", "https://", 1) if url.startswith("http://") else url
        try:
            resposta = sessao.get(url_teste, verify=False, timeout=15, headers=headers, stream=True)
            if resposta.status_code == 200 and ('application/pdf' in resposta.headers.get('Content-Type', '') or url_teste.endswith('.pdf')):
                urls_validas.append(url_teste)
            resposta.close()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Aviso ao verificar a URL '{url_teste}': {e}")
    sessao.close()
    
    logger.info(f"Encontrados {len(urls_validas)} PDFs reais no servidor.")
    logger.info(f"Fase 3: Lendo as páginas em busca de decretos...")
    
    urls_premiadas = []
    for i, url in enumerate(urls_validas, 1):
        url_base = url[:-7] # Exemplo: http://imagens.seplag.ce.gov.br/PDF/20231228/do20231228
        caderno_atual = 1
        url_caderno = url
        estado_poder_executivo = False
        
        while caderno_atual <= 50:
            arquivo_pdf = baixar_doe(url_caderno)
            if not arquivo_pdf:
                break
                
            resultado = listar_decretos_doe(arquivo_pdf, estado_inicial_executivo=estado_poder_executivo)
            lista_decretos = resultado["decretos"]
            governadoria_fechou = resultado["governadoria_fechou"]
            estado_poder_executivo = resultado["estado_final_executivo"]
            
            if len(lista_decretos) > 0:
                urls_premiadas.append(url_caderno)
                logger.info(f"APROVADO: {url_caderno} ({len(lista_decretos)} decretos)")
            else:
                logger.warning(f"DESCARTADO: {url_caderno} (0 decretos)")
                
            if governadoria_fechou:
                break
                
            # Se não fechou a governadoria, tenta o próximo caderno
            caderno_atual += 1
            num_formatado = f"{caderno_atual:02d}"
            url_caderno = f"{url_base}p{num_formatado}.pdf"
            
    logger.info(f"Varredura concluída! {len(urls_premiadas)} links possuem decretos.")
    return {"sucesso": True, "total_encontrado": len(urls_premiadas), "urls": urls_premiadas}

def montar_url_por_data(data: str) -> dict:
    formato_entrada = "%d/%m/%Y"
    try:
        data_dt = datetime.strptime(data, formato_entrada)
        data_formatada_url = data_dt.strftime("%Y%m%d")
        url = f"http://imagens.seplag.ce.gov.br/PDF/{data_formatada_url}/do{data_formatada_url}p01.pdf"
        return {"sucesso": True, "data": data, "url": url}
    except ValueError as e:
        logger.error(f"Erro de formatação de data: {e}")
        return {"sucesso": False, "mensagem": f"Formato de data inválido. Use dd/mm/yyyy. Detalhes: {e}"}

def orquestrar_montagem_url(data: str):
    yield json.dumps({"status": "log", "mensagem": f"Montando URL para a data {data}..."}) + "\n"
    resultado = montar_url_por_data(data)
    if resultado.get("sucesso"):
        yield json.dumps({"status": "done", "resultado": resultado}) + "\n"
    else:
        yield json.dumps({"status": "error", "mensagem": resultado.get("mensagem")}) + "\n"
