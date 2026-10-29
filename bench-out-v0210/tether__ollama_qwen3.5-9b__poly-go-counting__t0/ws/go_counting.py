from collections import deque


class Board:
    """Go board representation."""
    
    def __init__(self, board):
        """Initialize the board from a list of strings."""
        self.board = board
        self.height = len(board)
        self.width = len(board[0]) if self.height > 0 else 0
    
    def territory(self, x, y):
        """
        Determine the territory which includes a specified coordinate.
        
        Returns a tuple of (stone, territory) where:
        - stone is 'B', 'W', or ' ' (space)
        - territory is a set of (x, y) coordinates
        
        Raises ValueError if coordinates are invalid.
        """
        # Validate coordinates
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            raise ValueError('Invalid coordinate')
        
        # Check if the coordinate is valid (within board bounds)
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError('Invalid coordinate')
        
        # Start BFS from the given coordinate
        start_stone = self.board[y][x]
        
        # If the starting position is a stone, it's not territory
        if start_stone != ' ':
            return (' ', set())
        
        # BFS to find all connected empty spaces
        visited = set()
        queue = deque([(x, y)])
        visited.add((x, y))
        
        # Find all connected empty spaces
        while queue:
            cx, cy = queue.popleft()
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = cx + dx, cy + dy
                if (nx, ny) not in visited and 0 <= nx < self.width and 0 <= ny < self.height:
                    if self.board[ny][nx] == ' ':
                        visited.add((nx, ny))
                        queue.append((nx, ny))
        
        # Now determine which player owns this territory
        # A territory belongs to a player if all adjacent stones are that player's
        # and all empty spaces in the territory are connected
        
        # Find all stones adjacent to the territory
        adjacent_stones = set()
        for (tx, ty) in visited:
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = tx + dx, ty + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    if self.board[ny][nx] != ' ':
                        adjacent_stones.add(self.board[ny][nx])
        
        # Determine the owner
        if len(adjacent_stones) == 0:
            # No stones adjacent - this is shared territory (NONE)
            owner = ' '
        elif len(adjacent_stones) == 1:
            # All adjacent stones are the same player
            owner = list(adjacent_stones)[0]
        else:
            # Multiple different players adjacent - no territory
            owner = ' '
        
        return (owner, visited)
    
    def territories(self):
        """
        Calculate the territory of each player.
        
        Returns a dict with keys 'B', 'W', ' ' and values as sets of coordinates.
        """
        BLACK = 'B'
        WHITE = 'W'
        NONE = ' '
        
        # First, find all empty spaces and group them into connected components
        empty_spaces = set()
        for y in range(self.height):
            for x in range(self.width):
                if self.board[y][x] == ' ':
                    empty_spaces.add((x, y))
        
        # Group empty spaces into connected components
        components = []
        visited = set()
        
        for (x, y) in empty_spaces:
            if (x, y) in visited:
                continue
            
            # BFS to find this component
            component = set()
            queue = deque([(x, y)])
            visited.add((x, y))
            
            while queue:
                cx, cy = queue.popleft()
                component.add((cx, cy))
                for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                    nx, ny = cx + dx, cy + dy
                    if (nx, ny) not in visited and 0 <= nx < self.width and 0 <= ny < self.height:
                        if self.board[ny][nx] == ' ':
                            visited.add((nx, ny))
                            queue.append((nx, ny))
            
            components.append(component)
        
        # For each component, determine its owner
        territories = {BLACK: set(), WHITE: set(), NONE: set()}
        
        for component in components:
            # Find all stones adjacent to this component
            adjacent_stones = set()
            for (tx, ty) in component:
                for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                    nx, ny = tx + dx, ty + dy
                    if 0 <= nx < self.width and 0 <= ny < self.height:
                        if self.board[ny][nx] != ' ':
                            adjacent_stones.add(self.board[ny][nx])
            
            # Determine the owner
            if len(adjacent_stones) == 0:
                # No stones adjacent - shared territory
                owner = ' '
            elif len(adjacent_stones) == 1:
                owner = list(adjacent_stones)[0]
            else:
                owner = ' '
            
            territories[owner].update(component)
        
        return territories


# Constants
WHITE = 'W'
BLACK = 'B'
NONE = ' '