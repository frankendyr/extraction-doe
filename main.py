from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import extraction_doe_api as doe_api

app = FastAPI(
    title="API de Extração do Diário Oficial",
    description="API simples para processar diários oficiais e extrair decretos usando LLM.",
    version="1.0.0"
)

# Modelos Pydantic para as requisições
class DecretoUnicoRequest(BaseModel):
    url_do_diario: str
    numero_do_decreto: str

class DiarioLoteRequest(BaseModel):
    url_do_diario: str


@app.post("/api/v1/esteira/decreto-unico", summary="Executar esteira para um decreto único")
def executar_decreto_unico(req: DecretoUnicoRequest):
    """
    Aciona a extração de um único decreto e persiste no banco de dados.
    """
    resultado = doe_api.executar_esteira_decreto_unico(req.url_do_diario, req.numero_do_decreto)
    if not resultado.get("sucesso"):
        # Em caso de falha controlada, retornamos um 400 Bad Request
        raise HTTPException(status_code=400, detail=resultado)
    return resultado


@app.post("/api/v1/esteira/diario-lote", summary="Executar esteira para todo o diário (em lote)")
def executar_diario_lote(req: DiarioLoteRequest):
    """
    Orquestra o processamento completo de um Diário Oficial em lote.
    """
    resultado = doe_api.executar_esteira_publicacao_doe(req.url_do_diario)
    if not resultado.get("sucesso"):
        raise HTTPException(status_code=400, detail=resultado)
    return resultado

@app.post("/api/v1/diario/listar-decretos", summary="Listar os decretos de uma publicação do DOE")
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


@app.get("/api/v1/decreto/{numero_decreto}", summary="Buscar decreto salvo no banco de dados")
def buscar_decreto(numero_decreto: str):
    """
    Busca os dados de um decreto já extraído e seus anexos no banco.
    """
    resultado = doe_api.buscar_decreto_no_banco(numero_decreto)
    if not resultado.get("sucesso"):
        raise HTTPException(status_code=404, detail=resultado)
    return resultado
