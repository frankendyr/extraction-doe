
import psycopg2
from dotenv import load_dotenv
import os
from pathlib import Path
import psycopg2

base_dir = Path(__file__).resolve().parent.parent
env_path = base_dir / ".env"

load_dotenv(env_path)

db_name = os.getenv('DB_NAME')
db_user = os.getenv('DB_USER')
db_port = int(os.getenv('DB_PORT'))
db_host = os.getenv('DB_HOST')
db_senha = os.getenv('DB_SENHA')


def conectar_db():
    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_senha
    )
    
    cursor = conn.cursor()
    return conn, cursor