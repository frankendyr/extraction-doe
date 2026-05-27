

# Para chamar a API
uvicorn main:app --host 127.0.0.1 --port 8001

# Documentação
http://127.0.0.1:8001/docs


/opt/API_EXTRACTION_SERVICE
├── business
│   ├── esteira.py
│   └── minio_business.py
├── doe
│   ├── db_connection.py
│   ├── esteira_doe.py
│   └── minio_connection.py
├── venv
├── .env
├── .gitignore
├── leitor_de_logs.html
├── main.py
├── README.md
└── requirements.txt