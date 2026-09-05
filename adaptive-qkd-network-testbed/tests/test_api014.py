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
    c = TestClient(create_qkd014_app(KeyStore(), source_kme_id='A', target_kme_id='B', master_sae_id='SAE_A'))
    assert c.get('/api/v1/keys/SAE_B/status').status_code == 401
    # Unauthorized caller header must also be rejected
    assert c.get('/api/v1/keys/SAE_B/status', headers={'X-SAE-ID': 'IMPOSTOR'}).status_code == 401


def test_qkd014_dec_keys_initiator_authorization_no_mutation():
    from qkd_lab.kms.models import KeyState
    store = KeyStore()
    # Add key with initiator SAE_OTHER, not SAE_A
    item = store.add_key(peer_id='SAE_B', bits=256, initiator_sae_id='SAE_OTHER')
    c = TestClient(create_qkd014_app(store, source_kme_id='KME_A', target_kme_id='KME_B', master_sae_id='SAE_A'))
    
    # Caller SAE_B requests dec_keys with master_SAE_ID=SAE_A, but the key's initiator is SAE_OTHER
    res = c.post(
        '/api/v1/keys/SAE_A/dec_keys',
        headers={'X-SAE-ID': 'SAE_B'},
        json={'key_IDs': [{'key_ID': item.key_id}]},
    )
    assert res.status_code == 401
    # Key in store MUST remain AVAILABLE and NOT mutated to CONSUMED
    assert store.get(item.key_id).state == KeyState.AVAILABLE