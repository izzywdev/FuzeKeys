# Image for the tokenizer HTTP service AND the one-shot vault-bootstrap (same code, two commands).
FROM python:3.11-slim

WORKDIR /app
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" redis

COPY pii_vault.py /app/pii_vault.py
COPY service/ /app/service/

EXPOSE 8099

# Default = tokenizer service. The vault-bootstrap service overrides this with:
#   command: ["python", "service/vault_bootstrap.py"]
CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8099"]
