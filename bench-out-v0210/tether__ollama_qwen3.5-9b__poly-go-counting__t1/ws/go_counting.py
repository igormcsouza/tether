from collections import deque

WHITE = "W"
BLACK = "B"
NONE = " "


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
        stone = self.board[y][x]
        
        if stone != NONE:
            # If there's a stone, it's not territory
            return (NONE, set())
        
        # Find the territory using flood fill
        # We need to find all connected empty spaces and determine who owns them
        visited = set()
        territory = set()
        stack = [(x, y)]
        
        while stack:
            cx, cy = stack.pop()
            if (cx, cy) in visited:
                continue
            visited.add((cx, cy))
            territory.add((cx, cy))
            
            # Check all 4 neighbors
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    neighbor = self.board[ny][nx]
                    if neighbor == NONE and (nx, ny) not in visited:
                        stack.append((nx, ny))
        
        # Now determine who owns this territory
        # A territory belongs to a player if all adjacent stones are that player's
        # and there are no adjacent stones of the other player
        
        adjacent_stones = set()
        for (cx, cy) in territory:
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    adjacent_stones.add(self.board[ny][nx])
        
        # Check if there are any stones
        if adjacent_stones == {NONE}:
            # No stones adjacent, this is not territory for anyone
            return (NONE, set())
        
        # Check if all adjacent stones are of one color
        if adjacent_stones == {BLACK}:
            return (BLACK, territory)
        elif adjacent_stones == {WHITE}:
            return (WHITE, territory)
        else:
            # Mixed stones, not territory
            return (NONE, set())

    def territories(self):
        """Calculate the territory for each player."""
        territories = {BLACK: set(), WHITE: set(), NONE: set()}
        
        # Track which empty spaces we've already assigned
        visited = set()
        
        for y in range(self.height):
            for x in range(self.width):
                if self.board[y][x] == NONE and (x, y) not in visited:
                    # Find the territory connected to this empty space
                    stone, territory = self.territory(x, y)
                    if territory:
                        for (tx, ty) in territory:
                            visited.add((tx, ty))
                        territories[stone].update(territory)
        
        return territories