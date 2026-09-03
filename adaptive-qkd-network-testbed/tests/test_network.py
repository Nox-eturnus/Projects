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