from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from qkd_lab.config import load_yaml
from qkd_lab.network.topology import QKDLinkState, build_graph


app = FastAPI(
    title="Adaptive QKD Network Research Dashboard",
    description="Development dashboard for the adaptive QKD network testbed.",
)


def current_graph():
    """
    Build the current QKD network graph directly from the repository
    network configuration.

    The dashboard therefore visualizes the same link state used by the
    network simulation rather than maintaining a separate copy.
    """
    cfg = load_yaml("configs/network.yaml")

    links = [
        QKDLinkState(**item)
        for item in cfg["links"]
    ]

    return build_graph(links)


@app.get("/api/state")
def state():
    """
    Return the current configured network state.

    This endpoint intentionally exposes only values already present in
    the underlying QKDLinkState objects. The dashboard must not invent
    additional security metrics.
    """
    graph = current_graph()

    links = []

    for u, v, data in graph.edges(data=True):
        link = data["state"]

        links.append(
            {
                "u": u,
                "v": v,
                "distance_km": link.distance_km,
                "key_bits": link.key_bits,
                "secure_rate_bps": link.secure_rate_bps,
                "qber": link.qber,
                "active": link.active,
                "mdi_capable": link.mdi_capable,
            }
        )

    return {
        "nodes": sorted(graph.nodes),
        "links": links,
    }


@app.get("/", response_class=HTMLResponse)
def index():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1"
    >

    <title>Adaptive QKD Network Research Dashboard</title>

    <style>
        :root {
            --background: #08111f;
            --panel: #101b2d;
            --panel-soft: #152338;
            --border: #26364d;

            --text: #eef4ff;
            --text-secondary: #98a9c0;
            --text-muted: #70829b;

            --accent: #5ab7ff;
            --accent-soft: rgba(90, 183, 255, 0.12);

            --success: #4cd99b;
            --success-soft: rgba(76, 217, 155, 0.12);

            --danger: #ff7272;
            --danger-soft: rgba(255, 114, 114, 0.12);

            --warning: #f6c85f;
        }

        * {
            box-sizing: border-box;
        }

        html {
            scroll-behavior: smooth;
        }

        body {
            margin: 0;

            background:
                radial-gradient(
                    circle at top left,
                    rgba(90, 183, 255, 0.05),
                    transparent 35%
                ),
                var(--background);

            color: var(--text);

            font-family:
                Inter,
                "Segoe UI",
                Roboto,
                Helvetica,
                Arial,
                sans-serif;

            min-height: 100vh;
        }

        .page {
            max-width: 1500px;
            margin: 0 auto;
            padding: 30px;
        }

        /* --------------------------------------------------------- */
        /* Header                                                    */
        /* --------------------------------------------------------- */

        .header {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 25px;

            margin-bottom: 26px;
        }

        .header-left h1 {
            margin: 0 0 8px 0;

            font-size: clamp(1.7rem, 3vw, 2.5rem);
            font-weight: 650;
            letter-spacing: -0.025em;
        }

        .subtitle {
            color: var(--text-secondary);
            line-height: 1.6;
            max-width: 850px;
            margin: 0;
        }

        .header-status {
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 8px;

            min-width: 180px;
        }

        .live-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;

            border: 1px solid rgba(76, 217, 155, 0.35);
            background: var(--success-soft);

            padding: 7px 11px;
            border-radius: 999px;

            color: var(--success);
            font-size: 0.8rem;
            font-weight: 700;
            letter-spacing: 0.06em;
        }

        .live-dot {
            width: 8px;
            height: 8px;

            background: var(--success);
            border-radius: 50%;

            box-shadow:
                0 0 0 4px rgba(76, 217, 155, 0.10);
        }

        .live-badge.error {
            color: var(--danger);
            background: var(--danger-soft);
            border-color: rgba(255, 114, 114, 0.35);
        }

        .live-badge.error .live-dot {
            background: var(--danger);

            box-shadow:
                0 0 0 4px rgba(255, 114, 114, 0.10);
        }

        .last-update {
            color: var(--text-muted);
            font-size: 0.78rem;
        }

        /* --------------------------------------------------------- */
        /* Cards                                                     */
        /* --------------------------------------------------------- */

        .stats-grid {
            display: grid;

            grid-template-columns:
                repeat(4, minmax(180px, 1fr));

            gap: 16px;

            margin-bottom: 20px;
        }

        .stat-card {
            background: var(--panel);

            border: 1px solid var(--border);
            border-radius: 14px;

            padding: 20px 22px;

            min-height: 120px;

            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }

        .stat-label {
            color: var(--text-secondary);

            font-size: 0.78rem;
            font-weight: 650;

            letter-spacing: 0.055em;
            text-transform: uppercase;
        }

        .stat-value {
            font-size: 2rem;
            font-weight: 650;
            letter-spacing: -0.03em;

            margin-top: 10px;
        }

        .stat-note {
            color: var(--text-muted);
            font-size: 0.78rem;

            margin-top: 5px;
        }

        /* --------------------------------------------------------- */
        /* Generic panels                                            */
        /* --------------------------------------------------------- */

        .panel {
            background: var(--panel);

            border: 1px solid var(--border);
            border-radius: 14px;

            overflow: hidden;
        }

        .panel-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 15px;

            padding: 17px 20px;

            border-bottom: 1px solid var(--border);
        }

        .panel-title {
            margin: 0;

            font-size: 0.95rem;
            font-weight: 650;
        }

        .panel-subtitle {
            color: var(--text-muted);
            font-size: 0.75rem;
        }

        .panel-body {
            padding: 20px;
        }

        /* --------------------------------------------------------- */
        /* Main two-column area                                      */
        /* --------------------------------------------------------- */

        .main-grid {
            display: grid;

            grid-template-columns:
                minmax(0, 2fr)
                minmax(280px, 0.8fr);

            gap: 20px;

            margin-bottom: 20px;
        }

        /* --------------------------------------------------------- */
        /* Topology                                                  */
        /* --------------------------------------------------------- */

        .topology-container {
            width: 100%;
            height: 430px;

            display: flex;
            align-items: center;
            justify-content: center;

            position: relative;
        }

        #topology {
            width: 100%;
            height: 100%;

            min-height: 390px;
        }

        .link-active {
            stroke: #4cd99b;
            stroke-width: 3;
        }

        .link-inactive {
            stroke: #53647a;
            stroke-width: 2.5;
            stroke-dasharray: 8 6;
        }

        .node-circle {
            fill: #162b42;
            stroke: #5ab7ff;
            stroke-width: 2.5;
        }

        .node-label {
            fill: #eef4ff;

            font-size: 18px;
            font-weight: 700;

            text-anchor: middle;
            dominant-baseline: central;

            pointer-events: none;
        }

        .link-label {
            fill: #91a5bc;

            font-size: 12px;
            font-weight: 500;

            text-anchor: middle;
        }

        /* --------------------------------------------------------- */
        /* Network status                                            */
        /* --------------------------------------------------------- */

        .status-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .status-row {
            display: flex;
            align-items: center;
            justify-content: space-between;

            gap: 15px;

            padding: 12px 0;

            border-bottom: 1px solid rgba(38, 54, 77, 0.65);
        }

        .status-row:last-child {
            border-bottom: none;
        }

        .status-key {
            color: var(--text-secondary);
            font-size: 0.86rem;
        }

        .status-value {
            color: var(--text);
            font-weight: 600;
            font-size: 0.9rem;
        }

        .legend {
            margin-top: 22px;
            padding-top: 18px;

            border-top: 1px solid var(--border);
        }

        .legend-title {
            color: var(--text-muted);

            text-transform: uppercase;
            letter-spacing: 0.055em;

            font-size: 0.72rem;
            font-weight: 650;

            margin-bottom: 12px;
        }

        .legend-item {
            display: flex;
            align-items: center;
            gap: 9px;

            color: var(--text-secondary);

            font-size: 0.8rem;

            margin: 8px 0;
        }

        .legend-line {
            width: 32px;
            height: 3px;
            border-radius: 3px;
        }

        .legend-line.active {
            background: var(--success);
        }

        .legend-line.inactive {
            height: 0;
            border-top: 2px dashed #53647a;
        }

        /* --------------------------------------------------------- */
        /* Link table                                                */
        /* --------------------------------------------------------- */

        .table-panel {
            margin-bottom: 20px;
        }

        .table-wrapper {
            width: 100%;
            overflow-x: auto;
        }

        table {
            width: 100%;

            border-collapse: collapse;

            min-width: 900px;
        }

        thead th {
            color: var(--text-muted);

            text-align: left;

            font-size: 0.72rem;
            font-weight: 650;

            text-transform: uppercase;
            letter-spacing: 0.055em;

            padding: 13px 16px;

            border-bottom: 1px solid var(--border);

            background: rgba(255,255,255,0.012);
        }

        tbody td {
            padding: 15px 16px;

            color: var(--text-secondary);
            font-size: 0.86rem;

            border-bottom: 1px solid rgba(38, 54, 77, 0.65);
        }

        tbody tr:last-child td {
            border-bottom: none;
        }

        tbody tr:hover {
            background: rgba(90, 183, 255, 0.035);
        }

        .link-name {
            color: var(--text);
            font-weight: 650;
        }

        /* --------------------------------------------------------- */
        /* Badges                                                    */
        /* --------------------------------------------------------- */

        .badge {
            display: inline-flex;
            align-items: center;

            border-radius: 999px;

            padding: 5px 9px;

            font-size: 0.7rem;
            font-weight: 700;
            letter-spacing: 0.045em;
        }

        .badge.active {
            color: var(--success);
            background: var(--success-soft);
            border: 1px solid rgba(76, 217, 155, 0.25);
        }

        .badge.inactive {
            color: var(--danger);
            background: var(--danger-soft);
            border: 1px solid rgba(255, 114, 114, 0.25);
        }

        .badge.mdi {
            color: var(--accent);
            background: var(--accent-soft);
            border: 1px solid rgba(90, 183, 255, 0.25);
        }

        .badge.direct {
            color: var(--text-muted);
            background: rgba(112, 130, 155, 0.09);
            border: 1px solid rgba(112, 130, 155, 0.20);
        }

        /* --------------------------------------------------------- */
        /* Raw JSON                                                  */
        /* --------------------------------------------------------- */

        details {
            width: 100%;
        }

        summary {
            cursor: pointer;

            list-style: none;

            color: var(--text-secondary);

            padding: 17px 20px;

            font-size: 0.9rem;
            font-weight: 600;

            user-select: none;
        }

        summary::-webkit-details-marker {
            display: none;
        }

        summary::before {
            content: "›";

            display: inline-block;

            margin-right: 9px;

            color: var(--accent);

            transform: rotate(0deg);

            transition: transform 0.15s ease;
        }

        details[open] summary::before {
            transform: rotate(90deg);
        }

        #raw-state {
            margin: 0;

            border-top: 1px solid var(--border);

            padding: 20px;

            color: #a9bfd8;
            background: #091421;

            overflow: auto;

            max-height: 450px;

            font-family:
                "Cascadia Code",
                Consolas,
                "Courier New",
                monospace;

            font-size: 0.78rem;
            line-height: 1.55;
        }

        /* --------------------------------------------------------- */
        /* Footer                                                    */
        /* --------------------------------------------------------- */

        .footer {
            margin-top: 22px;

            color: var(--text-muted);
            font-size: 0.76rem;

            text-align: center;
        }

        /* --------------------------------------------------------- */
        /* Error state                                               */
        /* --------------------------------------------------------- */

        .error-message {
            display: none;

            margin-bottom: 20px;

            border: 1px solid rgba(255, 114, 114, 0.35);

            background: var(--danger-soft);

            color: #ffaaaa;

            padding: 14px 17px;

            border-radius: 10px;
        }

        /* --------------------------------------------------------- */
        /* Responsive                                                */
        /* --------------------------------------------------------- */

        @media (max-width: 1100px) {

            .stats-grid {
                grid-template-columns:
                    repeat(2, minmax(180px, 1fr));
            }

            .main-grid {
                grid-template-columns: 1fr;
            }

            .topology-container {
                height: 390px;
            }
        }

        @media (max-width: 650px) {

            .page {
                padding: 18px;
            }

            .header {
                flex-direction: column;
            }

            .header-status {
                align-items: flex-start;
            }

            .stats-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>

<body>

<div class="page">

    <!-- ========================================================= -->
    <!-- Header                                                    -->
    <!-- ========================================================= -->

    <header class="header">

        <div class="header-left">

            <h1>
                Adaptive QKD Network Research Dashboard
            </h1>

            <p class="subtitle">
                Development dashboard for the adaptive quantum key
                distribution network testbed. Values shown here are read
                from the repository's configured network state and do not
                represent measurements from physical QKD hardware.
            </p>

        </div>

        <div class="header-status">

            <div
                id="live-badge"
                class="live-badge"
            >
                <span class="live-dot"></span>
                <span id="live-text">LIVE</span>
            </div>

            <div
                id="last-update"
                class="last-update"
            >
                Waiting for first update...
            </div>

        </div>

    </header>


    <div
        id="error-message"
        class="error-message"
    >
        Unable to read the network state from
        <code>/api/state</code>.
    </div>


    <!-- ========================================================= -->
    <!-- Summary cards                                             -->
    <!-- ========================================================= -->

    <section class="stats-grid">

        <div class="stat-card">

            <div class="stat-label">
                Network Nodes
            </div>

            <div
                id="stat-nodes"
                class="stat-value"
            >
                —
            </div>

            <div class="stat-note">
                Configured QKD nodes
            </div>

        </div>


        <div class="stat-card">

            <div class="stat-label">
                Active Links
            </div>

            <div
                id="stat-active-links"
                class="stat-value"
            >
                —
            </div>

            <div
                id="stat-active-note"
                class="stat-note"
            >
                —
            </div>

        </div>


        <div class="stat-card">

            <div class="stat-label">
                Available Key Pool
            </div>

            <div
                id="stat-key-pool"
                class="stat-value"
            >
                —
            </div>

            <div class="stat-note">
                Sum across configured links
            </div>

        </div>


        <div class="stat-card">

            <div class="stat-label">
                Aggregate Secure Rate
            </div>

            <div
                id="stat-rate"
                class="stat-value"
            >
                —
            </div>

            <div class="stat-note">
                Sum of configured link rates
            </div>

        </div>

    </section>


    <!-- ========================================================= -->
    <!-- Topology + status                                         -->
    <!-- ========================================================= -->

    <section class="main-grid">

        <div class="panel">

            <div class="panel-header">

                <div>

                    <h2 class="panel-title">
                        Network Topology
                    </h2>

                    <div class="panel-subtitle">
                        Current configured QKD links
                    </div>

                </div>

            </div>

            <div class="panel-body">

                <div class="topology-container">

                    <svg
                        id="topology"
                        viewBox="0 0 800 430"
                        preserveAspectRatio="xMidYMid meet"
                    >
                    </svg>

                </div>

            </div>

        </div>


        <div class="panel">

            <div class="panel-header">

                <div>

                    <h2 class="panel-title">
                        Network Status
                    </h2>

                    <div class="panel-subtitle">
                        Derived from current link state
                    </div>

                </div>

            </div>


            <div class="panel-body">

                <div class="status-list">

                    <div class="status-row">

                        <span class="status-key">
                            Total links
                        </span>

                        <span
                            id="status-total-links"
                            class="status-value"
                        >
                            —
                        </span>

                    </div>


                    <div class="status-row">

                        <span class="status-key">
                            Active links
                        </span>

                        <span
                            id="status-active-links"
                            class="status-value"
                        >
                            —
                        </span>

                    </div>


                    <div class="status-row">

                        <span class="status-key">
                            Inactive links
                        </span>

                        <span
                            id="status-inactive-links"
                            class="status-value"
                        >
                            —
                        </span>

                    </div>


                    <div class="status-row">

                        <span class="status-key">
                            MDI-capable links
                        </span>

                        <span
                            id="status-mdi-links"
                            class="status-value"
                        >
                            —
                        </span>

                    </div>


                    <div class="status-row">

                        <span class="status-key">
                            Mean QBER
                        </span>

                        <span
                            id="status-mean-qber"
                            class="status-value"
                        >
                            —
                        </span>

                    </div>

                </div>


                <div class="legend">

                    <div class="legend-title">
                        Topology Legend
                    </div>


                    <div class="legend-item">

                        <span class="legend-line active"></span>

                        Active configured link

                    </div>


                    <div class="legend-item">

                        <span class="legend-line inactive"></span>

                        Inactive configured link

                    </div>

                </div>

            </div>

        </div>

    </section>


    <!-- ========================================================= -->
    <!-- Link table                                                -->
    <!-- ========================================================= -->

    <section class="panel table-panel">

        <div class="panel-header">

            <div>

                <h2 class="panel-title">
                    Link State
                </h2>

                <div class="panel-subtitle">
                    Current per-link resource and channel values
                </div>

            </div>

        </div>


        <div class="table-wrapper">

            <table>

                <thead>

                    <tr>
                        <th>Link</th>
                        <th>Distance</th>
                        <th>Key Pool</th>
                        <th>Secure Rate</th>
                        <th>QBER</th>
                        <th>Capability</th>
                        <th>Status</th>
                    </tr>

                </thead>


                <tbody id="link-table-body">

                    <tr>

                        <td colspan="7">
                            Loading network state...
                        </td>

                    </tr>

                </tbody>

            </table>

        </div>

    </section>


    <!-- ========================================================= -->
    <!-- Raw state                                                 -->
    <!-- ========================================================= -->

    <section class="panel">

        <details>

            <summary>
                Raw API State
            </summary>

            <pre id="raw-state">Loading...</pre>

        </details>

    </section>


    <div class="footer">
        Software research dashboard · Auto-refresh every 2 seconds
    </div>

</div>


<script>

    const SVG_NAMESPACE =
        "http://www.w3.org/2000/svg";


    function formatBits(bits) {

        const value = Number(bits);

        if (!Number.isFinite(value)) {
            return "—";
        }

        if (Math.abs(value) >= 1_000_000_000) {

            return (
                value / 1_000_000_000
            ).toFixed(2) + " Gbit";
        }

        if (Math.abs(value) >= 1_000_000) {

            return (
                value / 1_000_000
            ).toFixed(2) + " Mbit";
        }

        if (Math.abs(value) >= 1_000) {

            return (
                value / 1_000
            ).toFixed(1) + " kbit";
        }

        return value.toFixed(0) + " bit";
    }


    function formatRate(rate) {

        const value = Number(rate);

        if (!Number.isFinite(value)) {
            return "—";
        }

        if (Math.abs(value) >= 1_000_000_000) {

            return (
                value / 1_000_000_000
            ).toFixed(2) + " Gbit/s";
        }

        if (Math.abs(value) >= 1_000_000) {

            return (
                value / 1_000_000
            ).toFixed(2) + " Mbit/s";
        }

        if (Math.abs(value) >= 1_000) {

            return (
                value / 1_000
            ).toFixed(1) + " kbit/s";
        }

        return value.toFixed(0) + " bit/s";
    }


    function formatQber(qber) {

        const value = Number(qber);

        if (!Number.isFinite(value)) {
            return "—";
        }

        return (value * 100).toFixed(2) + " %";
    }


    function formatDistance(distance) {

        const value = Number(distance);

        if (!Number.isFinite(value)) {
            return "—";
        }

        return value.toFixed(1) + " km";
    }


    function createSvgElement(name, attributes = {}) {

        const element =
            document.createElementNS(
                SVG_NAMESPACE,
                name
            );

        for (
            const [key, value]
            of Object.entries(attributes)
        ) {

            element.setAttribute(
                key,
                String(value)
            );
        }

        return element;
    }


    function drawTopology(data) {

        const svg =
            document.getElementById(
                "topology"
            );

        svg.replaceChildren();


        const width = 800;
        const height = 430;

        const centerX = width / 2;
        const centerY = height / 2;

        const radius =
            Math.min(
                width,
                height
            ) * 0.34;


        const nodes = data.nodes || [];
        const links = data.links || [];


        if (nodes.length === 0) {

            const message =
                createSvgElement(
                    "text",
                    {
                        x: centerX,
                        y: centerY,
                        fill: "#91a5bc",
                        "text-anchor": "middle",
                        "font-size": 16,
                    }
                );

            message.textContent =
                "No nodes configured";

            svg.appendChild(message);

            return;
        }


        const positions = {};


        nodes.forEach(
            (node, index) => {

                const angle =
                    (
                        2
                        * Math.PI
                        * index
                        / nodes.length
                    )
                    - Math.PI / 2;


                positions[node] = {

                    x:
                        centerX
                        + radius
                        * Math.cos(angle),

                    y:
                        centerY
                        + radius
                        * Math.sin(angle),

                };

            }
        );


        /*
         * Draw links first so that nodes appear above the edges.
         */
        links.forEach(
            (link) => {

                const start =
                    positions[link.u];

                const end =
                    positions[link.v];


                if (!start || !end) {
                    return;
                }


                const line =
                    createSvgElement(
                        "line",
                        {
                            x1: start.x,
                            y1: start.y,
                            x2: end.x,
                            y2: end.y,
                            class:
                                link.active
                                    ? "link-active"
                                    : "link-inactive",
                        }
                    );


                const title =
                    createSvgElement(
                        "title"
                    );

                title.textContent =
                    `${link.u} ↔ ${link.v}`
                    + ` | ${formatDistance(link.distance_km)}`
                    + ` | ${formatRate(link.secure_rate_bps)}`
                    + ` | QBER ${formatQber(link.qber)}`;


                line.appendChild(title);

                svg.appendChild(line);


                const midpointX =
                    (
                        start.x
                        + end.x
                    ) / 2;

                const midpointY =
                    (
                        start.y
                        + end.y
                    ) / 2;


                const labelBackground =
                    createSvgElement(
                        "rect",
                        {
                            x: midpointX - 31,
                            y: midpointY - 13,
                            width: 62,
                            height: 21,
                            rx: 6,
                            fill: "#101b2d",
                            stroke: "#26364d",
                            "stroke-width": 1,
                        }
                    );


                svg.appendChild(
                    labelBackground
                );


                const label =
                    createSvgElement(
                        "text",
                        {
                            x: midpointX,
                            y: midpointY + 2,
                            class: "link-label",
                        }
                    );


                label.textContent =
                    `${Number(link.distance_km).toFixed(0)} km`;


                svg.appendChild(label);

            }
        );


        /*
         * Draw nodes.
         */
        nodes.forEach(
            (node) => {

                const position =
                    positions[node];


                const circle =
                    createSvgElement(
                        "circle",
                        {
                            cx: position.x,
                            cy: position.y,
                            r: 31,
                            class: "node-circle",
                        }
                    );


                const title =
                    createSvgElement(
                        "title"
                    );

                title.textContent =
                    `QKD node ${node}`;

                circle.appendChild(title);

                svg.appendChild(circle);


                const label =
                    createSvgElement(
                        "text",
                        {
                            x: position.x,
                            y: position.y + 1,
                            class: "node-label",
                        }
                    );


                label.textContent = node;

                svg.appendChild(label);

            }
        );

    }


    function updateSummary(data) {

        const nodes =
            data.nodes || [];

        const links =
            data.links || [];


        const activeLinks =
            links.filter(
                link => Boolean(link.active)
            );


        const inactiveLinks =
            links.length
            - activeLinks.length;


        const mdiLinks =
            links.filter(
                link =>
                    Boolean(
                        link.mdi_capable
                    )
            ).length;


        const totalKeyBits =
            links.reduce(
                (sum, link) =>
                    sum
                    + Number(
                        link.key_bits || 0
                    ),
                0
            );


        const totalSecureRate =
            links.reduce(
                (sum, link) =>
                    sum
                    + Number(
                        link.secure_rate_bps || 0
                    ),
                0
            );


        let meanQber = 0;

        if (links.length > 0) {

            meanQber =
                links.reduce(
                    (sum, link) =>
                        sum
                        + Number(
                            link.qber || 0
                        ),
                    0
                )
                / links.length;
        }


        document.getElementById(
            "stat-nodes"
        ).textContent =
            nodes.length;


        document.getElementById(
            "stat-active-links"
        ).textContent =
            `${activeLinks.length} / ${links.length}`;


        document.getElementById(
            "stat-active-note"
        ).textContent =
            `${inactiveLinks} inactive link`
            + (
                inactiveLinks === 1
                    ? ""
                    : "s"
            );


        document.getElementById(
            "stat-key-pool"
        ).textContent =
            formatBits(
                totalKeyBits
            );


        document.getElementById(
            "stat-rate"
        ).textContent =
            formatRate(
                totalSecureRate
            );


        document.getElementById(
            "status-total-links"
        ).textContent =
            links.length;


        document.getElementById(
            "status-active-links"
        ).textContent =
            activeLinks.length;


        document.getElementById(
            "status-inactive-links"
        ).textContent =
            inactiveLinks;


        document.getElementById(
            "status-mdi-links"
        ).textContent =
            mdiLinks;


        document.getElementById(
            "status-mean-qber"
        ).textContent =
            formatQber(
                meanQber
            );

    }


    function makeBadge(
        text,
        cssClass
    ) {

        const span =
            document.createElement(
                "span"
            );

        span.className =
            `badge ${cssClass}`;

        span.textContent =
            text;

        return span;
    }


    function updateLinkTable(data) {

        const tbody =
            document.getElementById(
                "link-table-body"
            );


        tbody.replaceChildren();


        const links =
            [...(data.links || [])];


        links.sort(
            (a, b) => {

                const first =
                    `${a.u}-${a.v}`;

                const second =
                    `${b.u}-${b.v}`;

                return first.localeCompare(
                    second
                );

            }
        );


        if (links.length === 0) {

            const row =
                document.createElement(
                    "tr"
                );


            const cell =
                document.createElement(
                    "td"
                );


            cell.colSpan = 7;

            cell.textContent =
                "No links configured.";


            row.appendChild(cell);

            tbody.appendChild(row);

            return;
        }


        links.forEach(
            (link) => {

                const row =
                    document.createElement(
                        "tr"
                    );


                const linkCell =
                    document.createElement(
                        "td"
                    );

                linkCell.className =
                    "link-name";

                linkCell.textContent =
                    `${link.u} ↔ ${link.v}`;


                const distanceCell =
                    document.createElement(
                        "td"
                    );

                distanceCell.textContent =
                    formatDistance(
                        link.distance_km
                    );


                const keyCell =
                    document.createElement(
                        "td"
                    );

                keyCell.textContent =
                    formatBits(
                        link.key_bits
                    );


                const rateCell =
                    document.createElement(
                        "td"
                    );

                rateCell.textContent =
                    formatRate(
                        link.secure_rate_bps
                    );


                const qberCell =
                    document.createElement(
                        "td"
                    );

                qberCell.textContent =
                    formatQber(
                        link.qber
                    );


                const capabilityCell =
                    document.createElement(
                        "td"
                    );


                capabilityCell.appendChild(

                    link.mdi_capable

                        ? makeBadge(
                            "MDI",
                            "mdi"
                        )

                        : makeBadge(
                            "DIRECT",
                            "direct"
                        )

                );


                const statusCell =
                    document.createElement(
                        "td"
                    );


                statusCell.appendChild(

                    link.active

                        ? makeBadge(
                            "ACTIVE",
                            "active"
                        )

                        : makeBadge(
                            "INACTIVE",
                            "inactive"
                        )

                );


                row.append(
                    linkCell,
                    distanceCell,
                    keyCell,
                    rateCell,
                    qberCell,
                    capabilityCell,
                    statusCell
                );


                tbody.appendChild(row);

            }
        );

    }


    function setConnectionStatus(
        connected
    ) {

        const badge =
            document.getElementById(
                "live-badge"
            );


        const text =
            document.getElementById(
                "live-text"
            );


        if (connected) {

            badge.classList.remove(
                "error"
            );

            text.textContent =
                "LIVE";

        } else {

            badge.classList.add(
                "error"
            );

            text.textContent =
                "API UNAVAILABLE";

        }

    }


    async function refresh() {

        try {

            const response =
                await fetch(
                    "/api/state",
                    {
                        cache: "no-store",
                    }
                );


            if (!response.ok) {

                throw new Error(
                    `HTTP ${response.status}`
                );

            }


            const data =
                await response.json();


            updateSummary(data);

            updateLinkTable(data);

            drawTopology(data);


            document.getElementById(
                "raw-state"
            ).textContent =
                JSON.stringify(
                    data,
                    null,
                    2
                );


            const now =
                new Date();


            document.getElementById(
                "last-update"
            ).textContent =
                "Last update: "
                + now.toLocaleTimeString();


            document.getElementById(
                "error-message"
            ).style.display =
                "none";


            setConnectionStatus(
                true
            );

        } catch (error) {

            console.error(
                "Dashboard refresh failed:",
                error
            );


            document.getElementById(
                "error-message"
            ).style.display =
                "block";


            document.getElementById(
                "last-update"
            ).textContent =
                "Last update failed";


            setConnectionStatus(
                false
            );

        }

    }


    /*
     * Load immediately, then refresh every two seconds.
     */
    refresh();

    setInterval(
        refresh,
        2000
    );

</script>

</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "dashboard.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )