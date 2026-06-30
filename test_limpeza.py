import sys
from business.esteira import limpar_texto_pagina_um

texto = """DECRETO Nº33.856, de 18 de dezembro de 2020.
ABRE AOS ÓRGÃOS E ENTIDADES CRÉDITO SUPLEMENTAR DE R$ 181.218.071,77 PARA REFORÇO DE
DOTAÇÕES ORÇAMENTÁRIAS CONSIGNADAS NO VIGENTE ORÇAMENTO.
O GOVERNADOR DO ESTADO DO CEARÁ, no uso das suas atribuições que lhe confere o inciso IV, do art. 88, da Constituição Estadual,
combinado com os incisos I, II e III do § 1º, do art.43, da Lei Federal nº 4.320, de 17 de março de 1964, do art. 5º da Lei Estadual nº 17.161, de 27 de
dezembro de 2019 – LOA 2020 e com o art. 40 da Lei Estadual nº 16.944, de 17 de julho de 2019 – LDO 2020. CONSIDERANDO a necessidade de realocar
dotações orçamentárias da DEFENSORIA PÚBLICA GERAL DO ESTADO – DPGE, entre projetos e atividades, para atender despesas com estruturação
física e melhoria tecnológica dos núcleos e unidades de atendimento jurídico. CONSIDERANDO a necessidade de suplementar dotações orçamentárias
da EMPRESA DE ASSISTÊNCIA TÉCNICA E EXTENSÃO RURAL DO CEARÁ – EMATERCE, para atender contrapartida de Convênio / MAPA
(Ministério da Agricultura Pecuária e Abastecimento). CONSIDERANDO a necessidade de realocar dotações orçamentárias do FUNDO DE ASSISTÊNCIA
A SAÚDE DOS SERVIDORES PÚBLICOS DO ESTADO DO CEARÁ – FASSEC, entre projetos e atividades, para atender despesas com assistência
hospitalar. CONSIDERANDO a necessidade de realocar e suplementar dotações orçamentárias do FUNDO ESTADUAL DE CULTURA – FEC, entre
projetos e atividades, para atender despesas com realização de edital de criação e produção artística – Aldir Blanc. CONSIDERANDO a necessidade de
realocar dotações orçamentárias do FUNDO FINANCEIRO – FUNAPREV, entre projetos e atividades, para atender despesas com pagamento de inativos
e pensionistas da Assembleia Legislativa, Tribunal de Contas e do Ensino Superior. CONSIDERANDO a necessidade de realocar dotações orçamentárias
da FUNDAÇÃO DE TELEDUCAÇÃO DO CEARÁ – FUNTELC, entre projetos e atividades, para atender despesas com manutenção e expansão da
oferta de serviços televisivos da TV Ceará. CONSIDERANDO a necessidade de realocar e suplementar dotações orçamentárias do FUNDO ESTADUAL
DE SAÚDE – FUNDES, entre projetos, atividades, regiões e modalidades, para atender ao ajuste orçamentário das Coordenadorias Regionais de Saúde,
CIDH, Escola de Saúde Pública, central de regulação, terceirização, Laboratório Central, IPC, UPA de Quixadá, Centro de Saúde Dona Libânia, contratos
de gestão, atender demandas de investimentos das unidades da rede SESA com aquisição de equipamentos, materiais permanentes, ajuste para complemento
de gastos do SAMU, para o encerramento do exercício 2020, ampliação e modernização do parque tecnológico do HGF e desenvolvimento de medidas de
enfrentamento e contenção da infecção humana pela Covid-19. CONSIDERANDO a necessidade de realocar dotações orçamentárias do FUNDO ESPECIAL
DE REAPARELHAMENTO E MODERNIZAÇÃO DO PODER JUDICIÁRIO - FERMOJU, entre projetos e atividades, para desenvolvimento da prestação
jurisdicional do 1º Grau. CONSIDERANDO a necessidade de realocar dotações orçamentárias do FUNDO DE REAPARELHAMENTO E MODERNIZAÇÃO
DO MINISTÉRIO PÚBLICO DO ESTADO DO CEARÁ – FRMMP, entre projetos e atividades, para viabilizar aquisição de equipamento para nova sede do
MPCE. CONSIDERANDO a necessidade de realocar dotações orçamentárias do INSTITUTO DE SAÚDE DOS SERVIDORES DO ESTADO DO CEARÁ
– ISSEC, entre projetos e atividades, para pagamento da folha de pessoal referente à dezembro 2020. CONSIDERANDO a necessidade de realocar dotações
orçamentárias da PROCURADORIA GERAL DO ESTADO – PGE, entre projetos e atividades, para manutenção da área de tecnologia da informação e
comunicação. CONSIDERANDO a necessidade de realocar dotações orçamentárias da PROCURADORIA GERAL DA JUSTIÇA – PGJ, entre projetos
e atividades, sendo o ajuste orçamentário necessário para viabilizar o pagamento da folha de pessoal de dezembro.. CONSIDERANDO a necessidade de
realocar dotações orçamentárias da SECRETARIA DA CIÊNCIA, TECNOLOGIA E EDUCAÇÃO SUPERIOR – SECITECE, entre projetos e atividades,
para despesas com pagamento de pessoal e viabilizar repactuações da terceirização. CONSIDERANDO a necessidade de realocar e suplementar dotações
orçamentárias da SECRETARIA DA EDUCAÇÃO – SEDUC, entre projetos, atividades, regiões e modalidades, para atender despesas com melhoria
da infraestrutura das escolas municipais de ensino fundamental e pagamento de pessoal do magistério. CONSIDERANDO a necessidade de realocar e
suplementar dotações orçamentárias da SECRETARIA DAS CIDADES – SCIDADES, entre projetos e atividades, para atender despesas com pagamento
de indenizações referente aos projetos de melhorias urbana e ambiental do rio Maranguapinho e projeto rio Maranguapinho trecho zero. CONSIDERANDO
a necessidade de realocar dotações orçamentárias da SECRETARIA DA CULTURA – SECULT, para atender despesas de termo de ajuste com município
de Redenção. CONSIDERANDO a necessidade de suplementar dotações orçamentárias da SECRETARIA DA INFRAESTRUTURA – SEINFRA, para
celebração de convênios para apoio aos municípios do Ceará. CONSIDERANDO a necessidade de suplementar dotações orçamentárias da SECRETARIA
DA ADMINISTRAÇÃO PENITENCIÁRIA – SAP, para pagamento de munições, construção de uma penitenciária de segurança máxima e aquisição de
material permanente. CONSIDERANDO a necessidade de realocar e suplementar dotações orçamentárias da SECRETARIA DO DESENVOLVIMENTO
AGRÁRIO – SDA, entre projetos, atividades e regiões, para atender aos seguintes projetos: apoio aos povos de terreiro com atividades agroecológicas e de
economia solidária e manutenção do parque de exposição agropecuária de Sobral – EXPONORTE, assistência técnica e extensão rural em assentamentos
rurais e realização de feiras municipais da reforma agrária e agricultura familiar. CONSIDERANDO a necessidade de realocar dotações orçamentárias da
SECRETARIA DO MEIO AMBIENTE – SEMA, entre projetos, atividades, regiões e modalidades, para atender despesas com a realização da gestão das
unidades de conservação estaduais. CONSIDERANDO a necessidade de realocar dotações orçamentárias da SECRETARIA DO PLANEJAMENTO E
GESTÃO – SEPLAG, entre projetos e atividades, para atender a manutenção da área de tecnologia da informação e comunicação. CONSIDERANDO a
necessidade de suplementar dotações orçamentárias da SECRETARIA DOS RECURSOS HÍDRICOS – SRH, para execução e supervisão do projeto Cinturão
de Águas do Ceará - CAC DECRETA:
Art. 1º – Fica aberto o crédito suplementar ao orçamento dos seguintes órgãos: da Defensoria Pública Geral do Estado, da Empresa de Assistência
Técnica e Extensão Rural do Ceará, do Fundo de Assistência a Saúde dos Servidores Públicos do Estado do Ceará, do Fundo Estadual de Cultura, do Fundo
Financeiro /Funaprev, da Fundação de Teleducação do Ceará, do Fundo Estadual de Saúde, do Fundo Especial de Reaparelhamento e Modernização do
Poder Judiciário, do Fundo de Reaparelhamento e Modernização do Ministério Público do Estado do Ceará, do Instituto de Saúde dos Servidores do Estado
do Ceará, da Procuradoria Geral do Estado, da Procuradoria Geral da Justiça, da Secretaria da Ciência, Tecnologia e Educação Superior, da Secretaria da
Educação, da Secretaria das Cidades, da Secretaria da Cultura, da Secretaria da Infraestrutura, da Secretaria da Administração Penitenciária, da Secretaria do
Desenvolvimento Agrário, da Secretaria do Meio Ambiente, da Secretaria do Planejamento e Gestão e da Secretaria dos Recursos Hídricos, no valor de R$
181.218.071,77 (CENTO E OITENTA E UM MILHÕES, DUZENTOS E DEZOITO MIL, SETENTA E UM REAIS E SETENTA E SETE CENTAVOS),
para reforço de dotações orçamentárias consignadas ao vigente orçamento, conforme os Anexos III e IV.
Governador
CAMILO SOBREIRA DE SANTANA
Vice-Governadora
MARIA IZOLDA CELA DE ARRUDA COELHO
Casa Civil
FRANCISCO DAS CHAGAS CIPRIANO VIEIRA
Procuradoria Geral do Estado
JUVÊNCIO VASCONCELOS VIANA
Controladoria e Ouvidoria-Geral do Estado
ALOÍSIO BARBOSA DE CARVALHO NETO
Secretaria de Administração Penitenciária
LUÍS MAURO ALBUQUERQUE ARAÚJO
Secretaria das Cidades
JOSÉ JÁCOME CARNEIRO ALBUQUERQUE
Secretaria da Ciência, Tecnologia e Educação Superior
INÁCIO FRANCISCO DE ASSIS NUNES ARRUDA
Secretaria da Cultura
FABIANO DOS SANTOS
Secretaria do Desenvolvimento Agrário
FRANCISCO DE ASSIS DINIZ
Secretaria do Desenvolvimento Econômico e Trabalho
FRANCISCO DE QUEIROZ MAIA JÚNIOR
Secretaria da Educação
ELIANA NUNES ESTRELA
Secretaria do Esporte e Juventude
ROGÉRIO NOGUEIRA PINHEIRO
Secretaria da Fazenda
FERNANDA MARA DE OLIVEIRA MACEDO
CARNEIRO PACOBAHYBA
Secretaria da Infraestrutura
LUCIO FERREIRA GOMES
Secretaria do Meio Ambiente
ARTUR JOSÉ VIEIRA BRUNO
Secretaria do Planejamento e Gestão
RONALDO LIMA MOREIRA BORGES
(RESPONDENDO)
Secretaria da Proteção Social, Justiça, Cidadania,
Mulheres e Direitos Humanos
MARIA DO PERPÉTUO SOCORRO FRANÇA PINTO
Secretaria dos Recursos Hídricos
FRANCISCO JOSÉ COELHO TEIXEIRA
Secretaria da Saúde
CARLOS ROBERTO MARTINS RODRIGUES SOBRINHO
Secretaria da Segurança Pública e Defesa Social
SANDRO LUCIANO CARON DE MORAES
Secretaria do Turismo
ARIALDO DE MELLO PINHO
Controladoria Geral de Disciplina dos Órgãos
de Segurança Pública e Sistema Penitenciário
RODRIGO BONA CARNEIRO
<fig_33856_170>
2
DIÁRIO OFICIAL DO ESTADO  |  SÉRIE 3  |  ANO XII Nº281  | FORTALEZA, 18 DE DEZEMBRO DE 2020
<fig_33856_172>
Art. 2º – Os recursos necessários à execução deste Decreto decorrem de anulações de dotações orçamentárias, excesso de arrecadação e superavit
financeiro, conforme os Anexos I e II.
Art. 3º – Este decreto entra em vigor na data da sua publicação.
Art. 4º – Revogam-se as disposições em contrário.
PALÁCIO DA ABOLIÇÃO, DO GOVERNO DO ESTADO DO CEARÁ, em Fortaleza, 18 de dezembro de 2020.
Camilo Sobreira de Santana
GOVERNADOR
Ronaldo Lima Moreira Borges
SECRETÁRIO DO PLANEJAMENTO E GESTÃO, RESPONDENDO
ANEXO I A QUE SE REFERE O ART. 2º DO DECRETO Nº33.856, DE 18 DE DEZEMBRO DE 2020
ANULAÇÃO DE CRÉDITO ORDINÁRIO - DIRETAS"""

texto_limpo = limpar_texto_pagina_um(texto)
print(texto_limpo)
