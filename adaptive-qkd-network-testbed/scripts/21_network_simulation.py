from pathlib import Path

import pandas as pd

from qkd_lab.config import load_yaml
from qkd_lab.network.qos import QKDNQoSRequest
from qkd_lab.network.simulator import generate_keys, replenish_from_qkd_physics, request_end_to_end_key
from qkd_lab.network.topology import QKDLinkState, build_graph


def graph_from_config():
    cfg = load_yaml("configs/network.yaml")
    links = [QKDLinkState(**item) for item in cfg["links"]]
    return build_graph(links)


def main():
    graph = graph_from_config()
    events = []

    # 1. Initial end-to-end request with high priority QoS
    qos_initial = QKDNQoSRequest(source="A", target="D", key_bits=256, service_priority=1, max_hops=4)
    first = request_end_to_end_key(graph, "A", "D", 256, qos=qos_initial)
    events.append({
        "event": "initial_request",
        "success": first.success,
        "path": "-".join(first.path),
        "trusted": "-".join(first.trusted_intermediate_nodes),
        "hops": first.hops,
        "eps_total": first.eps_total,
    })

    # 2. Simulate link outage (A-C fiber cut) and dynamic reroute
    graph["A"]["C"]["state"].active = False
    second = request_end_to_end_key(graph, "A", "D", 256, qos=qos_initial)
    events.append({
        "event": "AC_down_reroute",
        "success": second.success,
        "path": "-".join(second.path),
        "trusted": "-".join(second.trusted_intermediate_nodes),
        "hops": second.hops,
        "eps_total": second.eps_total,
    })

    # 3. Dynamic replenishment from physical finite-key QKD distillation
    replenished = replenish_from_qkd_physics(graph, pulses_per_link=20_000_000)
    # Also apply background rate replenishment for remaining duration
    generate_keys(graph, 1.0)

    pools = [
        {
            "u": u,
            "v": v,
            "key_bits": data["state"].key_bits,
            "active": data["state"].active,
            "mdi_capable": data["state"].mdi_capable,
            "replenished_bits": replenished.get((u, v), 0),
        }
        for u, v, data in graph.edges(data=True)
    ]

    Path("results/network").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(events).to_csv("results/network/network_events.csv", index=False)
    pd.DataFrame(pools).to_csv("results/network/key_pools.csv", index=False)
    print(pd.DataFrame(events).to_string(index=False))
    print("\nKey Pools after Physical QKD Replenishment:")
    print(pd.DataFrame(pools).to_string(index=False))

    assert first.success and second.success and first.path != second.path
    print("\nNetwork reroute and physical replenishment simulation PASSED")


if __name__ == "__main__":
    main()