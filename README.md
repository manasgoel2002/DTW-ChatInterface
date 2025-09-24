## DTW Chat Interface API

Modular FastAPI application with onboarding and check-in endpoints.

### Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Run

```bash
uvicorn main:app --reload
```

Open docs at `http://127.0.0.1:8000/docs`.

### Endpoints

- POST `/api/onboarding/`
  - Body: `{ "name": "Alice", "email": "alice@example.com" }`
  - Response: `{ "user_id": "...", "message": "Welcome Alice!" }`

- POST `/api/checkin/`
  - Body: `{ "user_id": "uuid", "note": "optional", "timestamp": "2024-01-01T00:00:00Z" }`
  - Response: `{ "status": "ok", "message": "Check-in recorded" }`

- POST `/api/onboarding/chat`
  - Body:
    ```json
    {
      "user_id": "uuid",
      "session_id": "session-1",
      "message": "Tell me about your routine...",
      "model": "gpt-4o-mini"
    }
    ```
  - Response: `{ "reply": "...", "history": [{"role":"user|assistant","content":"..."}] }`

### Environment

Create a `.env` file with your OpenAI key:

```bash
OPENAI_API_KEY=sk-...
```







