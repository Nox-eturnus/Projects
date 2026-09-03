import json
from pathlib import Path

from qkd_lab.kms.store import KeyStore


def main():
    store = KeyStore()
    created = [store.add_key(peer_id="SAE_B", bits=256, protocol="decoy_bb84") for _ in range(4)]
    consumed = store.consume(peer_id="SAE_B", number=2, bits=256)
    assert len({x.key_id for x in created}) == 4
    assert len(consumed) == 2
    safe = {"metrics": store.metrics(), "keys": store.safe_metadata()}
    Path("results/kms").mkdir(parents=True, exist_ok=True)
    Path("results/kms/kms_demo.json").write_text(json.dumps(safe, indent=2), encoding="utf-8")
    assert all("value_b64" not in x for x in safe["keys"])
    print(json.dumps(safe["metrics"], indent=2))
    print("KMS lifecycle demo PASSED")


if __name__ == "__main__":
    main()