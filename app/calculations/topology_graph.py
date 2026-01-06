
import networkx as nx

def build_diagram(analysis_result: dict) -> dict:
    """
    Builds a React Flow compatible JSON structure of the electrical network.
    """
    G = nx.DiGraph()
    bus_analysis = analysis_result.get('bus_analysis', [])
    if not bus_analysis:
        return {"nodes": [], "edges": []}

    bus_data = {bus['IDBus']: bus for bus in bus_analysis}

    for bus_id in bus_data:
        G.add_node(bus_id, type='BUS')

    for conn in analysis_result.get('topology', []):
        from_bus = conn.get('From')
        to_bus = conn.get('ToSec')
        if G.has_node(from_bus) and G.has_node(to_bus):
            # Use a unique key for each edge based on all its properties to allow parallel edges
            edge_key = f"{from_bus}-{to_bus}-{conn.get('ID')}"
            G.add_edge(from_bus, to_bus, key=edge_key, data=conn)

    start_nodes_info = []
    for incomer in analysis_result.get('incomer_analysis', []):
        connected_bus = incomer.get('ConnectedBus')
        if G.has_node(connected_bus):
            start_nodes_info.append({'bus': connected_bus, 'incomer': incomer})

    if not start_nodes_info:
        return {"nodes": [], "edges": []}

    nodes_for_flow = []
    edges_for_flow = []
    
    X_SPACING = 300
    Y_SPACING = 150
    
    positions = {}
    level_y_tracker = {}
    visited_for_layout = set()

    def get_voltage_str(bus_id):
        bus = bus_data.get(bus_id, {})
        voltage = bus.get('NomlkV', bus.get('BasekV'))
        if voltage is not None:
            try:
                v = float(voltage)
                return f"{v:.1f} kV" if v >= 1 else f"{v * 1000:.0f} V"
            except (ValueError, TypeError):
                pass
        return "N/A"

    def assign_positions(node, level=0, parent_y=0):
        if node in visited_for_layout:
            return
        visited_for_layout.add(node)
        
        y_pos = level_y_tracker.get(level, parent_y)
        positions[node] = {'x': level * X_SPACING, 'y': y_pos}
        level_y_tracker[level] = y_pos + Y_SPACING

        for successor in sorted(G.successors(node)):
            assign_positions(successor, level + 1, y_pos)

    # Run layout starting from sources
    initial_y = 0
    for start_info in start_nodes_info:
        start_bus = start_info['bus']
        assign_positions(start_bus, level=1, parent_y=initial_y)
        initial_y = max(level_y_tracker.values() or [0]) + Y_SPACING * 2

    # Create React Flow nodes and edges
    nodes_added = set()
    for start_info in start_nodes_info:
        start_bus = start_info['bus']
        incomer = start_info['incomer']
        source_id = f"source-{incomer['ID']}"

        if start_bus in positions and source_id not in nodes_added:
            nodes_for_flow.append({
                "id": source_id,
                "type": "input",
                "data": {"label": f"Source: {incomer['ID']}"},
                "position": {"x": 0, "y": positions[start_bus]['y']}
            })
            nodes_added.add(source_id)

            edges_for_flow.append({
                "id": f"edge-{source_id}-{start_bus}",
                "source": source_id,
                "target": start_bus,
                "label": "Incomer"
            })

    for bus_id in G.nodes():
        if bus_id in positions and bus_id not in nodes_added:
            nodes_for_flow.append({
                "id": bus_id,
                "type": "default",
                "data": {"label": f"{bus_id}\n({get_voltage_str(bus_id)})"},
                "position": positions[bus_id]
            })
            nodes_added.add(bus_id)

    for u, v, d in G.edges(data=True):
        edge_data = d['data']
        edge_id = f"edge-{u}-{v}-{edge_data.get('ID')}"
        label = f"{edge_data.get('Type','').strip()}: {edge_data.get('ID')}"
        edges_for_flow.append({
            "id": edge_id,
            "source": u,
            "target": v,
            "label": label
        })

    return {"nodes": nodes_for_flow, "edges": edges_for_flow}
