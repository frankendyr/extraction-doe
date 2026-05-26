from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import extraction_doe_api as doe_api

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


@app.post("/decreto-unico", summary="Executa o processamento de um decreto único com logs em tempo real (SSE)")
def executar_decreto_unico(req: DecretoUnicoRequest):
    """
    Aciona a extração de um único decreto e persiste no banco de dados.
    Retorna os logs em tempo real via Server-Sent Events (StreamingResponse).
    """
    gerador = doe_api.executar_esteira_decreto_unico(req.url_do_diario, req.numero_do_decreto)
    return StreamingResponse(gerador, media_type="text/event-stream")


@app.post("/decretos-lote-doe", summary="Executar esteira de processamento em lote de decretos de uma publicação do DOE com logs em tempo real (SSE)")
def executar_diario_lote(req: DiarioLoteRequest):
    """
    Orquestra o processamento completo de um Diário Oficial em lote.
    Retorna os logs em tempo real via Server-Sent Events (StreamingResponse).
    """
    gerador = doe_api.executar_esteira_publicacao_doe(req.url_do_diario)
    return StreamingResponse(gerador, media_type="text/event-stream")

@app.post("/listar-decretos-doe", summary="Listar os decretos de uma publicação do DOE")
def listar_decretos_publicacao(req: DiarioLoteRequest):
    """
    Baixa o Diário Oficial a partir da URL e lista todos os decretos contidos nele.
    """
    arquivo_doe = doe_api.baixar_doe(req.url_do_diario)
    
    if not arquivo_doe:
        raise HTTPException(status_code=400, detail={"sucesso": False, "mensagem": "Falha ao baixar o PDF da URL fornecida."})
        
    decretos = doe_api.listar_decretos_doe(arquivo_doe)
    
    return {
        "sucesso": True,
        "total": len(decretos),
        "decretos": decretos
    }


@app.get("/api/v1/decreto/{numero_decreto}", summary="Buscar decreto salvo no banco de dados", include_in_schema=False)
def buscar_decreto(numero_decreto: str):
    """
    Busca os dados de um decreto já extraído e seus anexos no banco.
    """
    resultado = doe_api.buscar_decreto_no_banco(numero_decreto)
    if not resultado.get("sucesso"):
        raise HTTPException(status_code=404, detail=resultado)
    return resultado
