# API Extraction Service - Diário Oficial 🚀

Esta API foi construída para automatizar a varredura, download e extração de metadados inteligentes de decretos publicados no Diário Oficial do Estado, alimentando o banco de dados e o repositório de arquivos (MinIO) de forma silenciosa e eficiente.

## 🛠️ Como Executar o Projeto

```bash
# Iniciar o servidor FastAPI
fastapi dev main.py
# Ou via Uvicorn na porta 8000:
uvicorn main:app --host 127.0.0.1 --port 8000
```
**Acessar Documentação (Swagger):** http://127.0.0.1:8000/docs

---

## 📡 Endpoints Disponíveis

### 1. `POST /listar-urls-decretos-por-periodo`
**Descrição:** Varredura de URLs de Diários Oficiais que possuem publicações de decretos dentro de um intervalo pré-definido passado como parâmetro.
Gera URLs matemáticas para um intervalo de datas e filtra validando quais arquivos PDF realmente existem no servidor e quais contêm decretos válidos.
- **Payload:** `{"data_inicio": "10/05/2026", "data_fim": "20/05/2026"}`
- **Retorno:** JSON com a contagem total e uma lista de URLs prontas para extração.

### 2. `GET /montar-url`
**Descrição:** Montar a URL do Diário Oficial a partir de uma data.
Monta rapidamente a URL no padrão do Diário Oficial a partir de uma única data informada.
- **Query Params:** `?data=06/03/2026`
- **Retorno:** `{"sucesso": true, "data": "06/03/2026", "url": "https://imagens.seplag.ce.gov.br/PDF/..."}`

### 3. `POST /listar-decretos-doe`
**Descrição:** Listar os decretos de uma publicação do DOE.
Baixa o PDF da URL informada e retorna uma lista simplificada de todos os decretos e suas respectivas páginas, sem acionar a Inteligência Artificial.
- **Payload:** `{"url_do_diario": "URL_DO_PDF"}`
- **Retorno:** JSON contendo os nomes dos decretos e a página de cada um.

---

## ⚡ Endpoints de Extração (Streaming SSE)
As rotas de processamento executam requisições complexas (Download do PDF, Integração com IA, e Upload para MinIO/PostgreSQL). Por conta disso, elas utilizam a arquitetura **Server-Sent Events (SSE)**, que não espera tudo terminar para devolver um JSON enorme. Em vez disso, enviam eventos em tempo real (`yield`) enquanto a extração acontece.

### 4. `POST /extrair-decreto-unico`
**Descrição:** Executa a extração do texto de um único decreto com logs em tempo real (SSE).
Aciona a extração de apenas 1 decreto específico de uma edição do Diário Oficial.
- **Payload:** `{"url_do_diario": "URL", "numero_do_decreto": "12345"}`

### 5. `POST /extrair-decretos-doe-lote`
**Descrição:** Executar esteira de extração em lote de decretos de uma publicação do DOE com logs em tempo real (SSE).
Processa e extrai **todos** os decretos encontrados em um Diário Oficial de uma só vez.
- **Payload:** `{"url_do_diario": "URL"}`

---

## 💻 Como usar o SSE no Frontend (Javascript / React / Vue)

Diferente de chamadas tradicionais (`await response.json()`), para ver os logs das rotas de extração atualizando na tela em tempo real, o frontend precisa ler os pedaços de texto (*chunks*) à medida que chegam.

Aqui está um exemplo de código funcional usando Javascript puro (Fetch API):

```javascript
async function iniciarProcessamentoEmTempoReal() {
    const response = await fetch('http://127.0.0.1:8000/extrair-decretos-doe-lote', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream' // Opcional, mas boa prática
        },
        body: JSON.stringify({ url_do_diario: "SUA_URL_AQUI" })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");

    // Loop que ficará rodando até a extração acabar
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const pedacoDeTexto = decoder.decode(value, { stream: true });
        const linhas = pedacoDeTexto.split('\n'); // Uma requisição pode mandar mais de 1 linha junta

        for (const linha of linhas) {
            if (!linha.trim()) continue;

            // Transforma o texto recebido em um objeto Javascript real
            const evento = JSON.parse(linha);

            if (evento.status === "log") {
                console.log("🟡 Em andamento:", evento.mensagem);
                // Exemplo: Atualize uma <div> ou barra de progresso aqui
            } else if (evento.status === "error") {
                console.error("🔴 Erro na esteira:", evento.mensagem);
            } else if (evento.status === "done") {
                console.log("🟢 Sucesso! Resultado final salvo no banco:", evento.resultados);
            }
        }
    }
}
```

Neste modelo, a cada vez que o servidor Python chamar o `yield json.dumps()`, o laço `while` no Javascript vai pegar essa linha, permitindo que a tela do usuário pisque e avise: *"Baixando PDF..."*, *"Lendo anexos..."*, *"Salvando no banco..."*, garantindo uma experiência super fluida e moderna.