import threading

from qkd_lab.kms.models import KeyState
from qkd_lab.kms.store import KeyStore


def test_consumed_key_not_reissued():
    store = KeyStore()
    item = store.add_key(peer_id='B', bits=256)
    got = store.consume(peer_id='B', number=1, bits=256)[0]
    assert got.key_id == item.key_id
    assert got.value_b64 != ""
    assert store.get(item.key_id).state == KeyState.CONSUMED
    assert store.get(item.key_id).value_b64 == ""
    assert store.available(peer_id='B', bits=256) == []


def test_concurrent_single_key_has_one_winner():
    store = KeyStore(); store.add_key(peer_id='B', bits=256)
    outcomes = []
    def worker():
        try:
            store.consume(peer_id='B', number=1, bits=256)
            outcomes.append('ok')
        except RuntimeError:
            outcomes.append('empty')
    threads=[threading.Thread(target=worker) for _ in range(2)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert outcomes.count('ok') == 1
    assert outcomes.count('empty') == 1