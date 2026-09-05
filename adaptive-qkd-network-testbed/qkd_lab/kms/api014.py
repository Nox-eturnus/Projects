from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from qkd_lab.kms.store import KeyStore


class KeyRequestV1(BaseModel):
    number: int = Field(default=1, ge=1, le=128)
    size: int = Field(default=256, ge=64, le=1024)
    additional_slave_SAE_IDs: list[str] = Field(default_factory=list)
    extension_mandatory: list[dict[str, Any]] = Field(default_factory=list)
    extension_optional: list[dict[str, Any]] = Field(default_factory=list)


class KeyIdItemV1(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    key_id: str = Field(alias="key_ID")


class KeyIdsV1(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    key_ids: list[KeyIdItemV1] = Field(alias="key_IDs")


def _key_container(keys) -> dict:
    return {
        "keys": [
            {
                "key_ID": key.key_id,
                "key": key.value_b64,
            }
            for key in keys
        ]
    }


def create_qkd014_app(
    store: KeyStore,
    *,
    source_kme_id: str,
    target_kme_id: str,
    master_sae_id: str,
) -> FastAPI:
    app = FastAPI(title="ETSI GS QKD 014 V1.1.1 research implementation")

    def require_caller(x_sae_id: str | None) -> str:
        # Development identity shim. Production conformance requires mTLS identity binding.
        if not x_sae_id:
            raise HTTPException(status_code=401, detail="missing X-SAE-ID development identity header")
        return x_sae_id

    @app.get("/api/v1/keys/{slave_SAE_ID}/status")
    def get_status(slave_SAE_ID: str, x_sae_id: str | None = Header(default=None, alias="X-SAE-ID")):
        caller = require_caller(x_sae_id)
        if caller != master_sae_id and caller != slave_SAE_ID:
            raise HTTPException(status_code=401, detail=f"caller {caller} is not authorized for status of {slave_SAE_ID}")
        stored_count = store.available_key_count(peer_id=slave_SAE_ID, key_size=256, initiator_sae_id=master_sae_id)
        return {
            "source_KME_ID": source_kme_id,
            "target_KME_ID": target_kme_id,
            "master_SAE_ID": master_sae_id,
            "slave_SAE_ID": slave_SAE_ID,
            "key_size": 256,
            "stored_key_count": stored_count,
            "max_key_count": 100000,
            "max_key_per_request": 128,
            "max_key_size": 1024,
            "min_key_size": 64,
            "max_SAE_ID_count": 0,
        }

    @app.post("/api/v1/keys/{slave_SAE_ID}/enc_keys")
    def get_key(
        slave_SAE_ID: str,
        request: KeyRequestV1,
        x_sae_id: str | None = Header(default=None, alias="X-SAE-ID"),
    ):
        caller = require_caller(x_sae_id)
        if caller != master_sae_id:
            raise HTTPException(status_code=401, detail="caller is not authorized master SAE")
        if request.additional_slave_SAE_IDs:
            raise HTTPException(status_code=400, detail="multicast is not implemented; max_SAE_ID_count=0")
        if request.extension_mandatory:
            raise HTTPException(status_code=400, detail="mandatory extensions are not implemented")
        try:
            keys = store.consume(
                peer_id=slave_SAE_ID,
                number=request.number,
                bits=request.size,
                initiator_sae_id=master_sae_id,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return _key_container(keys)

    @app.post("/api/v1/keys/{master_SAE_ID}/dec_keys")
    def get_key_by_ids(
        master_SAE_ID: str,
        request: KeyIdsV1,
        x_sae_id: str | None = Header(default=None, alias="X-SAE-ID"),
    ):
        caller = require_caller(x_sae_id)
        if master_SAE_ID != master_sae_id:
            raise HTTPException(status_code=400, detail=f"mismatched master_SAE_ID: expected {master_sae_id}, got {master_SAE_ID}")
        key_ids = [x.key_id for x in request.key_ids]
        try:
            # Atomic authorization & consumption: validates peer_id and initiator_sae_id BEFORE mutation
            keys = store.consume_by_ids(key_ids, peer_id=caller, initiator_sae_id=master_sae_id)
        except (KeyError, RuntimeError, PermissionError, ValueError) as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return _key_container(keys)

    return app