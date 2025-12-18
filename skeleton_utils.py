import math

def skeletonize(image, w=None, h=None):
    """
    Wrapper for Zhang-Suen thinning to match expected signature.
    Adds padding to ensure boundary pixels are processed.
    """
    rows = len(image)
    if rows == 0: return image
    cols = len(image[0])
    
    # Pad with 0
    padded_image = []
    padded_image.append([0] * (cols + 2)) # Top padding
    for row in image:
        padded_image.append([0] + row + [0]) # Left/Right padding
    padded_image.append([0] * (cols + 2)) # Bottom padding
    
    thinned = zhang_suen_thinning(padded_image)
    
    # Unpad
    result = []
    for r in range(1, rows + 1):
        result.append(thinned[r][1:cols+1])
        
    return result

def zhang_suen_thinning(image):
    """
    Implements the Zhang-Suen thinning algorithm.
    image: A list of lists (2D array) where 1 is foreground and 0 is background.
    Returns a thinned version of the image.
    """
    # Create a copy to modify
    rows = len(image)
    cols = len(image[0])
    img = [row[:] for row in image]
    
    def get_pixel(r, c):
        if 0 <= r < rows and 0 <= c < cols:
            return img[r][c]
        return 0

    def count_neighbors(r, c):
        # P9 P2 P3
        # P8 P1 P4
        # P7 P6 P5
        neighbors = [
            get_pixel(r-1, c),   # P2
            get_pixel(r-1, c+1), # P3
            get_pixel(r, c+1),   # P4
            get_pixel(r+1, c+1), # P5
            get_pixel(r+1, c),   # P6
            get_pixel(r+1, c-1), # P7
            get_pixel(r, c-1),   # P8
            get_pixel(r-1, c-1)  # P9
        ]
        return neighbors

    def transitions(neighbors):
        # Count 0->1 transitions in the sequence P2, P3, ..., P9, P2
        n = neighbors + [neighbors[0]]
        return sum(1 for i in range(8) if n[i] == 0 and n[i+1] == 1)

    changed = True
    while changed:
        changed = False
        # Step 1
        to_delete = []
        for r in range(1, rows - 1):
            for c in range(1, cols - 1):
                if img[r][c] == 0:
                    continue
                
                nbrs = count_neighbors(r, c)
                B = sum(nbrs)
                A = transitions(nbrs)
                
                # Conditions
                # 2 <= B <= 6
                # A == 1
                # P2 * P4 * P6 == 0
                # P4 * P6 * P8 == 0
                
                if (2 <= B <= 6) and (A == 1) and \
                   (nbrs[0] * nbrs[2] * nbrs[4] == 0) and \
                   (nbrs[2] * nbrs[4] * nbrs[6] == 0):
                    to_delete.append((r, c))
        
        if to_delete:
            changed = True
            for r, c in to_delete:
                img[r][c] = 0
                
        # Step 2
        to_delete = []
        for r in range(1, rows - 1):
            for c in range(1, cols - 1):
                if img[r][c] == 0:
                    continue
                
                nbrs = count_neighbors(r, c)
                B = sum(nbrs)
                A = transitions(nbrs)
                
                # Conditions
                # 2 <= B <= 6
                # A == 1
                # P2 * P4 * P8 == 0
                # P2 * P6 * P8 == 0
                
                if (2 <= B <= 6) and (A == 1) and \
                   (nbrs[0] * nbrs[2] * nbrs[6] == 0) and \
                   (nbrs[0] * nbrs[4] * nbrs[6] == 0):
                    to_delete.append((r, c))
                    
        if to_delete:
            changed = True
            for r, c in to_delete:
                img[r][c] = 0
                
    return img

def smooth_path(path, iterations=3):
    """
    Smooths a path using a simple moving average (Chaikin-like) approach.
    path: list of (x, y) tuples
    """
    if len(path) < 3:
        return path
        
    smoothed = list(path)
    for _ in range(iterations):
        new_path = [smoothed[0]]
        for i in range(1, len(smoothed) - 1):
            p0 = smoothed[i-1]
            p1 = smoothed[i]
            p2 = smoothed[i+1]
            
            # Average
            nx = (p0[0] + 2*p1[0] + p2[0]) / 4
            ny = (p0[1] + 2*p1[1] + p2[1]) / 4
            new_path.append((nx, ny))
        new_path.append(smoothed[-1])
        smoothed = new_path
    return smoothed

def trace_skeleton(skeleton, w=None, h=None):
    """
    Converts a skeletonized bitmap into a list of paths (list of points).
    Returns list of lists of (x, y) tuples.
    """
    rows = len(skeleton)
    cols = len(skeleton[0])
    
    def get_neighbors(r, c):
        # 8-connectivity
        nbrs = []
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0: continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and skeleton[nr][nc] == 1:
                    nbrs.append((nr, nc))
        return nbrs

    # Build graph
    graph = {}
    nodes = []
    for r in range(rows):
        for c in range(cols):
            if skeleton[r][c] == 1:
                nodes.append((r, c))
                graph[(r, c)] = get_neighbors(r, c)

    if not nodes:
        return []

    # Identify junctions and endpoints
    junctions = set()
    endpoints = set()
    for n in nodes:
        deg = len(graph[n])
        if deg != 2:
            if deg == 1: endpoints.add(n)
            else: junctions.add(n)
            
    # If loop (all degree 2), pick one as start
    if not endpoints and not junctions and nodes:
        endpoints.add(nodes[0])

    # Trace segments
    visited_edges = set()
    paths = []
    
    # Start from endpoints and junctions
    start_nodes = list(endpoints) + list(junctions)
    if not start_nodes and nodes: start_nodes = [nodes[0]]
    
    for start_node in start_nodes:
        for neighbor in graph[start_node]:
            edge = tuple(sorted((start_node, neighbor)))
            if edge in visited_edges: continue
            
            # Walk
            path = [start_node, neighbor]
            visited_edges.add(edge)
            
            curr = neighbor
            prev = start_node
            
            while True:
                # If curr is a junction or endpoint, stop
                if curr in junctions or curr in endpoints:
                    break
                
                # Find next neighbor
                nbrs = graph[curr]
                next_n = None
                for n in nbrs:
                    if n != prev:
                        next_n = n
                        break
                
                if next_n is None: # Dead end? Should be endpoint.
                    break
                    
                edge = tuple(sorted((curr, next_n)))
                if edge in visited_edges: break
                
                path.append(next_n)
                visited_edges.add(edge)
                
                prev = curr
                curr = next_n
                
                # If we looped back to start
                if curr == start_node:
                    break
            
            # Smooth the path
            if len(path) > 2:
                # Convert (r, c) to (x, y) for smoothing
                # Note: r is y, c is x.
                xy_path = [(c, r) for r, c in path]
                smoothed_xy = smooth_path(xy_path)
                paths.append(smoothed_xy)
            else:
                # Convert to (x, y)
                xy_path = [(c, r) for r, c in path]
                paths.append(xy_path)
                
    return paths

