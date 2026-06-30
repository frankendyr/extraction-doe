import sys
from business.esteira import limpar_texto_pagina_um

texto = """Governador
CAMILO SOBREIRA DE SANTANA
Vice-Governadora
MARIA IZOLDA CELA DE ARRUDA COELHO
Secretaria da Educação
ELIANA NUNES ESTRELA
Secretaria do Esporte e Juventude
ROGÉRIO NOGUEIRA PINHEIRO
RODRIGO BONA CARNEIRO
2
DIÁRIO OFICIAL DO ESTADO  |  SÉRIE 3  |  ANO XII Nº281  | FORTALEZA, 18 DE DEZEMBRO DE 2020"""

linhas = texto.split('\n')
limpando_secretariado = False
buffer_linhas = []
linhas_limpas = []

import re

for linha in linhas:
    linha_limpa = linha.strip()
    linha_upper = linha_limpa.upper()

    tem_diario = "DIÁRIO OFICIAL" in linha_upper
    tem_outros = "SÉRIE" in linha_upper or "ANO" in linha_upper or "FORTALEZA" in linha_upper

    if tem_diario and tem_outros:
        if len(linhas_limpas) > 0 and linhas_limpas[-1].strip().isdigit():
            linhas_limpas.pop()
        continue

    if linha_limpa in ["Governador", "GOVERNADOR"]:
        limpando_secretariado = True
        buffer_linhas = []
        continue

    if limpando_secretariado:
        if not linha_limpa:
            continue

        quebrou_padrao = False
        ultimo_char = linha_limpa[-1] if linha_limpa else ""

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
                buffer_linhas = []
                continue
            else:
                buffer_linhas.append(linha)
                continue

        limpando_secretariado = False
        linhas_limpas.extend(buffer_linhas)
        buffer_linhas = []

    linhas_limpas.append(linha)

print('\n'.join(linhas_limpas))
