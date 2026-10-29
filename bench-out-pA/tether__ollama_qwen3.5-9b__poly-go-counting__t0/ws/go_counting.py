from collections import deque

WHITE = 'W'
BLACK = 'B'
NONE = ' '


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
        
        if stone_at_coord != NONE:
            # If there's a stone, it's not territory
            return (NONE, set())
        
        # Find the territory using flood fill
        return self._find_territory(x, y)

    def _find_territory(self, start_x, start_y):
        # BFS to find all connected empty intersections
        visited = set()
        queue = deque([(start_x, start_y)])
        visited.add((start_x, start_y))
        
        # Collect all connected empty intersections
        territory_points = []
        
        while queue:
            x, y = queue.popleft()
            territory_points.append((x, y))
            
            # Check all 4 neighbors (horizontal and vertical)
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = x + dx, y + dy
                
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    if (nx, ny) not in visited:
                        neighbor = self.board[ny][nx]
                        if neighbor == NONE:
                            visited.add((nx, ny))
                            queue.append((nx, ny))
        
        # Now determine which player owns this territory
        # A territory belongs to a player if all boundary stones are that player's
        # and there are no stones of the other player
        
        black_boundary = False
        white_boundary = False
        
        for x, y in territory_points:
            # Check all 4 neighbors
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = x + dx, y + dy
                
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    neighbor = self.board[ny][nx]
                    if neighbor == BLACK:
                        black_boundary = True
                    elif neighbor == WHITE:
                        white_boundary = True
        
        # Determine ownership
        if black_boundary and white_boundary:
            # Territory is shared or not owned by anyone
            return (NONE, set())
        elif black_boundary:
            return (BLACK, set(territory_points))
        elif white_boundary:
            return (WHITE, set(territory_points))
        else:
            # No boundary stones - this shouldn't happen on a valid board
            # but if it does, it's NONE territory
            return (NONE, set(territory_points))

    def territories(self):
        # Calculate territories for all players
        black_territory = set()
        white_territory = set()
        none_territory = set()
        
        # Find all connected empty regions
        visited = set()
        
        for y in range(self.height):
            for x in range(self.width):
                if (x, y) not in visited and self.board[y][x] == NONE:
                    # Found an unvisited empty point, find its territory
                    territory_points, owner = self._find_territory_region(x, y)
                    
                    if owner == BLACK:
                        black_territory.update(territory_points)
                    elif owner == WHITE:
                        white_territory.update(territory_points)
                    else:
                        none_territory.update(territory_points)
                    
                    visited.update(territory_points)
        
        return {BLACK: black_territory, WHITE: white_territory, NONE: none_territory}

    def _find_territory_region(self, start_x, start_y):
        """Find all connected empty intersections and determine ownership."""
        visited = set()
        queue = deque([(start_x, start_y)])
        visited.add((start_x, start_y))
        
        territory_points = []
        
        while queue:
            x, y = queue.popleft()
            territory_points.append((x, y))
            
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = x + dx, y + dy
                
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    if (nx, ny) not in visited:
                        neighbor = self.board[ny][nx]
                        if neighbor == NONE:
                            visited.add((nx, ny))
                            queue.append((nx, ny))
        
        # Determine ownership by checking boundary stones
        black_boundary = False
        white_boundary = False
        
        for x, y in territory_points:
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = x + dx, y + dy
                
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    neighbor = self.board[ny][nx]
                    if neighbor == BLACK:
                        black_boundary = True
                    elif neighbor == WHITE:
                        white_boundary = True
        
        if black_boundary and white_boundary:
            return (territory_points, NONE)
        elif black_boundary:
            return (territory_points, BLACK)
        elif white_boundary:
            return (territory_points, WHITE)
        else:
            return (territory_points, NONE)