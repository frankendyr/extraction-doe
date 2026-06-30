
# Regras de Negócio - Extração do Diário Oficial (DOE)

## Limpeza do Secretariado
1. **Ativação da Limpeza**: A detecção da lista do Secretariado NÃO DEVE ter limite de número de linhas (ex: `idx < 50`). Decretos longos que começam na página 1 podem cruzar a fronteira para a página 2 (onde o Secretariado está) apenas depois de muitas dezenas de linhas. O gatilho correto é buscar a string exata "Governador" ou "GOVERNADOR" e deixar a limpeza descer até quebrar o padrão (encontrando ponto final, dígitos, etc).
2. **Identificação da Primeira Página**: A função que identifica se o decreto está no início do Diário Oficial (`verificar_decreto_primeira_pagina`) DEVE checar sempre as primeiras 3 páginas (`range(min(3, len(doc)))`), e não apenas a página 0. Nos DOEs antigos, o decreto frequentemente começa na página 2 ou 3 após uma capa visual.
