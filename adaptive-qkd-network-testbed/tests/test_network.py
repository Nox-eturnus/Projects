from qkd_lab.network.simulator import request_end_to_end_key
from qkd_lab.network.topology import QKDLinkState, build_graph


def test_routing_respects_reserve_and_failure():
    g=build_graph([
        QKDLinkState('A','B',10,1000,1000),
        QKDLinkState('B','D',10,1000,1000),
        QKDLinkState('A','C',20,1000,500),
        QKDLinkState('C','D',20,1000,500),
    ])
    first=request_end_to_end_key(g,'A','D',256)
    assert first.success
    edge=(first.path[0],first.path[1]); g[edge[0]][edge[1]]['state'].active=False
    second=request_end_to_end_key(g,'A','D',256)
    assert second.success
    assert second.path != first.path


def test_disconnected_refuses_service():
    g=build_graph([QKDLinkState('A','B',10,0,1000)])
    assert not request_end_to_end_key(g,'A','B',256).success


def test_network_kms_reservoir_synchronization():
    from qkd_lab.kms.store import KeyStore

    kms_a = KeyStore()
    link_ab = QKDLinkState('A', 'B', 10, key_bits=1024, secure_rate_bps=1000, key_store=kms_a)
    link_bd = QKDLinkState('B', 'D', 10, key_bits=1024, secure_rate_bps=1000)
    g = build_graph([link_ab, link_bd])

    # Available bits in KMS and link_ab must be synchronized to 1024
    assert link_ab.key_bits == 1024
    assert kms_a.available_bits(peer_id='B') == 1024

    # Perform network routing consumption of 256 bits across A -> D
    res = request_end_to_end_key(g, 'A', 'D', 256)
    assert res.success
    # link_ab and KMS must both be down to 768
    assert link_ab.key_bits == 768
    assert kms_a.available_bits(peer_id='B') == 768

    # Now consume 1 256-bit key via KMS API
    keys = kms_a.consume(peer_id='B', number=1, bits=256, initiator_sae_id='A')
    assert len(keys) == 1
    # Both must now be down to 512
    assert link_ab.key_bits == 512
    assert kms_a.available_bits(peer_id='B') == 512


def test_transactional_reservation_rollback():
    # Link AB has 1000 bits, Link BD has only 100 bits (insufficient for 256)
    link_ab = QKDLinkState('A', 'B', 10, key_bits=1000, secure_rate_bps=1000)
    link_bd = QKDLinkState('B', 'D', 10, key_bits=100, secure_rate_bps=1000)
    g = build_graph([link_ab, link_bd])

    res = request_end_to_end_key(g, 'A', 'D', 256)
    assert not res.success
    # Invariant: Link AB must NOT have suffered bit leakage or partial state mutation
    assert link_ab.key_bits == 1000
    assert link_bd.key_bits == 100


def test_trusted_node_e2e_key_relay_delivery():
    import base64
    from qkd_lab.kms.store import KeyStore

    kms_a = KeyStore()
    kms_d = KeyStore()
    kms_nodes = {'A': kms_a, 'D': kms_d}

    link_ab = QKDLinkState('A', 'B', 10, key_bits=2000, secure_rate_bps=1000)
    link_bd = QKDLinkState('B', 'D', 10, key_bits=2000, secure_rate_bps=1000)
    g = build_graph([link_ab, link_bd])

    res = request_end_to_end_key(g, 'A', 'D', 256, kms_nodes=kms_nodes)
    assert res.success
    assert res.key_id is not None
    assert not hasattr(res, "key_material") or getattr(res, "key_material", None) is None

    # Node A and Node D consume the delivered key from their respective local stores
    key_a = kms_a.consume_by_ids([res.key_id], peer_id='D', initiator_sae_id='A')[0]
    key_d = kms_d.consume_by_ids([res.key_id], peer_id='A', initiator_sae_id='A')[0]

    # Cryptographic invariant: Delivered key material is identical across endpoints and confidential
    raw_a = base64.b64decode(key_a.value_b64)
    raw_d = base64.b64decode(key_d.value_b64)
    assert raw_a == raw_d
    assert key_a.source == "budget_synthetic"
    assert key_d.source == "budget_synthetic"
    assert key_a.security_scope == "theorem_composable"
    assert key_a.protocol == "trusted_relay_e2e"
    assert key_d.protocol == "trusted_relay_e2e"
    assert link_ab.key_bits == 2000 - 256
    assert link_bd.key_bits == 2000 - 256


def test_trusted_node_e2e_key_relay_material_mode():
    from qkd_lab.kms.store import KeyStore

    kms_a = KeyStore()
    kms_b = KeyStore()
    kms_d = KeyStore()
    kms_nodes = {'A': kms_a, 'D': kms_d}

    # Deposit actual key material into reservoirs
    kms_a.deposit_reservoir_key_material(peer_id='B', key_material=b"\x01" * 256, initiator_sae_id='A')
    kms_b.deposit_reservoir_key_material(peer_id='D', key_material=b"\x02" * 256, initiator_sae_id='B')

    link_ab = QKDLinkState('A', 'B', 10, key_bits=2048, secure_rate_bps=1000, key_store=kms_a)
    link_bd = QKDLinkState('B', 'D', 10, key_bits=2048, secure_rate_bps=1000, key_store=kms_b)
    g = build_graph([link_ab, link_bd])

    res = request_end_to_end_key(g, 'A', 'D', 256, kms_nodes=kms_nodes)
    assert res.success
    assert res.security_scope == "theorem_composable"
    assert res.is_composable is True

    key_a = kms_a.consume_by_ids([res.key_id], peer_id='D', initiator_sae_id='A')[0]
    assert key_a.source == "material"


def test_destination_kms_failure_rolls_back_source_and_links():
    from unittest.mock import MagicMock
    from qkd_lab.kms.store import KeyStore

    kms_a = KeyStore()
    failing_kms_d = MagicMock()
    failing_kms_d.add_key.side_effect = RuntimeError("Storage engine write failed")
    kms_nodes = {'A': kms_a, 'D': failing_kms_d}

    link_ab = QKDLinkState('A', 'B', 10, key_bits=2000, secure_rate_bps=1000)
    link_bd = QKDLinkState('B', 'D', 10, key_bits=2000, secure_rate_bps=1000)
    g = build_graph([link_ab, link_bd])

    res = request_end_to_end_key(g, 'A', 'D', 256, kms_nodes=kms_nodes)
    assert not res.success
    assert res.key_id is None
    assert "reservation failed and rolled back" in res.message

    # Atomic Invariant: Source KMS must have zero keys remaining
    assert len(kms_a.safe_metadata()) == 0

    # Links must have exact bits restored
    assert link_ab.key_bits == 2000
    assert link_bd.key_bits == 2000


def test_missing_endpoint_kms_fails_immediately():
    from qkd_lab.kms.store import KeyStore

    kms_a = KeyStore()
    # Node D is missing from kms_nodes mapping
    kms_nodes = {'A': kms_a}

    link_ab = QKDLinkState('A', 'B', 10, key_bits=2000, secure_rate_bps=1000)
    link_bd = QKDLinkState('B', 'D', 10, key_bits=2000, secure_rate_bps=1000)
    g = build_graph([link_ab, link_bd])

    res = request_end_to_end_key(g, 'A', 'D', 256, kms_nodes=kms_nodes)
    assert not res.success
    assert "endpoint KMS missing from kms_nodes" in res.message
    assert link_ab.key_bits == 2000
    assert link_bd.key_bits == 2000