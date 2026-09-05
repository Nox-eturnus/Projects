import base64
import pytest
from fastapi.testclient import TestClient

from qkd_lab.kms.api020 import create_qkd020_app
from qkd_lab.kms.models import KeyState
from qkd_lab.kms.store import KeyStore


def test_qkd020_transfer_ack_void():
    store = KeyStore()
    c = TestClient(create_qkd020_app(store))
    v = c.get("/kmapi/versions").json()
    assert v["versions"] == ["v1"]
    assert "synchronous_mode" in v["capabilities"]
    assert v["synchronous_mode"] is True
    
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


def test_qkd020_explicit_key_void_tenant_isolation():
    store = KeyStore()
    c = TestClient(create_qkd020_app(store))
    payload_ab = {
        "keys": [{"key_id": "k_tenant_a", "value": base64.b64encode(b"A" * 32).decode()}],
        "initiator_sae_id": "Tenant_A",
        "target_sae_ids": ["B"],
    }
    c.post("/kmapi/v1/ext_keys", json=payload_ab)

    # Impostor tenant attempts to void k_tenant_a explicitly
    void_impostor = {
        "key_ids": ["k_tenant_a"],
        "initiator_sae_id": "Tenant_B",
        "target_sae_ids": ["B"],
    }
    res = c.post("/kmapi/v1/ext_keys/void", json=void_impostor)
    assert res.status_code == 403
    assert store.get("k_tenant_a").state == KeyState.AVAILABLE

    # Legitimate tenant voids k_tenant_a
    void_legit = {
        "key_ids": ["k_tenant_a"],
        "initiator_sae_id": "Tenant_A",
        "target_sae_ids": ["B"],
    }
    res2 = c.post("/kmapi/v1/ext_keys/void", json=void_legit)
    assert res2.status_code == 200
    assert store.get("k_tenant_a").state == KeyState.VOID


def test_qkd020_explicit_void_unbound_key_rejected():
    store = KeyStore()
    c = TestClient(create_qkd020_app(store))
    # Unbound key (initiator_sae_id is None)
    store.add_key(peer_id="B", bits=256, key_id="k_unbound", initiator_sae_id=None)
    assert store.get("k_unbound").initiator_sae_id is None

    # Any tenant attempting to void this unbound key must be rejected with 403
    void_req = {
        "key_ids": ["k_unbound"],
        "initiator_sae_id": "Tenant_A",
        "target_sae_ids": ["B"],
    }
    res = c.post("/kmapi/v1/ext_keys/void", json=void_req)
    assert res.status_code == 403
    assert "does not match" in res.json()["detail"]
    assert store.get("k_unbound").state == KeyState.AVAILABLE