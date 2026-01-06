
import networkx as nx

def build_diagram(analysis_result: dict) -> dict:
    """
    Builds a hierarchical, text-based diagram of the electrical network topology.
    """
    G = nx.DiGraph()
    
    bus_analysis = analysis_result.get('bus_analysis', [])
    if not bus_analysis:
        return {"diagram": "No bus data found to build the diagram."}
        
    bus_voltages = {bus['IDBus']: bus.get('BasekV', 0) for bus in bus_analysis}

    # 1. Nodes are Buses
    for bus_id in bus_voltages:
        G.add_node(bus_id, type='BUS')

    # 2. Edges are connecting equipment
    for conn in analysis_result.get('topology', []):
        from_bus = conn.get('From')
        to_bus = conn.get('ToSec')
        equip_id = conn.get('ID')
        equip_type = conn.get('Type', 'LINK').strip()

        if G.has_node(from_bus) and G.has_node(to_bus):
            G.add_edge(from_bus, to_bus, id=equip_id, type=equip_type)

    # 3. Find starting points (incomers)
    start_nodes_info = []
    for incomer in analysis_result.get('incomer_analysis', []):
        source_id = incomer.get('ID', 'SOURCE')
        connected_bus = incomer.get('ConnectedBus')
        if G.has_node(connected_bus):
            start_nodes_info.append({'bus': connected_bus, 'source_id': source_id})

    if not start_nodes_info:
        return {"diagram": "No incomer found to start the diagram."}

    # 4. Generate the diagram string
    final_diagram = ""
    
    def get_voltage_str(bus_id):
        voltage = bus_voltages.get(bus_id)
        if voltage is not None:
            if voltage >= 1:
                return f"{voltage:.1f} kV"
            return f"{voltage * 1000:.0f} V"
        return "N/A"

    visited_nodes = set()

    def trace_feeder(bus_node, prefix=""):
        nonlocal final_diagram
        if bus_node in visited_nodes:
            final_diagram += f'{prefix}└─> [Path already displayed: {bus_node}]\n'
            return
            
        visited_nodes.add(bus_node)

        outgoing_edges = sorted(G.out_edges(bus_node, data=True), key=lambda x: x[1])

        for i, (u, v, edge_data) in enumerate(outgoing_edges):
            is_last = (i == len(outgoing_edges) - 1)
            branch_char = "└─" if is_last else "├─"
            new_prefix = prefix + ("    " if is_last else "│   ")

            equip_type = edge_data.get('type', 'LINK')
            equip_id = edge_data.get('id', '?')
            
            final_diagram += f'{prefix}{branch_char}[{equip_type}: {equip_id}]───>'
            final_diagram += f"BUS: {v} ({get_voltage_str(v)})\n'
            
            trace_feeder(v, new_prefix)

    # Main loop to start tracing from each incomer
    for start_info in start_nodes_info:
        start_bus = start_info['bus']
        source_id = start_info['source_id']
        final_diagram += f"SOURCE: {source_id}\n"
        final_diagram += f"   │\n"
        final_diagram += f"   └──────>BUS: {start_bus} ({get_voltage_str(start_bus)})\n"
        
        trace_feeder(start_bus, "           ")
        final_diagram += "\n"

    return {"diagram": final_diagram.strip()}
