from __future__ import annotations

import base64
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from qkd_lab.kms.models import KeyState, ManagedKey, utcnow
from qkd_lab.kms.store import KeyStore


class ExtKey(BaseModel):
    key_id: str
    value: str
    extension: dict[str, Any] | None = None


class ExtKeyContainer(BaseModel):
    keys: list[ExtKey] = Field(min_length=1, max_length=1024)
    initiator_sae_id: str
    target_sae_ids: list[str] = Field(min_length=1)
    ack_callback_url: str | None = None
    extension_mandatory: list[dict[str, Any]] = Field(default_factory=list)
    extension_optional: list[dict[str, Any]] = Field(default_factory=list)


class AckContainer(BaseModel):
    key_ids: list[str]
    ack_status: str
    initiator_sae_id: str
    target_sae_id: str
    message: str | None = None


class VoidContainer(BaseModel):
    key_ids: list[str] = Field(default_factory=list)
    initiator_sae_id: str
    target_sae_ids: list[str]
    ack_callback_url: str | None = None
    all_confirmation: bool = False


def create_qkd020_app(store: KeyStore) -> FastAPI:
    app = FastAPI(title="ETSI GS QKD 020 V1.1.1 research implementation")
    app.state.acks = []

    @app.get("/kmapi/versions")
    def versions():
        return {
            "versions": ["v1"],
            "capabilities": ["synchronous_mode"],
            "synchronous_mode": True,
        }

    @app.post("/kmapi/v1/ext_keys")
    def ext_keys(container: ExtKeyContainer):
        if container.extension_mandatory:
            raise HTTPException(status_code=400, detail="mandatory extensions are not implemented")
        if len(container.target_sae_ids) != 1:
            raise HTTPException(status_code=400, detail="research baseline supports exactly one target SAE")
        target = container.target_sae_ids[0]
        keys_to_import: list[ManagedKey] = []
        try:
            for item in container.keys:
                raw = base64.b64decode(item.value, validate=True)
                key = ManagedKey(
                    key_id=item.key_id,
                    peer_id=target,
                    bits=len(raw) * 8,
                    value_b64=item.value,
                    state=KeyState.AVAILABLE,
                    created_at=utcnow(),
                    protocol="qkd020_import",
                    eps_sec=1e-10,
                    eps_cor=1e-15,
                    initiator_sae_id=container.initiator_sae_id,
                    target_sae_id=target,
                )
                keys_to_import.append(key)
            imported_items = store.import_keys_batch(keys_to_import, peer_id=target)
            imported = [k.key_id for k in imported_items]
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "relayed", "key_ids": imported}

    @app.post("/kmapi/v1/ext_keys/ack")
    def ext_keys_ack(container: AckContainer | list[AckContainer]):
        items = [container] if isinstance(container, AckContainer) else container
        for item in items:
            if item.ack_status not in {"relayed", "voided", "failed", "key not present"}:
                raise HTTPException(status_code=400, detail="invalid ack_status")
            app.state.acks.append(item.model_dump())
        return {"message": "success"}

    @app.post("/kmapi/v1/ext_keys/void")
    def ext_keys_void(container: VoidContainer):
        if not container.key_ids and not container.all_confirmation:
            raise HTTPException(status_code=400, detail="supply key_ids or set all_confirmation=true")
        if container.all_confirmation:
            # Multi-tenant safety: Scope all_confirmation strictly to specified initiator/target SAE pair
            available_keys = store.available(allow_unbound=False)
            key_ids = [
                k.key_id for k in available_keys
                if (k.peer_id in container.target_sae_ids) and
                   (k.initiator_sae_id == container.initiator_sae_id)
            ]
        else:
            for kid in container.key_ids:
                try:
                    k = store.get(kid)
                except KeyError:
                    raise HTTPException(status_code=400, detail=f"key {kid} not found")
                if k.peer_id not in container.target_sae_ids:
                    raise HTTPException(status_code=403, detail=f"key {kid} does not target specified SAE")
                if k.initiator_sae_id is not None and k.initiator_sae_id != container.initiator_sae_id:
                    raise HTTPException(
                        status_code=403,
                        detail=f"key {kid} initiator {k.initiator_sae_id} does not match {container.initiator_sae_id}",
                    )
            key_ids = container.key_ids
        try:
            voided = store.void(key_ids)
        except (KeyError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "voided", "key_ids": voided}

    return app