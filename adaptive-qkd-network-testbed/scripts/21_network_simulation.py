from pathlib import Path

import pandas as pd

from qkd_lab.config import load_yaml
from qkd_lab.network.simulator import generate_keys, request_end_to_end_key
from qkd_lab.network.topology import QKDLinkState, build_graph


def graph_from_config():
    cfg = load_yaml("configs/network.yaml")
    links = [QKDLinkState(**item) for item in cfg["links"]]
    return build_graph(links)


def main():
    graph = graph_from_config()
    events = []
    first = request_end_to_end_key(graph, "A", "D", 256)
    events.append({"event": "initial_request", "success": first.success, "path": "-".join(first.path), "trusted": "-".join(first.trusted_intermediate_nodes)})
    graph["A"]["C"]["state"].active = False
    second = request_end_to_end_key(graph, "A", "D", 256)
    events.append({"event": "AC_down_reroute", "success": second.success, "path": "-".join(second.path), "trusted": "-".join(second.trusted_intermediate_nodes)})
    generate_keys(graph, 1.0)
    pools = [{"u": u, "v": v, "key_bits": data["state"].key_bits, "active": data["state"].active} for u, v, data in graph.edges(data=True)]
    Path("results/network").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(events).to_csv("results/network/network_events.csv", index=False)
    pd.DataFrame(pools).to_csv("results/network/key_pools.csv", index=False)
    print(pd.DataFrame(events).to_string(index=False))
    assert first.success and second.success and first.path != second.path
    print("Network reroute simulation PASSED")


if __name__ == "__main__":
    main()