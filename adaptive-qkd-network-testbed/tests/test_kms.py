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


def test_import_key_preserves_source_provenance():
    store_a = KeyStore()
    store_b = KeyStore()

    # Add a key with source='material' and one with source='budget_synthetic'
    k_mat = store_a.add_key(peer_id='B', bits=256, source='material')
    k_bud = store_a.add_key(peer_id='B', bits=256, source='budget_synthetic')
    assert k_mat.source == "material"
    assert k_bud.source == "budget_synthetic"

    # Single import
    imp_mat = store_b.import_key(k_mat, peer_id='A')
    assert imp_mat.source == "material"

    # Batch import
    store_c = KeyStore()
    imp_batch = store_c.import_keys_batch([k_mat, k_bud], peer_id='A')
    assert imp_batch[0].source == "material"
    assert imp_batch[1].source == "budget_synthetic"


def test_key_reservoir_reservation_rollback_material():
    import base64
    from qkd_lab.kms.reservoir import KeyReservoir

    res = KeyReservoir(peer_id='peer_B')
    raw_material = bytes(range(64))  # 512 bits
    res.deposit_key_material(raw_material, initiator_sae_id='SAE_A')
    assert res.available_bits(initiator_sae_id='SAE_A') == 512

    # Reserve 256 bits
    reservation = res.reserve_bits(256, initiator_sae_id='SAE_A')
    assert res.available_bits(initiator_sae_id='SAE_A') == 256

    # Roll back reservation
    reservation.rollback()
    assert res.available_bits(initiator_sae_id='SAE_A') == 512

    # Verify that original material is completely intact
    key1 = res.slice_key(bits=256, initiator_sae_id='SAE_A')
    assert key1.source == "material"
    assert base64.b64decode(key1.value_b64) == raw_material[:32]

    key2 = res.slice_key(bits=256, initiator_sae_id='SAE_A')
    assert key2.source == "material"
    assert base64.b64decode(key2.value_b64) == raw_material[32:64]


def test_multi_block_composable_security_parameters():
    from qkd_lab.kms.reservoir import KeyReservoir

    res = KeyReservoir(peer_id='peer_B')
    # Two distinct 128-bit blocks
    res.deposit_bits(128, protocol='decoy_bb84', eps_sec=1.5e-10, eps_cor=1e-15)
    res.deposit_bits(128, protocol='mdi_qkd', eps_sec=2.5e-10, eps_cor=2e-15)

    key = res.slice_key(bits=256)
    assert key.bits == 256
    # Multi-block union bound composable security parameters
    assert abs(key.eps_sec - 4.0e-10) < 1e-15
    assert abs(key.eps_cor - 3.0e-15) < 1e-16
    assert key.protocol == "composite:decoy_bb84+mdi_qkd"


def test_reservoir_reservation_public_properties_and_commit_wiping():
    from qkd_lab.kms.reservoir import KeyReservoir

    res = KeyReservoir(peer_id='peer_B')
    raw_material = bytes(range(64))  # 512 bits
    res.deposit_key_material(raw_material, protocol='decoy_bb84', eps_sec=1e-10, eps_cor=1e-15, security_scope='theorem_composable')

    reservation = res.reserve_bits(256)
    assert reservation.eps_sec == 1e-10
    assert reservation.eps_cor == 1e-15
    assert reservation.protocols == ['decoy_bb84']
    assert reservation.security_scope == 'theorem_composable'
    assert reservation.is_composable is True
    assert reservation.source == 'material'
    assert reservation.segments[0].material_slice is not None

    # Cryptographic hygiene: commit wipes material_slice
    reservation.commit()
    assert reservation.committed is True
    assert reservation.segments[0].material_slice is None


def test_reservoir_reservation_engineering_model_scope():
    from qkd_lab.kms.reservoir import KeyReservoir

    res = KeyReservoir(peer_id='peer_B')
    res.deposit_bits(128, protocol='decoy_bb84', security_scope='theorem_composable')
    res.deposit_bits(128, protocol='mdi_qkd', security_scope='engineering_model')

    reservation = res.reserve_bits(256)
    assert reservation.security_scope == 'engineering_model'
    assert reservation.is_composable is False
    assert reservation.source == 'budget_synthetic'
    reservation.rollback()


def test_canonical_service_utility_consistency():
    from qkd_lab.adaptive.utility import compute_service_utility

    u1 = compute_service_utility(500_000, 0, 10.0)
    assert u1 == (50000.0 - 0.05 * 10.0)

    u2 = compute_service_utility(200_000, 300_000, 10.0, abort=True)
    expected = (20000.0 - 2.0 * 30000.0 - 0.5 - 1.0e6)
    assert abs(u2 - expected) < 1e-6