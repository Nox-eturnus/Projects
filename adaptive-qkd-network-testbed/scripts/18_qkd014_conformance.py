import json
from pathlib import Path

from fastapi.testclient import TestClient

from qkd_lab.kms.api014 import create_qkd014_app
from qkd_lab.kms.store import KeyStore


def main():
    store = KeyStore()
    for _ in range(5):
        store.add_key(peer_id="SAE_B", bits=256)
    client = TestClient(create_qkd014_app(store, source_kme_id="KME_A", target_kme_id="KME_B", master_sae_id="SAE_A"))
    headers = {"X-SAE-ID": "SAE_A"}
    status = client.get("/api/v1/keys/SAE_B/status", headers=headers)
    enc = client.post("/api/v1/keys/SAE_B/enc_keys", headers=headers, json={"number": 1, "size": 256})
    assert status.status_code == 200
    assert enc.status_code == 200
    key_id = enc.json()["keys"][0]["key_ID"]
    replay = client.post("/api/v1/keys/SAE_B/enc_keys", headers=headers, json={"number": 99, "size": 256})
    assert replay.status_code == 503
    summary = {"status_code": status.status_code, "enc_code": enc.status_code, "key_id_present": bool(key_id), "insufficient_pool_code": replay.status_code}
    Path("results/kms").mkdir(parents=True, exist_ok=True)
    Path("results/kms/qkd014_conformance.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("QKD 014 local conformance checks PASSED")


if __name__ == "__main__":
    main()