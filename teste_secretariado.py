import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from business.esteira import baixar_doe, extrair_texto_bruto_decreto, limpar_texto_pagina_um, limpar_texto_demais_paginas, separar_decreto_dos_anexos

url = "http://imagens.seplag.ce.gov.br/PDF/20190213/do20190213p01.pdf"
numero = "32.945"

arquivo = baixar_doe(url)
texto_bruto = extrair_texto_bruto_decreto(arquivo, numero)

if texto_bruto["sucesso"]:
    print("=== FINAL DO TEXTO BRUTO ===")
    print(texto_bruto["texto"][-2000:])
    
    texto_limpo = limpar_texto_pagina_um(texto_bruto["texto"])
    corpo, anexos = separar_decreto_dos_anexos(texto_limpo)
    
    print("\n=== FINAL DO CORPO PRINCIPAL ===")
    print(corpo[-1000:])
else:
    print("Falha na extração bruta")
