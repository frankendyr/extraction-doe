import sys
from business.esteira import baixar_doe, extrair_texto_bruto_decreto, separar_decreto_dos_anexos

url = "http://imagens.seplag.ce.gov.br/PDF/20000405/do20000405p01.pdf"
arquivo_doe = baixar_doe(url)
texto_bruto = extrair_texto_bruto_decreto(arquivo_doe, "25.701")
print("=== TEXTO BRUTO ===")
print(texto_bruto["texto"])

corpo, anexos = separar_decreto_dos_anexos(texto_bruto["texto"])
print("\n=== CORPO PRINCIPAL ===")
print(corpo)
