
import networkx as nx
from collections import defaultdict

def build_diagram(analysis_result: dict) -> dict:
    """
    Builds a React Flow diagram using a "Horizontal Center & Shift" layout algorithm 
    to produce a readable left-to-right hierarchical graph.
    """
    nodes_for_flow = []
    edges_for_flow = []
    details_map = {}
    G = nx.DiGraph()

    # 1. Build Graph from analysis results
    all_equipment = {}
    analysis_types = ['incomer', 'bus', 'transformer', 'cable', 'coupling', 'incomer_breaker']
    for component_type in analysis_types:
        for item in analysis_result.get(f'{component_type}_analysis', []):
            item_id = item.get('IDBus') or item.get('ID')
            if item_id:
                item['component_label'] = component_type.replace('_', ' ').title()
                all_equipment[item_id] = item
                G.add_node(item_id)

    for incomer in analysis_result.get('incomer_analysis', []):
        if incomer.get('ID') and incomer.get('ConnectedBus'):
            G.add_edge(incomer['ID'], incomer['ConnectedBus'])

    for conn in analysis_result.get('topology', []):
        conn_id, from_node, to_node = conn.get('ID'), conn.get('From'), conn.get('ToSec')
        if conn_id in all_equipment and from_node in all_equipment and to_node in all_equipment:
            G.add_edge(from_node, conn_id)
            G.add_edge(conn_id, to_node)

    # --- LAYOUT ALGORITHM: "Horizontal Center & Shift" ---
    positions = {}
    node_heights = {nid: (25 if d.get('component_label') == 'Bus' else 70) for nid, d in all_equipment.items()}

    try:
        if not nx.is_directed_acyclic_graph(G):
            raise nx.NetworkXUnfeasible("Graph has cycles.")

        # A. Assign levels (X-coordinates) and pre-sort nodes to minimize crossings
        nodes_by_level = defaultdict(list)
        for i, generation in enumerate(nx.topological_generations(G)):
            nodes_by_level[i] = sorted(list(generation))
        max_level = len(nodes_by_level) - 1

        # Use barycenter method to refine vertical order within levels
        node_order = {node: i for level in nodes_by_level.values() for i, node in enumerate(level)}
        for _ in range(8): # Iterations for stability
            for level in range(1, max_level + 1):
                barycenters = {n: sum(node_order.get(p, 0) for p in G.predecessors(n)) / len(list(G.predecessors(n))) if list(G.predecessors(n)) else -1 for n in nodes_by_level[level]}
                nodes_by_level[level].sort(key=lambda n: barycenters.get(n, -1))
                for i, node in enumerate(nodes_by_level[level]): node_order[node] = i

        # B. Pass 1: Idealistic Placement (Center next to parents, ignore overlaps)
        X_SPACING = 300
        for level in range(max_level + 1):
            for node_id in nodes_by_level[level]:
                height = node_heights.get(node_id, 70)
                ideal_y = 0
                parents = list(G.predecessors(node_id))
                if parents and all(p in positions for p in parents):
                    parent_centers = [positions[p]['y'] + node_heights[p] / 2 for p in parents]
                    ideal_y = sum(parent_centers) / len(parent_centers) - height / 2
                positions[node_id] = {'x': level * X_SPACING, 'y': ideal_y}
        
        # C. Pass 2: Resolve Overlaps by Shifting Subtrees Downwards
        Y_PADDING = 50
        all_descendants = {n: nx.descendants(G, n) for n in G.nodes()}
        for level in range(max_level + 1):
            level_nodes = nodes_by_level[level]
            level_nodes.sort(key=lambda n: positions[n]['y'])
            
            for i in range(1, len(level_nodes)):
                upper_node = level_nodes[i-1]
                lower_node = level_nodes[i]
                
                upper_bound = positions[upper_node]['y'] + node_heights[upper_node]
                lower_bound = positions[lower_node]['y']
                
                if lower_bound < upper_bound + Y_PADDING:
                    shift = (upper_bound + Y_PADDING) - lower_bound
                    nodes_to_shift = all_descendants[lower_node].union({lower_node})
                    for node_to_shift in nodes_to_shift:
                        if node_to_shift in positions:
                            positions[node_to_shift]['y'] += shift

        # D. Final Vertical Centering
        if positions:
            min_y = min((p['y'] for p in positions.values()), default=0)
            if min_y < 0:
                for node_id in positions:
                    positions[node_id]['y'] -= min_y

    except (nx.NetworkXUnfeasible, nx.NetworkXError) as e:
        print(f"Graph layout error: {e}.")
        positions = nx.spring_layout(G, iterations=50) # Fallback

    # 4. Generate React Flow JSON
    for node_id, data in all_equipment.items():
        width = (350 if data.get('component_label') == 'Bus' else 120)
        height = node_heights.get(node_id, 70)
        lightweight_data = {'label': node_id, 'component_type': data.get('component_label')}

        nodes_for_flow.append({
            "id": node_id, "type": "custom", "position": positions.get(node_id, {'x': 0, 'y': 0}),
            "data": lightweight_data, "width": width, "height": height,
        })
        details_map[node_id] = data

    for u, v in G.edges():
        edges_for_flow.append({
            "id": f"e-{u}-{v}", "source": u, "target": v, "type": "smoothstep", "markerEnd": {"type": "arrowclosed"},
        })

    return {"nodes": nodes_for_flow, "edges": edges_for_flow, "details": details_map}
