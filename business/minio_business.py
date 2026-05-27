import json
from pathlib import Path
from mimetypes import guess_type
import boto3
from doe.minio_connection import obter_configuracoes_minio

def criar_cliente_s3(endpoint_url, access_key, secret_key):
    return boto3.client("s3", endpoint_url=endpoint_url, aws_access_key_id=access_key, aws_secret_access_key=secret_key, region_name="us-east-1")

def bucket_existe(s3, bucket_name):
    buckets = s3.list_buckets()["Buckets"]
    return bucket_name in [bucket["Name"] for bucket in buckets]

def tornar_bucket_publico(s3, bucket_name):
    public_policy = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Principal": {"AWS": ["*"]}, "Action": ["s3:GetObject"], "Resource": [f"arn:aws:s3:::{bucket_name}/*"]}]
    }
    s3.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(public_policy))

def garantir_bucket(s3, bucket_name, tornar_publico=True):
    if bucket_existe(s3, bucket_name):
        return False
    s3.create_bucket(Bucket=bucket_name)
    if tornar_publico:
        tornar_bucket_publico(s3, bucket_name)
    return True

def obter_content_type(file_path):
    content_type, _ = guess_type(file_path.name)
    return content_type if content_type else "application/octet-stream"

def subir_imagem(s3, bucket_name, file_path, nome_pasta, endpoint_url):
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {file_path.resolve()}")
    nome_pasta = nome_pasta.strip("/")
    object_name = f"{nome_pasta}/{file_path.name}"
    s3.upload_file(Filename=str(file_path), Bucket=bucket_name, Key=object_name, ExtraArgs={"ContentType": obter_content_type(file_path)})
    return f"{endpoint_url}/{bucket_name}/{object_name}"

def subir_imagens_para_pasta(endpoint_url, access_key, secret_key, bucket_name, nome_pasta, imagens, tornar_publico=True):
    s3 = criar_cliente_s3(endpoint_url, access_key, secret_key)
    garantir_bucket(s3, bucket_name, tornar_publico)
    links = []
    for imagem in imagens:
        links.append(subir_imagem(s3, bucket_name, file_path=imagem, nome_pasta=nome_pasta, endpoint_url=endpoint_url))
    return links


def enviar_imagens_minio(numero_decreto: str, xrefs: list, logger) -> list:
    if not xrefs:
        return []

    numero_limpo = str(numero_decreto).replace(".", "")
    caminhos_locais = []
    base_path = Path.cwd()
    pasta_destino = base_path / "imagens_decretos"

    for xref in set(xrefs):
        caminho_imagem = pasta_destino / f"fig_{numero_limpo}_{xref}.png"
        if caminho_imagem.exists():
            caminhos_locais.append(caminho_imagem)

    if not caminhos_locais:
        return []

    logger.info(f"☁️ Subindo {len(caminhos_locais)} imagem(ns) do decreto {numero_decreto} para o MinIO...")

    try:
        # 👇 Puxa as configurações diretamente da fábrica 👇
        config_minio = obter_configuracoes_minio()

        links_gerados = subir_imagens_para_pasta(
            endpoint_url=config_minio["endpoint_url"],
            access_key=config_minio["access_key"],
            secret_key=config_minio["secret_key"],
            bucket_name=config_minio["bucket_name"],
            nome_pasta=f"decretos/{numero_limpo}",
            imagens=caminhos_locais,
            tornar_publico=True
        )
        return links_gerados

    except Exception as e:
        logger.error(f"⚠️ Falha ao subir imagens para o MinIO: {e}")
        return []