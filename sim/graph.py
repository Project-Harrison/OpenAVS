"""
Ocean routing graph — grid of sea nodes sampled from chart_bg pixels.
A* pathfinding for AIS vessel route assignment.
"""
import math
import heapq


def build_graph(chart_is_sea, lat_min, lat_max, lon_min, lon_max,
                n_cols=50, n_rows=40):
    """
    Sample a regular grid over the viewport, keep only sea nodes,
    connect 8-directional neighbours.

    Returns (graph, lats, lons) where:
      graph : {(r,c): [((nr,nc), cost_nm), ...]}
      lats  : list, index r → latitude   (r=0 is lat_min)
      lons  : list, index c → longitude  (c=0 is lon_min)
    """
    lats = [lat_min + (lat_max - lat_min) * r / max(n_rows - 1, 1)
            for r in range(n_rows)]
    lons = [lon_min + (lon_max - lon_min) * c / max(n_cols - 1, 1)
            for c in range(n_cols)]

    sea = set()
    for r in range(n_rows):
        for c in range(n_cols):
            if chart_is_sea(lats[r], lons[c]):
                sea.add((r, c))

    dlat = lats[1] - lats[0] if n_rows > 1 else 1e-3
    dlon = lons[1] - lons[0] if n_cols > 1 else 1e-3

    graph = {}
    for (r, c) in sea:
        nbrs = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if (nr, nc) in sea:
                    dlat_nm = dr * dlat * 60
                    dlon_nm = dc * dlon * 60 * math.cos(math.radians(lats[r]))
                    nbrs.append(((nr, nc), math.sqrt(dlat_nm ** 2 + dlon_nm ** 2)))
        graph[(r, c)] = nbrs

    return graph, lats, lons


def latlon_to_node(lat, lon, lats, lons):
    """Snap a lat/lon to the nearest grid indices."""
    if len(lats) < 2 or len(lons) < 2:
        return 0, 0
    r = int(round((lat - lats[0]) / (lats[1] - lats[0])))
    c = int(round((lon - lons[0]) / (lons[1] - lons[0])))
    return max(0, min(len(lats) - 1, r)), max(0, min(len(lons) - 1, c))


def find_nearest_sea_node(lat, lon, lats, lons, graph, max_search=15):
    """Return nearest (r, c) that is in the graph (sea), or None."""
    r0, c0 = latlon_to_node(lat, lon, lats, lons)
    if (r0, c0) in graph:
        return r0, c0
    for radius in range(1, max_search + 1):
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                if abs(dr) != radius and abs(dc) != radius:
                    continue
                nr, nc = r0 + dr, c0 + dc
                if (nr, nc) in graph:
                    return nr, nc
    return None


def node_to_latlon(r, c, lats, lons):
    return lats[r], lons[c]


def _heuristic(node, goal, lats, lons):
    r1, c1 = node
    r2, c2 = goal
    dlat = (lats[r2] - lats[r1]) * 60
    mid  = (lats[r1] + lats[r2]) / 2
    dlon = (lons[c2] - lons[c1]) * 60 * math.cos(math.radians(mid))
    return math.sqrt(dlat ** 2 + dlon ** 2)


def astar(graph, start, goal, lats, lons):
    """Return list of (r,c) from start to goal, or [] if unreachable."""
    if start == goal:
        return [start]
    if start not in graph or goal not in graph:
        return []

    open_set  = [(0.0, start)]
    came_from = {}
    g         = {start: 0.0}

    while open_set:
        _, current = heapq.heappop(open_set)
        if current == goal:
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.append(start)
            return list(reversed(path))
        for nbr, cost in graph.get(current, []):
            ng = g[current] + cost
            if ng < g.get(nbr, float('inf')):
                came_from[nbr] = current
                g[nbr] = ng
                heapq.heappush(open_set,
                               (ng + _heuristic(nbr, goal, lats, lons), nbr))
    return []


def pick_destination(start_r, start_c, course_deg, lats, lons, graph,
                     n_rows, n_cols):
    """
    Pick a destination node roughly in the direction of course_deg,
    near the far edge of the grid.
    """
    crad   = math.radians(course_deg)
    dr_dir = math.cos(crad)   # N component → row index increases north
    dc_dir = math.sin(crad)   # E component → col index increases east

    steps  = max(n_rows, n_cols) * 2
    tr     = max(0, min(n_rows - 1, int(round(start_r + dr_dir * steps))))
    tc     = max(0, min(n_cols - 1, int(round(start_c + dc_dir * steps))))

    goal = find_nearest_sea_node(lats[tr], lons[tc], lats, lons, graph,
                                 max_search=30)
    if goal is None or goal == (start_r, start_c):
        # Fall back: the node farthest from start
        best, best_d = None, -1
        for node in graph:
            d = abs(node[0] - start_r) + abs(node[1] - start_c)
            if d > best_d:
                best_d, best = d, node
        goal = best
    return goal
