from pathlib import Path
from dotenv import load_dotenv
import os

base_dir = Path(__file__).resolve().parent.parent
env_path = base_dir / ".env"

load_dotenv(env_path)

endpoint_url = os.getenv('ENDPOINT_URL')
access_key = os.getenv('ACCESS_KEY')
secret_key = os.getenv('SECRET_KEY')
bucket_name = os.getenv('BUCKET_NAME')





def obter_configuracoes_minio() -> dict:
    """
    Centraliza as credenciais e configurações de acesso ao MinIO.
    No futuro, esses valores podem ser facilmente trocados por variáveis de ambiente (os.getenv).
    """
    return {
        "endpoint_url": endpoint_url,
        "access_key": access_key,
        "secret_key": secret_key,
        "bucket_name": bucket_name
    }