# RepoScope
### A graph-powered developer tool that ingests a GitHub repository, builds a typed code graph, and uses it for PR impact analysis, evidence-cited Q&amp;A, and ranked recommendations on what to work on next.

<div align="center">
  <img width="600" alt="image" src="https://github.com/user-attachments/assets/43806b3f-7a71-4557-8916-7ee9b7eb6bd9" />
</div>

## Local development

Requirements: Python 3.11+, Node.js 20+, and Docker (for the local PostgreSQL database).

1. Copy `.env.example` to `.env` and set `DATABASE_URL` if you are not using the Compose defaults.
2. Start PostgreSQL with `docker compose up -d db`.
3. Install the backend with `python -m pip install -r backend/requirements.txt`.
4. Run `alembic -c backend/alembic.ini upgrade head`.
5. Start the API with `uvicorn backend.app.main:app --reload`.
6. In another terminal, run `cd frontend`, `npm install`, and `npm run dev`.

The API health check is available at `http://localhost:8000/api/health`; interactive API docs are at `http://localhost:8000/docs`.

The repository currently provides the application and module boundaries for ingestion, graph analysis, retrieval, and agent workflows. Feature routes that depend on those not-yet-implemented services return HTTP 501 rather than simulated results.

Run backend tests with `python -m pytest` from the repository root and the frontend production build with `npm run build` from `frontend/`.
