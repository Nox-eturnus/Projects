import base64
import pytest
from fastapi.testclient import TestClient

from qkd_lab.kms.api020 import create_qkd020_app
from qkd_lab.kms.models import KeyState
from qkd_lab.kms.store import KeyStore


def test_qkd020_transfer_ack_void():
    store = KeyStore()
    c = TestClient(create_qkd020_app(store))
    assert c.get("/kmapi/versions").json() == {"versions": ["v1"], "synchronous_mode": True}
    
    payload = {
        "keys": [{"key_id": "k1", "value": base64.b64encode(b"A" * 32).decode()}],
        "initiator_sae_id": "A",
        "target_sae_ids": ["B"],
    }
    assert c.post("/kmapi/v1/ext_keys", json=payload).status_code == 200
    assert store.get("k1").state == KeyState.AVAILABLE
    
    # Array of AckContainers
    ack = [{"key_ids": ["k1"], "ack_status": "relayed", "initiator_sae_id": "A", "target_sae_id": "B"}]
    assert c.post("/kmapi/v1/ext_keys/ack", json=ack).status_code == 200
    
    void = {"key_ids": ["k1"], "initiator_sae_id": "A", "target_sae_ids": ["B"]}
    assert c.post("/kmapi/v1/ext_keys/void", json=void).status_code == 200
    assert store.get("k1").state == KeyState.VOID


def test_qkd020_scoped_all_confirmation_void():
    store = KeyStore()
    c = TestClient(create_qkd020_app(store))
    # Import keys for A->B and C->D
    payload_ab = {
        "keys": [{"key_id": "k_ab_1", "value": base64.b64encode(b"A" * 32).decode()}],
        "initiator_sae_id": "A",
        "target_sae_ids": ["B"],
    }
    payload_cd = {
        "keys": [{"key_id": "k_cd_1", "value": base64.b64encode(b"B" * 32).decode()}],
        "initiator_sae_id": "C",
        "target_sae_ids": ["D"],
    }
    c.post("/kmapi/v1/ext_keys", json=payload_ab)
    c.post("/kmapi/v1/ext_keys", json=payload_cd)
    
    # Void all keys for pair A->B
    void_req = {
        "initiator_sae_id": "A",
        "target_sae_ids": ["B"],
        "all_confirmation": True,
    }
    res = c.post("/kmapi/v1/ext_keys/void", json=void_req)
    assert res.status_code == 200
    assert res.json()["key_ids"] == ["k_ab_1"]
    assert store.get("k_ab_1").state == KeyState.VOID
    # k_cd_1 MUST NOT be voided (multi-tenant isolation)
    assert store.get("k_cd_1").state == KeyState.AVAILABLE