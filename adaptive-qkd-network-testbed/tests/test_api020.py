import base64

from fastapi.testclient import TestClient

from qkd_lab.kms.api020 import create_qkd020_app
from qkd_lab.kms.models import KeyState
from qkd_lab.kms.store import KeyStore


def test_qkd020_transfer_ack_void():
    store=KeyStore(); c=TestClient(create_qkd020_app(store))
    assert c.get('/kmapi/versions').json() == {'versions':['v1']}
    payload={'keys':[{'key_id':'k1','value':base64.b64encode(b'A'*32).decode()}], 'initiator_sae_id':'A','target_sae_ids':['B']}
    assert c.post('/kmapi/v1/ext_keys',json=payload).status_code == 200
    assert store.get('k1').state == KeyState.AVAILABLE
    ack={'key_ids':['k1'],'ack_status':'relayed','initiator_sae_id':'A','target_sae_id':'B'}
    assert c.post('/kmapi/v1/ext_keys/ack',json=ack).status_code == 200
    void={'key_ids':['k1'],'initiator_sae_id':'A','target_sae_ids':['B']}
    assert c.post('/kmapi/v1/ext_keys/void',json=void).status_code == 200
    assert store.get('k1').state == KeyState.VOID