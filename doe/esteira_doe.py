import psycopg2
from doe.db_connection import conectar_db
import logging
import json
import re
from datetime import datetime

# Configuração básica do logger para a API
logger = logging.getLogger("ExtratorDOE")
logger.setLevel(logging.INFO)
# Configura o formato da mensagem: [DATA HORA] [NÍVEL] Mensagem
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
if not logger.handlers:
    logger.addHandler(handler)

def salvar_no_banco(resultado_json: dict, id_lote):
    """
    Realiza a conexão com o banco de homologação usando a fábrica central,
    calcula o próximo index e insere os dados extraídos usando a regra contra duplicidade.
    """
    if not resultado_json.get("sucesso") or not resultado_json.get("dados"):
        print("Nenhum dado disponível para salvar.")
        return

    def formatar_para_varchar(valor):
        if isinstance(valor, list):
            return ", ".join(valor) if valor else ""
        return valor if valor is not None else ""

    conn = None
    cursor = None
    try:
        # SIMPLIFICAÇÃO APLICADA: Conexão desacoplada
        conn, cursor = conectar_db()

        # Busca o maior index atual
        cursor.execute("SELECT COALESCE(MAX(index), -1) FROM documento_extraido;")
        ultimo_index = cursor.fetchone()[0]

        # O PULO DO GATO (ON CONFLICT): O PostgreSQL lida com a duplicidade sozinho!
        # query_insert = """
        #     INSERT INTO documento_extraido (
        #         index, id_nome_decreto, nup, viproc, pagina, orgao_entidade_esfera,
        #         pi_entes_programas, pi_pessoas_fisicas, pi_pessoas_juridicas,
        #         pi_municipios, responsaveis, data_diario, url, original, anexos,
        #         arquivo_origem, id_tipo, id_documento, processado, data_criacao
        #     ) VALUES (
        #         %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        #     ) ON CONFLICT (id_documento) DO NOTHING;
        # """
        
        query_insert = """
            INSERT INTO documento_extraido (
                index, id_nome_decreto, nup, viproc, pagina, orgao_entidade_esfera,
                pi_entes_programas, pi_pessoas_fisicas, pi_pessoas_juridicas,
                pi_municipios, responsaveis, data_diario, url, original, anexos,
                arquivo_origem, id_tipo, id_documento, id_lote, processado, data_criacao
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) ON CONFLICT (id_documento, id_lote) DO NOTHING;
        """

        total_inseridos = 0
        total_duplicados = 0

        for item in resultado_json["dados"]:
            meta = item["metadados"]
            textos = item["textos"]

            ultimo_index += 1

            valores = (
                ultimo_index,
                meta["id_nome_decreto"],
                formatar_para_varchar(meta["nup"]),
                meta["viproc"],
                meta["pagina"],
                meta["orgao_entidade_esfera"],
                formatar_para_varchar(meta["pi_entes_programas"]),
                formatar_para_varchar(meta["pi_pessoas_fisicas"]),
                formatar_para_varchar(meta["pi_pessoas_juridicas"]),
                formatar_para_varchar(meta["pi_municipios"]),
                formatar_para_varchar(meta["responsaveis"]),
                meta["data_diario"],
                meta["url"],
                textos["original"],
                textos["anexos"],
                meta["arquivo_origem"],
                meta.get("id_tipo", 1),
                meta["id_documento"],
                id_lote,
                meta.get("processado", True),
                meta["data_criacao"]
            )

            cursor.execute(query_insert, valores)

            # O cursor.rowcount informa quantas linhas foram afetadas.
            if cursor.rowcount == 1:
                total_inseridos += 1
            else:
                total_duplicados += 1
                ultimo_index -= 1 # Retrocede o número do index para não "pular" números na tabela

        conn.commit()

        # Relatório final na tela
        print(f"\nRELATÓRIO DO BANCO DE DADOS:")
        print(f"   {total_inseridos} novos decreto(s) salvo(s).")
        if total_duplicados > 0:
            print(f"   {total_duplicados} decreto(s) ignorado(s) pois já existiam (Regra UNIQUE).")

        return total_inseridos

    except psycopg2.Error as e:
        print(f"\nErro na operação de banco de dados:\n{e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def salvar_anexos_no_banco(resultado_json: dict, id_lote):
    """
    Varre o JSON final em busca de links de imagens no MinIO e
    insere os metadados na tabela documento_extraido_anexo usando a conexão central.
    """
    if not resultado_json.get("sucesso") or not resultado_json.get("dados"):
        return

    conn = None
    cursor = None
    try:
        # SIMPLIFICAÇÃO APLICADA: Conexão desacoplada
        conn, cursor = conectar_db()

        # Prevenção: Descobre o maior ID atual para fazer o autoincremento seguro
        cursor.execute("SELECT COALESCE(MAX(id), 0) FROM documento_extraido_anexo;")
        ultimo_id = cursor.fetchone()[0]

        query_insert = """
            INSERT INTO documento_extraido_anexo (
                id, id_documento, tipo_anexo, anexo, sequencia_anexo, processado, data_criacao
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s
            );
        """

        total_anexos_salvos = 0

        for item in resultado_json["dados"]:
            meta = item["metadados"]
            links_imagens = meta.get("links_imagens", [])

            if not links_imagens:
                continue

            id_doc = meta["id_documento"]
            data_criacao = meta["data_criacao"]

            for sequencia, link_minio in enumerate(links_imagens, start=1):
                ultimo_id += 1

                valores = (
                    ultimo_id,
                    id_doc,
                    "imagem",
                    link_minio,
                    sequencia,
                    False,
                    data_criacao,
                    id_lote
                )

                cursor.execute(query_insert, valores)
                total_anexos_salvos += 1

        conn.commit()

        if total_anexos_salvos > 0:
            print(f"   {total_anexos_salvos} anexo(s) de imagem vinculado(s) no banco com sucesso!")

    except psycopg2.Error as e:
        print(f"\nErro na operação do banco de dados (Tabela de Anexos):\n{e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def buscar_decreto_no_banco(numero_decreto: str) -> dict:
    """
    Busca os dados de um decreto e seus anexos agregados em formato JSON.
    """
    logger.info(f"Iniciando busca no banco pelo Decreto Nº {numero_decreto}...")
    numero_limpo = str(numero_decreto).replace(".", "").strip()

    try:
        # Utiliza a conexão desacoplada
        # conn = obter_conexao_banco()
        # cursor = conn.cursor(cursor_factory=RealDictCursor)
        conn, cursor = conectar_db()

        query = """
            SELECT
                d.id_documento,
                d.id_nome_decreto,
                d.data_diario,
                d.url,
                d.pagina,
                d.original AS texto_original,
                d.anexos AS texto_anexos,
                COALESCE(
                    json_agg(a.anexo) FILTER (WHERE a.anexo IS NOT NULL),
                    '[]'::json
                ) AS links_imagens
            FROM documento_extraido d
            LEFT JOIN documento_extraido_anexo a ON d.id_documento = a.id_documento
            WHERE REPLACE(d.id_nome_decreto, '.', '') ILIKE %s
            GROUP BY
                d.id_documento, d.id_nome_decreto, d.data_diario, d.url, d.pagina, d.original, d.anexos;
        """

        cursor.execute(query, (f"%{numero_limpo}%",))
        resultado = cursor.fetchone()

        cursor.close()
        conn.close()

        if resultado:
            logger.info(f"Decreto {numero_decreto} encontrado com sucesso na base!")
            return {"sucesso": True, "dados": dict(resultado)}
        else:
            logger.warning(f"Decreto {numero_decreto} não encontrado na base de dados.")
            return {"sucesso": False, "mensagem": f"O Decreto Nº {numero_decreto} não foi encontrado."}

    except psycopg2.Error as e:
        logger.error(f"Erro crítico ao consultar o banco de dados:\n{e}")
        return {"sucesso": False, "mensagem": "Erro interno do servidor ao tentar consultar o banco de dados."}

def criar_lote_decretos(url_fonte_lote: str, usuario: str) -> int:
    """
    Cria um registro de lote no banco de dados e retorna o ID gerado.
    Extrai a data do diário a partir da URL para a coluna periodo_importacao.
    """
    logger.info(f"Criando registro de lote para o usuário {usuario}...")
    
    # Extração da data pela URL (ex: .../PDF/20260422/do...)
    periodo_importacao = None
    match = re.search(r'/(\d{4})(\d{2})(\d{2})/', url_fonte_lote)
    if match:
        periodo_importacao = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

    conn = None
    cursor = None
    try:
        conn, cursor = conectar_db()
        query = """
            INSERT INTO lote_decretos (url_fonte_lote, usuario, data_importacao, periodo_importacao)
            VALUES (%s, %s, NOW(), %s)
            RETURNING id;
        """
        cursor.execute(query, (url_fonte_lote, usuario, periodo_importacao))
        id_lote = cursor.fetchone()[0]
        conn.commit()
        logger.info(f"Lote {id_lote} criado com sucesso!")
        return id_lote
    except psycopg2.Error as e:
        logger.error(f"Erro ao criar lote de decretos:\n{e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def atualizar_total_decretos_lote(id_lote: int, total_decretos: int):
    """
    Atualiza a quantidade de decretos que foram efetivamente extraídos e inseridos no banco.
    """
    conn = None
    cursor = None
    try:
        conn, cursor = conectar_db()
        query = "UPDATE lote_decretos SET decretos_extraidos = %s WHERE id = %s;"
        cursor.execute(query, (total_decretos, id_lote))
        conn.commit()
        logger.info(f"Lote {id_lote} atualizado: {total_decretos} decretos extraídos.")
    except psycopg2.Error as e:
        logger.error(f"Erro ao atualizar total de decretos do lote {id_lote}:\n{e}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
