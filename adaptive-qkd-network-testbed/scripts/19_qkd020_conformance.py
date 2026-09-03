import base64
import json
from pathlib import Path

from fastapi.testclient import TestClient

from qkd_lab.kms.api020 import create_qkd020_app
from qkd_lab.kms.store import KeyStore


def main():
    store = KeyStore()
    client = TestClient(create_qkd020_app(store))
    version = client.get("/kmapi/versions")
    payload = {
        "keys": [{"key_id": "interop-key-1", "value": base64.b64encode(b"A" * 32).decode("ascii")}],
        "initiator_sae_id": "SAE_A",
        "target_sae_ids": ["SAE_B"],
    }
    transferred = client.post("/kmapi/v1/ext_keys", json=payload)
    acked = client.post("/kmapi/v1/ext_keys/ack", json={"key_ids": ["interop-key-1"], "ack_status": "relayed", "initiator_sae_id": "SAE_A", "target_sae_id": "SAE_B"})
    voided = client.post("/kmapi/v1/ext_keys/void", json={"key_ids": ["interop-key-1"], "initiator_sae_id": "SAE_A", "target_sae_ids": ["SAE_B"]})
    assert version.status_code == transferred.status_code == acked.status_code == voided.status_code == 200
    summary = {"versions": version.json(), "transfer": transferred.json(), "ack": acked.json(), "void": voided.json()}
    Path("results/kms").mkdir(parents=True, exist_ok=True)
    Path("results/kms/qkd020_conformance.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("QKD 020 local conformance checks PASSED")


if __name__ == "__main__":
    main()