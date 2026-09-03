from fastapi.testclient import TestClient

from qkd_lab.kms.api014 import create_qkd014_app
from qkd_lab.kms.store import KeyStore


def test_qkd014_status_and_enc_key():
    store=KeyStore(); store.add_key(peer_id='SAE_B', bits=256)
    c=TestClient(create_qkd014_app(store, source_kme_id='KME_A', target_kme_id='KME_B', master_sae_id='SAE_A'))
    h={'X-SAE-ID':'SAE_A'}
    status=c.get('/api/v1/keys/SAE_B/status', headers=h)
    assert status.status_code == 200
    assert status.json()['source_KME_ID'] == 'KME_A'
    key=c.post('/api/v1/keys/SAE_B/enc_keys', headers=h, json={'number':1,'size':256})
    assert key.status_code == 200
    assert len(key.json()['keys']) == 1


def test_qkd014_requires_identity():
    c=TestClient(create_qkd014_app(KeyStore(), source_kme_id='A', target_kme_id='B', master_sae_id='SAE_A'))
    assert c.get('/api/v1/keys/SAE_B/status').status_code == 401