import logging
import requests
import urllib3
from datetime import datetime, timedelta

from .esteira import baixar_doe, listar_decretos_doe

# Desativa avisos de SSL (comum em sites do governo)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger("ExtratorDOE")

# ==============================================================================
# FASE 1: GERAÇÃO MATEMÁTICA DE DATAS E URLs
# ==============================================================================
def gerar_urls_por_periodo(data_inicio: str, data_fim: str) -> list:
    """Gera todas as URLs matemáticas de um período, incluindo fins de semana."""
    formato_entrada = "%d/%m/%Y"
    urls_geradas = []

    try:
        data_inicial_dt = datetime.strptime(data_inicio, formato_entrada)
        data_final_dt = datetime.strptime(data_fim, formato_entrada)

        if data_inicial_dt > data_final_dt:
            logger.error("❌ A data inicial não pode ser maior que a data final.")
            return []

        delta_dias = (data_final_dt - data_inicial_dt).days

        for i in range(delta_dias + 1):
            data_atual = data_inicial_dt + timedelta(days=i)
            data_formatada_url = data_atual.strftime("%Y%m%d")

            url = f"http://imagens.seplag.ce.gov.br/PDF/{data_formatada_url}/do{data_formatada_url}p01.pdf"
            urls_geradas.append(url)

        return urls_geradas
    except ValueError as e:
        logger.error(f"❌ Erro de formatação de data: {e}")
        return []

# ==============================================================================
# FASE 2: FILTRO DE REDE (O ARQUIVO EXISTE NO SERVIDOR?)
# ==============================================================================
def filtrar_urls_validas(urls_geradas: list) -> list:
    """Bate na porta do servidor e descarta links quebrados (ex: fins de semana)."""
    urls_validas = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    sessao = requests.Session()

    logger.info(f"🔎 Fase 2: Testando a existência de {len(urls_geradas)} URLs geradas...")

    for url in urls_geradas:
        try:
            # stream=True baixa apenas o cabeçalho, sendo super rápido
            resposta = sessao.get(url, verify=False, timeout=10, headers=headers, stream=True)
            content_type = resposta.headers.get('Content-Type', '')
            status = resposta.status_code

            if status == 200 and 'application/pdf' in content_type:
                urls_validas.append(url)
            resposta.close()
        except requests.exceptions.RequestException:
            pass # Ignora erros de conexão em links mortos

    sessao.close()
    logger.info(f"✅ Encontrados {len(urls_validas)} PDFs reais no servidor.")
    return urls_validas

# ==============================================================================
# FASE 3: FILTRO DE CONTEÚDO (POSSUI DECRETOS?)
# ==============================================================================
def filtrar_urls_com_decretos(urls_validas: list) -> list:
    """Abre os PDFs confirmados e mantém apenas as URLs que possuem decretos."""
    urls_com_decretos = []

    logger.info(f"🧠 Fase 3: Lendo as páginas de {len(urls_validas)} diários em busca de decretos...")

    for url in urls_validas:
        arquivo_pdf = baixar_doe(url)

        if not arquivo_pdf:
            continue

        lista_decretos = listar_decretos_doe(arquivo_pdf)
        total_decretos = len(lista_decretos)

        if total_decretos > 0:
            urls_com_decretos.append(url)
            logger.info(f"   🟢 APROVADO: {url} ({total_decretos} decretos)")
        else:
            logger.warning(f"   🔴 DESCARTADO: {url} (0 decretos encontrados)")

    logger.info(f"✅ Filtragem concluída! {len(urls_com_decretos)} links possuem decretos.")
    return urls_com_decretos

# ==============================================================================
# FUNÇÃO ORQUESTRADORA PARA A API
# ==============================================================================
def orquestrar_varredura(data_inicio: str, data_fim: str) -> dict:
    """Executa as três fases da varredura de URLs."""
    urls_brutas = gerar_urls_por_periodo(data_inicio, data_fim)
    
    if not urls_brutas:
        return {"sucesso": False, "mensagem": "Nenhuma URL pôde ser gerada ou datas inválidas."}
        
    urls_existentes = filtrar_urls_validas(urls_brutas)
    urls_premiadas = filtrar_urls_com_decretos(urls_existentes)
    
    return {
        "sucesso": True,
        "total_encontrado": len(urls_premiadas),
        "urls": urls_premiadas
    }

def montar_url_por_data(data: str) -> dict:
    """Monta a URL do Diário Oficial a partir de uma data no formato dd/mm/yyyy."""
    formato_entrada = "%d/%m/%Y"
    try:
        data_dt = datetime.strptime(data, formato_entrada)
        data_formatada_url = data_dt.strftime("%Y%m%d")
        url = f"https://imagens.seplag.ce.gov.br/PDF/{data_formatada_url}/do{data_formatada_url}p01.pdf"
        
        return {
            "sucesso": True,
            "data": data,
            "url": url
        }
    except ValueError as e:
        logger.error(f"❌ Erro de formatação de data: {e}")
        return {"sucesso": False, "mensagem": f"Formato de data inválido. Use dd/mm/yyyy. Detalhes: {e}"}
