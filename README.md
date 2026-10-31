# Invoice A2A Agent v2

FastAPI + Groq + Neon PostgreSQL, designed for deployment to Vercel.

## Setup

1. `python -m pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and supply your own secrets. Never commit `.env`.
3. `uvicorn api.index:app --reload`
4. Check `http://127.0.0.1:8000/.well-known/agent-card.json`.
5. Run `python smoke_test.py` while the server is running.

## Vercel

Set `DATABASE_URL`, `GROQ_API_KEY`, `GROQ_MODEL`, and `BASE_URL=https://YOUR-PROJECT.vercel.app/a2a` in project environment variables. Deploy GitHub repository, then submit exactly `https://YOUR-PROJECT.vercel.app/a2a`.

## Important limitations

This is a candidate implementation, not a verified passing submission. The smoke test uses synthetic inputs and may require adjusting to actual invoice package schema. The grader requires exact three references and precise action/facts. Groq free-tier rate and token limits may prevent large batches from completing within 45 seconds. No actual banking or payment integration is included: receipt execution is a durable A2A ledger record after acceptance.
