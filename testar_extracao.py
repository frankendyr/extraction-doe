import os
import sys
import json
from dotenv import load_dotenv

# Carrega variáveis de ambiente, caso existam, para o Gemini funcionar
load_dotenv()

from business.esteira import (
    baixar_doe,
    extrair_texto_bruto_decreto,
    separar_decreto_dos_anexos,
    processar_texto_com_llm
)

def testar_extracao(url: str, numero_decreto: str):
    print(f"\n===========================================")
    print(f"Iniciando teste de extração para o Decreto: {numero_decreto}")
    print(f"URL do DOE: {url}")
    print(f"===========================================\n")

    print("[1/5] Baixando PDF do Diário Oficial...")
    arquivo_doe = baixar_doe(url)
    if not arquivo_doe:
        print("❌ Falha ao baixar o PDF. Verifique a URL.")
        return

    print("[2/5] Extraindo texto bruto e figuras...")
    resultado_extracao = extrair_texto_bruto_decreto(arquivo_doe, numero_decreto)
    
    if not resultado_extracao.get("sucesso"):
        print(f"❌ {resultado_extracao.get('mensagem')}")
        return

    texto_bruto = resultado_extracao.get("texto", "")
    tem_figuras = resultado_extracao.get("tem_figuras", False)
    
    print(f"✅ Texto extraído com sucesso! Tamanho: {len(texto_bruto)} caracteres.")
    if tem_figuras:
        print(f"✅ Figuras detectadas no decreto (as imagens foram salvas localmente).")
    else:
        print(f"✅ Nenhuma figura detectada.")

    print("\n[3/5] Separando Corpo Principal dos Anexos...")
    corpo, anexos = separar_decreto_dos_anexos(texto_bruto)
    
    print(f"✅ Corpo Principal: {len(corpo)} caracteres.")
    print(f"✅ Anexos: {len(anexos)} caracteres.")

    modelo_padrao = "models/gemini-1.5-flash"
    id_teste = "teste-terminal"

    print("\n[4/5] Processando Corpo Principal com IA (Buscando Estruturas Tabulares)...")
    corpo_formatado = processar_texto_com_llm(
        nome_parte="Decreto", 
        texto=corpo, 
        modelo=modelo_padrao, 
        id_usuario=id_teste, 
        id_documento=id_teste
    )

    print("\n[5/5] Processando Anexos com IA (Buscando Estruturas Tabulares)...")
    if anexos.strip():
        anexos_formatados = processar_texto_com_llm(
            nome_parte="Anexos", 
            texto=anexos, 
            modelo=modelo_padrao, 
            id_usuario=id_teste, 
            id_documento=id_teste
        )
    else:
        anexos_formatados = "Sem anexos."

    print("\n\n" + "="*50)
    print("                RESULTADO FINAL                ")
    print("="*50 + "\n")
    
    print("------------- CORPO PRINCIPAL -------------")
    print(corpo_formatado)
    print("-" * 43 + "\n")
    
    print("----------------- ANEXOS ------------------")
    print(anexos_formatados)
    print("-" * 43 + "\n")

    print("===========================================")
    print("Teste finalizado (nenhum dado foi gravado no banco).")


if __name__ == "__main__":
    print("--- Teste de Extração Local do DOE ---")
    url_input = input("Digite a URL do PDF do Diário Oficial: ").strip()
    decreto_input = input("Digite o número do Decreto (ex: 25.939): ").strip()
    
    if url_input and decreto_input:
        testar_extracao(url_input, decreto_input)
    else:
        print("URL e Número do Decreto são obrigatórios!")
