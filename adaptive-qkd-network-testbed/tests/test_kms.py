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


def test_key_reservoir_deposit_slice_and_consume():
    from qkd_lab.kms.reservoir import KeyReservoir

    res = KeyReservoir(peer_id='peer_B')
    res.deposit_bits(1024, initiator_sae_id='SAE_A')
    assert res.available_bits() == 1024
    assert res.available_bits(initiator_sae_id='SAE_A') == 1024
    assert res.available_bits(initiator_sae_id='SAE_C') == 0

    # Slice a 256-bit key
    sliced = res.slice_key(bits=256, initiator_sae_id='SAE_A')
    assert sliced.bits == 256
    assert sliced.peer_id == 'peer_B'
    assert sliced.initiator_sae_id == 'SAE_A'
    assert res.available_bits() == 768

    # Consume 512 raw bits directly
    consumed = res.consume_bits(512, initiator_sae_id='SAE_A')
    assert consumed == 512
    assert res.available_bits() == 256


def test_keystore_reservoir_integration():
    store = KeyStore()
    # Deposit 512 bits directly into reservoir
    store.deposit_reservoir_bits(peer_id='SAE_B', bits=512, initiator_sae_id='SAE_A')
    assert store.available_bits(peer_id='SAE_B') == 512
    assert store.available_key_count(peer_id='SAE_B', key_size=256, initiator_sae_id='SAE_A') == 2
    assert store.available_key_count(peer_id='SAE_B', key_size=256, initiator_sae_id='SAE_OTHER') == 0

    # Consuming 1 key slices on-demand from reservoir
    keys = store.consume(peer_id='SAE_B', number=1, bits=256, initiator_sae_id='SAE_A')
    assert len(keys) == 1
    assert keys[0].bits == 256
    assert store.available_bits(peer_id='SAE_B') == 256

    # Consume remaining 256 bits via consume_bits
    store.consume_bits(peer_id='SAE_B', bits=256, initiator_sae_id='SAE_A')
    assert store.available_bits(peer_id='SAE_B') == 0


def test_key_reservoir_material_mode_exact_slicing():
    import base64
    from qkd_lab.kms.reservoir import KeyReservoir

    res = KeyReservoir(peer_id='peer_B')
    raw_material = bytes(range(64))  # 64 bytes = 512 bits
    res.deposit_key_material(raw_material, initiator_sae_id='SAE_A')
    assert res.available_bits(initiator_sae_id='SAE_A') == 512

    # Slice first 256 bits (32 bytes)
    key1 = res.slice_key(bits=256, initiator_sae_id='SAE_A')
    assert key1.source == "material"
    assert base64.b64decode(key1.value_b64) == raw_material[:32]
    assert res.available_bits(initiator_sae_id='SAE_A') == 256

    # Slice second 256 bits (32 bytes)
    key2 = res.slice_key(bits=256, initiator_sae_id='SAE_A')
    assert key2.source == "material"
    assert base64.b64decode(key2.value_b64) == raw_material[32:64]
    assert res.available_bits(initiator_sae_id='SAE_A') == 0


def test_key_reservoir_budget_mode_synthetic_tag():
    import base64
    from qkd_lab.kms.reservoir import KeyReservoir

    res = KeyReservoir(peer_id='peer_B')
    res.deposit_bits(512, initiator_sae_id='SAE_A')  # budget mode
    key = res.slice_key(bits=256, initiator_sae_id='SAE_A')
    assert key.source == "budget_synthetic"
    assert len(base64.b64decode(key.value_b64)) == 32
    assert res.available_bits(initiator_sae_id='SAE_A') == 256


def test_strict_multi_tenant_scoping_unbound_keys():
    store = KeyStore()
    # Add an unbound discrete key and an unbound reservoir pool
    store.add_key(peer_id='B', bits=256)
    store.deposit_reservoir_bits(peer_id='B', bits=512)

    # In strict mode (default allow_unbound=False), tenant-scoped queries see 0 keys
    assert store.available_key_count(peer_id='B', initiator_sae_id='Tenant_X') == 0
    assert store.available_bits(peer_id='B', initiator_sae_id='Tenant_X') == 0
    assert len(store.available(peer_id='B', bits=256, initiator_sae_id='Tenant_X')) == 0

    # With allow_unbound=True, unbound keys and reservoir pools can be accessed
    assert store.available_key_count(peer_id='B', initiator_sae_id='Tenant_X', allow_unbound=True) == 3
    assert store.available_bits(peer_id='B', initiator_sae_id='Tenant_X', allow_unbound=True) == 768
    assert len(store.available(peer_id='B', bits=256, initiator_sae_id='Tenant_X', allow_unbound=True)) == 1