from collections import deque

BLACK = "black"
WHITE = "white"
NONE = "none"


class Board:
    def __init__(self, board):
        self.board = board
        self.height = len(board)
        self.width = len(board[0]) if self.height > 0 else 0

    def territory(self, x, y):
        # Validate coordinates
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            raise ValueError('Invalid coordinate')
        
        # Get the stone at the coordinate
        stone_at_coord = self.board[y][x]
        
        if stone_at_coord != ' ':
            # Not an empty intersection, no territory
            return (NONE, set())
        
        # Find the territory using flood fill
        # We need to find all connected empty spaces and determine their owner
        visited = set()
        queue = deque([(x, y)])
        visited.add((x, y))
        
        # Collect all connected empty spaces
        empty_spaces = []
        while queue:
            cx, cy = queue.popleft()
            empty_spaces.append((cx, cy))
            
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    if (nx, ny) not in visited and self.board[ny][nx] == ' ':
                        visited.add((nx, ny))
                        queue.append((nx, ny))
        
        # Now determine the owner of these empty spaces
        # An empty space belongs to a player if all its neighbors are that player's stones
        # or empty spaces that also belong to that player's territory
        
        # For each empty space, check its neighbors
        # If all neighbors are either the same player's stones or empty spaces,
        # then it belongs to that player
        
        # Let's find the owner by checking boundary stones
        # For each empty space, collect all adjacent stones
        stone_neighbors = set()
        for cx, cy in empty_spaces:
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    stone_neighbors.add(self.board[ny][nx])
        
        # If no stones surround the territory, it belongs to NONE
        # If only BLACK stones surround it, it belongs to BLACK
        # If only WHITE stones surround it, it belongs to WHITE
        # If both BLACK and WHITE stones surround it, it belongs to NONE
        
        if len(stone_neighbors) == 0:
            owner = NONE
        elif 'black' in stone_neighbors and 'white' in stone_neighbors:
            owner = NONE
        elif 'black' in stone_neighbors:
            owner = BLACK
        elif 'white' in stone_neighbors:
            owner = WHITE
        else:
            owner = NONE
        
        return (owner, set(empty_spaces))

    def territories(self):
        # Calculate territories for all players
        territories = {BLACK: set(), WHITE: set(), NONE: set()}
        
        # Track which empty spaces we've already assigned
        assigned = set()
        
        for y in range(self.height):
            for x in range(self.width):
                if self.board[y][x] == ' ' and (x, y) not in assigned:
                    # Find the territory connected to this empty space
                    stone_at_coord = self.board[y][x]
                    
                    if stone_at_coord != ' ':
                        continue
                    
                    # Flood fill to find all connected empty spaces
                    visited = set()
                    queue = deque([(x, y)])
                    visited.add((x, y))
                    
                    empty_spaces = []
                    while queue:
                        cx, cy = queue.popleft()
                        empty_spaces.append((cx, cy))
                        assigned.add((cx, cy))
                        
                        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                            nx, ny = cx + dx, cy + dy
                            if 0 <= nx < self.width and 0 <= ny < self.height:
                                if (nx, ny) not in visited and self.board[ny][nx] == ' ':
                                    visited.add((nx, ny))
                                    queue.append((nx, ny))
                    
                    # Determine the owner
                    stone_neighbors = set()
                    for cx, cy in empty_spaces:
                        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                            nx, ny = cx + dx, cy + dy
                            if 0 <= nx < self.width and 0 <= ny < self.height:
                                stone_neighbors.add(self.board[ny][nx])
                    
                    if len(stone_neighbors) == 0:
                        owner = NONE
                    elif 'black' in stone_neighbors and 'white' in stone_neighbors:
                        owner = NONE
                    elif 'black' in stone_neighbors:
                        owner = BLACK
                    elif 'white' in stone_neighbors:
                        owner = WHITE
                    else:
                        owner = NONE
                    
                    territories[owner].update(empty_spaces)
        
        return territories