
import networkx as nx
from collections import defaultdict

def build_diagram(analysis_result: dict) -> dict:
    """
    Builds a React Flow compatible JSON structure using a two-pass "Center & Shift" layout 
    algorithm, reflecting the concept of "nested propositions" to ensure straight vertical alignments.
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
                item['component_type'] = component_type.replace('_', ' ').title()
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

    # --- LAYOUT ALGORITHM: "Center & Shift" --- 
    positions = {}
    node_widths = { nid: (350 if d.get('component_type') == 'Bus' else 120) for nid, d in all_equipment.items() }

    try:
        if not nx.is_directed_acyclic_graph(G):
             raise nx.NetworkXUnfeasible("Graph has cycles.")

        # A. Pre-computation: Levels and horizontal order to minimize crossings
        nodes_by_level = defaultdict(list)
        for i, generation in enumerate(nx.topological_generations(G)):
            nodes_by_level[i] = sorted(list(generation))
        max_level = len(nodes_by_level) - 1
        
        node_order = {node: i for level in nodes_by_level.values() for i, node in enumerate(level)}
        for _ in range(8): # Barycenter method to stabilize layout
            for level in range(1, max_level + 1):
                barycenters = {n: sum(node_order.get(p, 0) for p in G.predecessors(n)) / len(list(G.predecessors(n))) if G.predecessors(n) else -1 for n in nodes_by_level[level]}
                nodes_by_level[level].sort(key=lambda n: barycenters.get(n, -1))
                for i, node in enumerate(nodes_by_level[level]): node_order[node] = i

        # B. Pass 1: Idealistic Placement (The Initial Proposition)
        # Position nodes centered under their parents, ignoring all overlaps.
        Y_SPACING = 250
        for level in range(max_level + 1):
            for node_id in nodes_by_level[level]:
                width = node_widths[node_id]
                parents = list(G.predecessors(node_id))
                ideal_x = 0
                if parents:
                    parent_centers = [positions[p]['x'] + node_widths[p] / 2 for p in parents if p in positions]
                    if parent_centers:
                        ideal_x = sum(parent_centers) / len(parent_centers) - width / 2
                positions[node_id] = {'x': ideal_x, 'y': level * Y_SPACING}

        # C. Pass 2: Resolve Overlaps by Shifting Subtrees (The Nested/Corrective Proposition)
        X_PADDING = 75
        all_descendants = {n: list(nx.descendants(G, n)) for n in G.nodes()}
        for level in range(max_level + 1):
            level_nodes = nodes_by_level[level]
            for i in range(1, len(level_nodes)):
                right_node = level_nodes[i]
                left_node = level_nodes[i-1]

                left_bound = positions[left_node]['x'] + node_widths[left_node]
                right_bound = positions[right_node]['x']
                
                if right_bound < left_bound + X_PADDING:
                    shift = (left_bound + X_PADDING) - right_bound
                    nodes_to_shift = [right_node] + all_descendants.get(right_node, [])
                    for node_to_shift in nodes_to_shift:
                        if node_to_shift in positions:
                            positions[node_to_shift]['x'] += shift

        # D. Final Centering
        if positions:
            min_x = min((p['x'] for p in positions.values()), default=0)
            for node_id in positions:
                positions[node_id]['x'] -= min_x

    except (nx.NetworkXUnfeasible, nx.NetworkXError) as e:
        print(f"Graph layout error: {e}. Fallback to basic layout.")

    # 3. Generate React Flow JSON
    for node_id, data in all_equipment.items():
        w = node_widths.get(node_id, 120)
        h = 25 if data.get('component_type') == 'Bus' else 70
        vn_str = ""
        if data.get('component_type') == 'Bus':
            vn_kv = data.get('NomlkV', data.get('BasekV', ''))
            try: 
                vn = float(vn_kv)
                vn_str = f" ({vn:.1f} kV)" if vn >= 1 else f" ({vn*1000:.0f} V)"
            except (ValueError, TypeError): 
                vn_str = f" ({vn_kv})" if vn_kv else ""

        nodes_for_flow.append({
            "id": node_id, "type": "custom", "position": positions.get(node_id, {'x': 0, 'y': 0}),
            "data": {'label': node_id + vn_str, 'component_type': data.get('component_type', 'Equipment')},
            "width": w, "height": h,
        })
        details_map[node_id] = data

    for u, v in G.edges():
        edges_for_flow.append({
            "id": f"e-{u}-{v}", "source": u, "target": v, "type": "smoothstep", "markerEnd": {"type": "arrowclosed"},
        })

    return {"nodes": nodes_for_flow, "edges": edges_for_flow, "details": details_map}
