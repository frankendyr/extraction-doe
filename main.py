from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from business.esteira import executar_esteira_decreto_unico, executar_esteira_publicacao_doe, executar_listagem_decretos
from business.varredura_business import orquestrar_varredura, orquestrar_montagem_url

app = FastAPI(
    title="API_EXTRACTION_SERVICE",
    description="API para extrair os textos dos decretos publicados no diário oficial.",
    version="1.0.0"
)

# Adicionando CORS para permitir consumo do endpoint de streaming por arquivos HTML locais
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelos Pydantic para as requisições
class DecretoUnicoRequest(BaseModel):
    url_do_diario: str
    numero_do_decreto: str

class DiarioLoteRequest(BaseModel):
    url_do_diario: str
    id_usuario: str

class ListarDecretosRequest(BaseModel):
    url_do_diario: str

class VarreduraRequest(BaseModel):
    data_inicio: str
    data_fim: str


@app.post("/extrair-decreto-unico", summary="Executa a extração do texto de um único decreto com logs em tempo real (SSE)")
def executar_decreto_unico(req: DecretoUnicoRequest):
    """
    Aciona a extração de um único decreto e persiste no banco de dados.
    Retorna os logs em tempo real via Server-Sent Events (StreamingResponse).
    """
    gerador = executar_esteira_decreto_unico(req.url_do_diario, req.numero_do_decreto)
    return StreamingResponse(gerador, media_type="text/event-stream")


@app.post("/listar-urls-decretos-por-periodo", summary="Varredura de URLs de Diários Oficiais com logs em tempo real (SSE)")
def varredura_urls(req: VarreduraRequest):
    """
    Gera URLs para o período informado, verifica quais PDFs existem, 
    e filtra quais deles contêm decretos.
    Retorna a lista de URLs prontas para extração via SSE.
    """
    gerador = orquestrar_varredura(req.data_inicio, req.data_fim)
    return StreamingResponse(gerador, media_type="text/event-stream")

@app.get("/montar-url", summary="Montar a URL do Diário Oficial a partir de uma data com logs em tempo real (SSE)")
def montar_url(data: str):
    """
    Recebe uma data via Query Params (ex: ?data=06/03/2026) e retorna a URL padronizada via SSE.
    """
    gerador = orquestrar_montagem_url(data)
    return StreamingResponse(gerador, media_type="text/event-stream")

@app.post("/extrair-decretos-doe-lote", summary="Executar esteira de extração em lote de decretos de uma publicação do DOE com logs em tempo real (SSE)")
def executar_diario_lote(req: DiarioLoteRequest):
    """
    Orquestra o processamento completo de um Diário Oficial em lote.
    Retorna os logs em tempo real via Server-Sent Events (StreamingResponse).
    """
    gerador = executar_esteira_publicacao_doe(req.url_do_diario, req.id_usuario)
    return StreamingResponse(gerador, media_type="text/event-stream")

@app.post("/listar-decretos-doe", summary="Listar os decretos de uma publicação do DOE com logs em tempo real (SSE)")
def listar_decretos_publicacao(req: ListarDecretosRequest):
    """
    Baixa o Diário Oficial a partir da URL e lista todos os decretos contidos nele via SSE.
    """
    gerador = executar_listagem_decretos(req.url_do_diario)
    return StreamingResponse(gerador, media_type="text/event-stream")


@app.get("/api/v1/decreto/{numero_decreto}", summary="Buscar decreto salvo no banco de dados", include_in_schema=False)
def buscar_decreto(numero_decreto: str):
    """
    Busca os dados de um decreto já extraído e seus anexos no banco.
    """
    resultado = buscar_decreto_no_banco(numero_decreto)
    if not resultado.get("sucesso"):
        raise HTTPException(status_code=404, detail=resultado)
    return resultado
