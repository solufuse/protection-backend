
import pandas as pd
import networkx as nx

def build_diagram(analysis_result: dict) -> dict:
    """
    Builds a hierarchical, text-based diagram of the electrical network topology.
    """
    G = nx.DiGraph()
    bus_voltages = {bus['IDBus']: bus.get('BasekV', 0) for bus in analysis_result.get('bus_analysis', [])}

    # Add nodes with data
    for component_type in ['incomer', 'incomer_breaker', 'bus', 'transformer', 'cable', 'coupling']:
        for item in analysis_result.get(f'{component_type}_analysis', []):
            node_id = item.get('ID') or item.get('IDBus')
            if node_id:
                G.add_node(node_id, data=item, type=component_type.upper())

    # Add edges from the main topology data
    for conn in analysis_result.get('topology', []):
        from_node = conn.get('From')
        to_node = conn.get('ToSec')
        if from_node and to_node and G.has_node(from_node) and G.has_node(to_node):
            G.add_edge(from_node, to_node, type='CONNECTION', data=conn)

    # Find starting points (incomers)
    start_nodes = [incomer['ConnectedBus'] for incomer in analysis_result.get('incomer_analysis', []) if 'ConnectedBus' in incomer]
    if not start_nodes:
        return {"diagram": "No incomer found to start the diagram."}

    # Generate the diagram string
    diagram_str = ""
    visited_nodes = set()

    def get_voltage(bus_id):
        return bus_voltages.get(bus_id, 0)

    def format_node(node_id, node_data):
        node_type = node_data.get('type', 'UNKNOWN')
        if node_type == 'BUS':
            voltage = bus_voltages.get(node_id, 'N/A')
            return f"BUS: {node_id} ({voltage} kV)"
        return f"{node_type}: {node_id}"

    def build_path(start_node, indent_level=0):
        nonlocal diagram_str
        if start_node in visited_nodes:
            return
        
        visited_nodes.add(start_node)
        prefix = "    " * indent_level
        node_data = G.nodes.get(start_node, {})
        diagram_str += f"{prefix}{format_node(start_node, node_data)}\n"

        # Sort successors by voltage level (descending)
        successors = sorted(list(G.successors(start_node)), key=lambda n: get_voltage(n), reverse=True)
        
        for succ in successors:
            edge_data = G.get_edge_data(start_node, succ).get('data', {})
            edge_id = edge_data.get('ID', 'Direct Connection')
            edge_type = edge_data.get('Type', '').strip()
            
            diagram_str += f"{prefix}  --> {edge_type}: {edge_id}\n"
            build_path(succ, indent_level + 1)

    # Build diagram from all starting points
    for start_node in sorted(start_nodes, key=lambda n: get_voltage(n), reverse=True):
        diagram_str += "--- START OF FEEDER ---\n"
        build_path(start_node)
        diagram_str += "--- END OF FEEDER ---\n\n"

    return {"diagram": diagram_str.strip()}
