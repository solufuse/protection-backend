
import networkx as nx
from collections import defaultdict

def build_diagram(analysis_result: dict) -> dict:
    """
    Builds a React Flow compatible JSON structure where each piece of equipment is a node.
    The output is separated into graph structure (nodes, edges) and detailed data (details).
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
                item['component_type'] = component_type.replace('_', ' ').title()
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
            
    # 3. Automatic Layout Calculation using Barycenter method
    positions = {}
    
    # Find root nodes (in-degree == 0)
    root_nodes = [n for n, d in G.in_degree() if d == 0]

    if root_nodes:
        # A. Calculate levels (y-coordinate) based on longest path from a root
        levels = {}
        try:
            topo_sorted_nodes = list(nx.topological_sort(G))
            for node in topo_sorted_nodes:
                max_level = 0
                # Level is 1 greater than the max level of its predecessors
                for pred in G.predecessors(node):
                    max_level = max(max_level, levels.get(pred, -1) + 1)
                levels[node] = max_level
        except nx.NetworkXUnfeasible: # Handle cycles gracefully
            # Fallback to simple BFS for level calculation if cycles exist
            for root in root_nodes:
                if root not in levels:
                    levels[root] = 0
                queue = [(root, 0)]
                visited_bfs = {root}
                while queue:
                    u, level = queue.pop(0)
                    for v in sorted(G.successors(u)):
                        if v not in visited_bfs:
                            visited_bfs.add(v)
                            levels[v] = max(levels.get(v, 0), level + 1)
                            queue.append((v, level + 1))
        
        nodes_by_level = defaultdict(list)
        for node, level in levels.items():
            nodes_by_level[level].append(node)

        # B. Calculate initial horizontal positions (x-coordinate) using barycenter method
        # This requires multiple passes to improve layout
        node_order = {} # Stores final x-order index for each node within its level
        
        # Initialize order for level 0
        for i, node in enumerate(sorted(nodes_by_level.get(0, []))):
            node_order[node] = i

        # Iterate down the levels, positioning children based on parents (barycenter)
        max_level = max(nodes_by_level.keys()) if nodes_by_level else -1
        for level in range(1, max_level + 1):
            level_nodes = nodes_by_level[level]
            barycenters = {}
            for node in level_nodes:
                predecessors = list(G.predecessors(node))
                if not predecessors:
                    barycenters[node] = 0
                    continue
                
                # Get the order index of predecessors
                pred_orders = [node_order[p] for p in predecessors if p in node_order]
                if not pred_orders:
                     barycenters[node] = 0
                     continue
                
                barycenters[node] = sum(pred_orders) / len(pred_orders)
            
            # Sort nodes in the current level based on their barycenter value
            sorted_nodes = sorted(level_nodes, key=lambda n: barycenters.get(n, 0))
            for i, node in enumerate(sorted_nodes):
                node_order[node] = i

        # C. Assign final coordinates and resolve overlaps
        Y_SPACING = 200
        X_PADDING = 50
        
        node_widths = {
            node_id: (350 if data.get('component_type') == 'Bus' else 120)
            for node_id, data in all_equipment.items()
        }

        # Use the established order to place nodes and resolve overlaps
        level_x_starts = {}
        for level in range(max_level + 1):
            nodes_on_level = sorted(nodes_by_level[level], key=lambda n: node_order.get(n, 0))
            
            level_x_starts[level] = {}
            last_x_pos = 0
            for node_id in nodes_on_level:
                # Store the starting x for this node
                level_x_starts[level][node_id] = last_x_pos
                last_x_pos += node_widths.get(node_id, 120) + X_PADDING
        
        # Center each level relative to the widest level
        max_width = max((sum(node_widths.get(n, 120) for n in nodes) + max(0, len(nodes) - 1) * X_PADDING)
                        for level, nodes in nodes_by_level.items()) if nodes_by_level else 0

        for level in range(max_level + 1):
            nodes_on_level = nodes_by_level[level]
            level_width = (sum(node_widths.get(n, 120) for n in nodes_on_level) + 
                           max(0, len(nodes_on_level) - 1) * X_PADDING)
            offset = (max_width - level_width) / 2
            
            for node_id in nodes_on_level:
                pos_x = level_x_starts[level][node_id] + offset
                pos_y = level * Y_SPACING
                positions[node_id] = {'x': pos_x, 'y': pos_y}


    # 4. Generate React Flow JSON output
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
            "id": node_id,
            "type": "custom",
            "position": positions.get(node_id, {'x': 0, 'y': 0}),
            "data": lightweight_data,
            "width": width, "height": height,
        })
        details_map[node_id] = data

    for u, v in G.edges():
        edges_for_flow.append({
            "id": f"e-{u}-{v}",
            "source": u, "target": v,
            "type": "smoothstep",
            "markerEnd": {"type": "arrowclosed"},
        })

    return {"nodes": nodes_for_flow, "edges": edges_for_flow, "details": details_map}
