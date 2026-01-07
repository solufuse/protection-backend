
import networkx as nx
from collections import defaultdict

def build_diagram(analysis_result: dict) -> dict:
    """
    Builds a React Flow compatible JSON structure using a robust, multi-pass layout algorithm 
    to create a clean, inverted-tree style diagram.
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

    # 2. Advanced Layout Calculation
    positions = {}
    node_widths = { nid: (350 if d.get('component_type') == 'Bus' else 120) for nid, d in all_equipment.items() }

    try:
        # A. Assign Levels (Y-position) using topological sort
        nodes_by_level = defaultdict(list)
        for i, level_nodes in enumerate(nx.topological_generations(G)):
            for node in sorted(level_nodes):
                nodes_by_level[i].append(node)
        max_level = len(nodes_by_level) - 1

        # B. Iterative Vertex Ordering (to minimize edge crossings)
        node_order = {}
        for level in range(max_level + 1):
            for i, node in enumerate(sorted(nodes_by_level[level])):
                node_order[node] = i

        for _ in range(8): # More iterations for better convergence
            # Downward pass
            for level in range(1, max_level + 1):
                barycenters = {}
                for node in nodes_by_level[level]:
                    preds = list(G.predecessors(node))
                    if preds:
                        barycenters[node] = sum(node_order.get(p, 0) for p in preds) / len(preds)
                    else:
                        barycenters[node] = -1
                sorted_nodes = sorted(nodes_by_level[level], key=lambda n: (barycenters.get(n, -1), node_order.get(n, 0)))
                for i, node in enumerate(sorted_nodes):
                    node_order[node] = i
            # Upward pass
            for level in range(max_level - 1, -1, -1):
                barycenters = {}
                for node in nodes_by_level[level]:
                    succs = list(G.successors(node))
                    if succs:
                        barycenters[node] = sum(node_order.get(c, 0) for c in succs) / len(succs)
                    else:
                        barycenters[node] = -1
                sorted_nodes = sorted(nodes_by_level[level], key=lambda n: (barycenters.get(n, -1), node_order.get(n, 0)))
                for i, node in enumerate(sorted_nodes):
                    node_order[node] = i

        sorted_levels = {lvl: sorted(nodes, key=lambda n: node_order.get(n, 0)) for lvl, nodes in nodes_by_level.items()}

        # C. Assign Final Coordinates (Placement & Compaction)
        Y_SPACING, X_PADDING = 250, 75
        
        # Pass 1: Assign ideal X based on parent center, creating vertical alignment
        for level in range(max_level + 1):
            y_pos = level * Y_SPACING
            for node_id in sorted_levels.get(level, []):
                parent_x_centers = [positions[p]['x'] + node_widths[p] / 2 for p in G.predecessors(node_id) if p in positions]
                ideal_x = (sum(parent_x_centers) / len(parent_x_centers)) - node_widths[node_id] / 2 if parent_x_centers else node_order.get(node_id, 0) * (120 + X_PADDING)
                positions[node_id] = {'x': ideal_x, 'y': y_pos}
        
        # Pass 2: Resolve overlaps (compaction) level by level
        for level in range(max_level + 1):
            level_nodes = sorted_levels.get(level, [])
            for i in range(1, len(level_nodes)):
                prev_node, curr_node = level_nodes[i-1], level_nodes[i]
                if prev_node not in positions or curr_node not in positions: continue
                required_x = positions[prev_node]['x'] + node_widths[prev_node] + X_PADDING
                if positions[curr_node]['x'] < required_x:
                    shift = required_x - positions[curr_node]['x']
                    for j in range(i, len(level_nodes)):
                        positions[level_nodes[j]]['x'] += shift
        
        # Pass 3: Center the entire diagram globally
        max_width = 0
        for level in range(max_level + 1):
            level_nodes = sorted_levels.get(level, [])
            if not level_nodes or level_nodes[-1] not in positions or level_nodes[0] not in positions: continue
            level_width = positions[level_nodes[-1]]['x'] + node_widths[level_nodes[-1]] - positions[level_nodes[0]]['x']
            if level_width > max_width:
                max_width = level_width

        for level in range(max_level + 1):
            level_nodes = sorted_levels.get(level, [])
            if not level_nodes or level_nodes[-1] not in positions or level_nodes[0] not in positions: continue
            level_width = positions[level_nodes[-1]]['x'] + node_widths[level_nodes[-1]] - positions[level_nodes[0]]['x']
            offset = (max_width - level_width) / 2
            for node_id in level_nodes:
                positions[node_id]['x'] -= positions[level_nodes[0]]['x'] - offset

    except (nx.NetworkXUnfeasible, nx.NetworkXError) as e:
        print(f"Graph layout error: {e}. Graph may have cycles or be disconnected, using fallback.")

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
