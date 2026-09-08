# RAG Assistant

A starter Retrieval-Augmented Generation assistant with a FastAPI backend, React frontend, Chroma-ready data folder, and Ollama service in Docker Compose.

## Structure

- `backend/app/main.py` contains the FastAPI app factory.
- `backend/app/api/v1` contains versioned API routes for documents, chat, knowledge bases, and admin.
- `backend/app/services` contains ingestion, retrieval, chat, and citation orchestration.
- `backend/app/rag` contains loaders, chunking, embeddings, vector store, retriever, and Ollama wrappers.
- `data/uploads`, `data/chroma_db`, and `data/sample_docs` are mounted data folders.
- `frontend` is a minimal Vite React UI.

## Quick Start

1. Copy `.env.example` to `.env`.
2. Start the stack:

```bash
docker compose up --build
```

3. Open the API at `http://localhost:8000/docs`.
4. Open the frontend at `http://localhost:5173`.

## Local Backend Development

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Next Steps

- Replace placeholder embedding and vector store implementations with Chroma persistence.
- Expand loaders for PDF, DOCX, TXT, and CSV ingestion.
- Add Alembic migration files.
- Add authentication if `API_KEY` is not enough for your deployment.
