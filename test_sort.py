import fitz
from business.esteira import baixar_doe
doc = fitz.open(stream=baixar_doe('http://imagens.seplag.ce.gov.br/PDF/20000630/do20000630p01.pdf'), filetype='pdf')
page = doc.load_page(43)
blocos = page.get_text("dict")["blocks"]

col_esq = []
col_dir = []
cabecalhos = []
meio = page.rect.width / 2

for b in blocos:
    if b.get("type", 0) != 0: continue
    x0, y0, x1, y1 = b["bbox"]
    if (x1 - x0) > page.rect.width * 0.7:
        cabecalhos.append(b)
    elif (x0 + x1) / 2 < meio:
        col_esq.append(b)
    else:
        col_dir.append(b)

col_esq.sort(key=lambda b: b["bbox"][1])
col_dir.sort(key=lambda b: b["bbox"][1])
cabecalhos.sort(key=lambda b: b["bbox"][1])

ordenados = cabecalhos + col_esq + col_dir
for b in ordenados:
    texto = "".join([s["text"] for l in b.get("lines", []) for s in l.get("spans", [])])
    print(texto[:50].replace("\n", " ") + "...")
