FROM python:3.11-slim
WORKDIR /app

# System deps required by PyMuPDF (fitz)
RUN apt-get update && apt-get install -y \
    libmupdf-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the fastembed BM25 model so it's baked into the image.
# Without this, the model downloads from HuggingFace on the first request,
# blocking document_rag_node and potentially timing out on Railway cold start.
RUN python -c "from fastembed import SparseTextEmbedding; SparseTextEmbedding('Qdrant/bm25')"

COPY . .

EXPOSE 8080
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
