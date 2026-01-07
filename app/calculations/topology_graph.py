
import networkx as nx
from collections import defaultdict

def build_diagram(analysis_result: dict) -> dict:
    """
    Builds a React Flow compatible JSON structure with an advanced layout algorithm.
    """
    nodes_for_flow = []
    edges_for_flow = []
    details_map = {}
    G = nx.DiGraph()

    # 1. Build Graph
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
    node_widths = {
        node_id: (350 if data.get('component_type') == 'Bus' else 120)
        for node_id, data in all_equipment.items()
    }
    
    try:
        # A. Assign Levels (Y-position) using topological sort
        nodes_by_level = defaultdict(list)
        levels = {}
        for i, level_nodes in enumerate(nx.topological_generations(G)):
            for node in sorted(level_nodes):
                nodes_by_level[i].append(node)
                levels[node] = i
        
        max_level = len(nodes_by_level) - 1

        # B. Determine Horizontal Order (Barycenter Method)
        node_order = {}  # Stores float value for sorting
        for i in range(max_level + 1):
            for node in nodes_by_level[i]:
                parent_orders = [node_order.get(p, 0) for p in G.predecessors(node)]
                if parent_orders:
                    node_order[node] = sum(parent_orders) / len(parent_orders)
                else: # Root or level 0 node
                    # Initial placement for level 0, will be sorted later
                    node_order[node] = len(node_order) 

            # Sort nodes within the level by their barycenter value to create a stable order
            sorted_level_nodes = sorted(nodes_by_level[i], key=lambda n: node_order[n])
            # Update the order to be an integer index for the next iteration
            for idx, node in enumerate(sorted_level_nodes):
                node_order[node] = idx
                
        # Get final sorted lists per level
        sorted_levels = {lvl: sorted(nodes, key=lambda n: node_order[n]) for lvl, nodes in nodes_by_level.items()}

        # C. Assign Final Coordinates (3-pass method)
        Y_SPACING, X_PADDING = 250, 75

        # Pass 1: Ideal X-position based on parents' final position
        for level in range(max_level + 1):
            y_pos = level * Y_SPACING
            if level == 0:
                # Place root nodes sequentially first
                x_pos = 0
                for node_id in sorted_levels.get(level, []):
                    positions[node_id] = {'x': x_pos, 'y': y_pos}
                    x_pos += node_widths.get(node_id, 120) + X_PADDING
                continue
            
            for node_id in sorted_levels.get(level, []):
                parent_x_centers = [positions[p]['x'] + node_widths.get(p, 120) / 2 for p in G.predecessors(node_id) if p in positions]
                if parent_x_centers:
                    ideal_x = (sum(parent_x_centers) / len(parent_x_centers)) - node_widths.get(node_id, 120) / 2
                    positions[node_id] = {'x': ideal_x, 'y': y_pos}
                else:
                    positions[node_id] = {'x': 0, 'y': y_pos}

        # Pass 2: Resolve overlaps, preserving the sorted order
        for level in range(max_level + 1):
            level_nodes = sorted_levels.get(level, [])
            for i in range(1, len(level_nodes)):
                prev_node, curr_node = level_nodes[i-1], level_nodes[i]
                required_x = positions[prev_node]['x'] + node_widths.get(prev_node, 120) + X_PADDING
                if positions[curr_node]['x'] < required_x:
                    positions[curr_node]['x'] = required_x

        # Pass 3: Center the entire layout
        min_x = min((p['x'] for p in positions.values()), default=0)
        max_x = max((p['x'] + node_widths.get(nid, 120) for nid, p in positions.items()), default=0)
        diagram_width = max_x - min_x
        
        level_widths = {}
        for level in range(max_level + 1):
            level_nodes = sorted_levels.get(level, [])
            if not level_nodes: continue
            
            first_node_x = positions[level_nodes[0]]['x']
            last_node_x_end = positions[level_nodes[-1]]['x'] + node_widths.get(level_nodes[-1], 120)
            level_widths[level] = last_node_x_end - first_node_x
            
            offset = (diagram_width - level_widths[level]) / 2 - first_node_x
            for node_id in level_nodes:
                positions[node_id]['x'] += offset
                
    except nx.NetworkXUnfeasible:
        # Fallback for graphs with cycles (less optimal layout)
        print("Graph has cycles, using fallback layout.")
        # ... (previous simpler layout logic could be here) ...

    # 3. Generate React Flow JSON
    for node_id, data in all_equipment.items():
        width, height = (120, 70)
        component_type = data.get('component_type', 'Equipment')
        lightweight_data = {'label': node_id, 'component_type': component_type}
        
        if component_type == 'Bus':
            width, height = (350, 25)
            vn_kv = data.get('NomlkV', data.get('BasekV', ''))
            try:
                vn = float(vn_kv)
                vn_str = f"{vn:.1f} kV" if vn >= 1 else f"{vn*1000:.0f} V"
                lightweight_data['label'] = f"{node_id} ({vn_str})"
            except (ValueError, TypeError):
                lightweight_data['label'] = f"{node_id} ({vn_kv})"

        nodes_for_flow.append({
            "id": node_id, "type": "custom",
            "position": positions.get(node_id, {'x': 0, 'y': 0}),
            "data": lightweight_data, "width": width, "height": height,
        })
        details_map[node_id] = data

    for u, v in G.edges():
        edges_for_flow.append({
            "id": f"e-{u}-{v}", "source": u, "target": v,
            "type": "smoothstep", "markerEnd": {"type": "arrowclosed"},
        })

    return {"nodes": nodes_for_flow, "edges": edges_for_flow, "details": details_map}

