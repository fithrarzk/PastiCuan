# PastiCuan

How to run
`streamlit run app.py`

## Local AI setup

PastiCuan can generate the AI Research Report with a local Ollama model, so the
core app does not depend on paid API calls.

1. Install Ollama from https://ollama.com/download
2. Pull the default model:

```bash
ollama pull qwen2.5:7b
```

3. Copy `.env.example` to `.env`, then keep:

```bash
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
```

4. Start the app:

```bash
streamlit run app.py
```

If Ollama is not running or the model is missing, the app will still generate a
deterministic local report from the technical/fundamental engine.
