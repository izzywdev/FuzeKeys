"""FastAPI tokenizer service — the containerized home of the PII tokenization logic.

Wraps pii_vault so the LiteLLM guardrail and the Claude Code host hook shims can tokenize /
detokenize over HTTP instead of importing the library (and its Redis/Vault/Presidio deps) directly.
"""
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

import pii_vault as pv

app = FastAPI(title="fuzekeys-tokenizer")


class TextIn(BaseModel):
    text: str


class ObjIn(BaseModel):
    obj: Any


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/tokenize")
def tokenize(body: TextIn):
    return {"text": pv.tokenize(body.text)}


@app.post("/detokenize")
def detokenize(body: TextIn):
    return {"text": pv.detokenize(body.text)}


@app.post("/tokenize_obj")
def tokenize_obj(body: ObjIn):
    return {"obj": pv.tokenize_obj(body.obj)}


@app.post("/detokenize_obj")
def detokenize_obj(body: ObjIn):
    return {"obj": pv.detokenize_obj(body.obj)}
