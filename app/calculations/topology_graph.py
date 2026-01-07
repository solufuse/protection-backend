
import networkx as nx

def build_diagram(analysis_result: dict) -> dict:
    """
    Builds a React Flow compatible JSON structure with a left-to-right horizontal layout.
    """
    nodes_for_flow = []
    edges_for_flow = []
    details_map = {}
    G = nx.DiGraph()

    # 1. Create a node for every single piece of equipment
    all_equipment = {}
    analysis_types = ['incomer', 'bus', 'transformer', 'cable', 'coupling', 'incomer_breaker']

    for component_type in analysis_types:
        for item in analysis_result.get(f'{component_type}_analysis', []):
            item_id = item.get('IDBus') or item.get('ID')
            if item_id:
                item['component_label'] = component_type.replace('_', ' ').title()
                all_equipment[item_id] = item
                G.add_node(item_id)

    # 2. Create edges based on logical connections
    for incomer in analysis_result.get('incomer_analysis', []):
        if incomer.get('ID') and incomer.get('ConnectedBus'):
            G.add_edge(incomer['ID'], incomer['ConnectedBus'])

    for conn in analysis_result.get('topology', []):
        conn_id = conn.get('ID')
        from_node_id = conn.get('From')
        to_node_id = conn.get('ToSec')

        if conn_id in all_equipment and from_node_id in all_equipment and to_node_id in all_equipment:
            G.add_edge(from_node_id, conn_id)
            G.add_edge(conn_id, to_node_id)
            
    # 3. Automatic Layout Calculation for a Horizontal (Left-to-Right) Hierarchy
    positions = {}
    root_nodes = [item['ID'] for item in analysis_result.get('incomer_analysis', []) if item.get('ID') in G]

    if root_nodes:
        # Determine the level (X coordinate) of each node using BFS
        levels = {node: 0 for node in G.nodes()}
        for root in root_nodes:
            queue = [(root, 0)]
            visited_bfs = {root}
            while queue:
                u, level = queue.pop(0)
                levels[u] = max(levels[u], level)
                for v in sorted(G.successors(u)):
                    if v not in visited_bfs:
                        visited_bfs.add(v)
                        queue.append((v, level + 1))

        # Assign (x, y) positions for a horizontal layout
        X_SPACING = 300
        Y_SPACING = 150
        y_counts_per_level = {}
        
        # Sort nodes by level for processing order
        sorted_nodes = sorted(list(G.nodes()), key=lambda n: (levels.get(n, 0), n))

        for node_id in sorted_nodes:
            level = levels.get(node_id, 0)
            y_count = y_counts_per_level.get(level, 0)
            # X is determined by level (depth), Y is determined by order within the level
            positions[node_id] = {'x': level * X_SPACING, 'y': y_count * Y_SPACING}
            y_counts_per_level[level] = y_count + 1

    # 4. Generate React Flow JSON output
    for node_id, data in all_equipment.items():
        width, height = (120, 70)
        if data.get('component_label') == 'Bus':
            width, height = (350, 25)

        # Use a simple label, details are in the details_map
        lightweight_data = {'label': node_id, 'component_type': data.get('component_label')}

        nodes_for_flow.append({
            "id": node_id,
            "type": "custom",
            "position": positions.get(node_id, {'x': 0, 'y': 0}),
            "data": lightweight_data,
            "width": width,
            "height": height,
        })
        # Populate the details map for the frontend
        details_map[node_id] = data

    for u, v in G.edges():
        edges_for_flow.append({
            "id": f"e-{u}-{v}",
            "source": u, "target": v,
            "type": "smoothstep",
            "markerEnd": {"type": "arrowclosed"},
        })

    return {"nodes": nodes_for_flow, "edges": edges_for_flow, "details": details_map}
