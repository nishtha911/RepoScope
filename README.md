# RepoScope
### A graph-powered developer tool that ingests a GitHub repository, builds a typed code graph, and uses it for PR impact analysis, evidence-cited Q&amp;A, and ranked recommendations on what to work on next.

<div align="center">
  <img width="600" alt="image" src="https://github.com/user-attachments/assets/43806b3f-7a71-4557-8916-7ee9b7eb6bd9" />
</div>

backend:
python -m uvicorn reposcope.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000

frontend:
cd "C:\Users\deole\Desktop\python\RepoScope-clean\frontend"
npm install
npm run dev


