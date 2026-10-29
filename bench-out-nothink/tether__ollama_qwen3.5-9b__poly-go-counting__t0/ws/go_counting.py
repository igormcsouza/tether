WHITE = "W"
BLACK = "B"
NONE = ""


class Board:
    """Count territories of each player in a Go game

    Args:
        board (list[str]): A two-dimensional Go board
    """
    def __init__(self, board):
        self.board = board
        self.rows = len(board)
        self.cols = len(board[0]) if self.rows > 0 else 0

    def territory(self, x, y):
        """Find the owner and the territories given a coordinate on
           the board

        Args:
            x (int): Column on the board
            y (int): Row on the board

        Returns:
            (str, set): A tuple, the first element being the owner
                        of that area.  One of "W", "B", "".  The
                        second being a set of coordinates, representing
                        the owner's territories.
        """
        # Validate coordinates
        if x < 0 or x >= self.cols or y < 0 or y >= self.rows:
            raise ValueError('Invalid coordinate')

        # Get the stone at the given position
        stone_at_pos = self.board[y][x]

        # If it's a stone, it's not territory
        if stone_at_pos in (WHITE, BLACK):
            return (stone_at_pos, set())

        # Find the territory by exploring connected empty spaces
        # and checking all neighbors
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
                if 0 <= nx < self.cols and 0 <= ny < self.rows:
                    neighbor = self.board[ny][nx]
                    if neighbor not in (WHITE, BLACK) and (nx, ny) not in visited:
                        stack.append((nx, ny))
        
        # Now determine ownership by checking all neighbors of the territory
        # If all neighbors are of one player, that player owns the territory
        # If neighbors are mixed or include empty, it's unowned
        
        owners = set()
        for (tx, ty) in territory:
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = tx + dx, ty + dy
                if 0 <= nx < self.cols and 0 <= ny < self.rows:
                    neighbor = self.board[ny][nx]
                    if neighbor in (WHITE, BLACK):
                        owners.add(neighbor)
        
        if len(owners) == 0:
            # Territory is not owned by anyone (surrounded by empty or off-board)
            return (NONE, territory)
        elif len(owners) == 1:
            return (list(owners)[0], territory)
        else:
            # Mixed ownership - not territory
            return (NONE, set())

    def territories(self):
        """Find the owners and the territories of the whole board

        Args:
            none

        Returns:
            dict(str, set): A dictionary whose key being the owner
                        , i.e. "W", "B", "".  The value being a set
                        of coordinates owned by the owner.
        """
        territories = {WHITE: set(), BLACK: set(), NONE: set()}
        
        # Track which empty cells we've already processed
        processed = set()
        
        for y in range(self.rows):
            for x in range(self.cols):
                if self.board[y][x] not in (WHITE, BLACK) and (x, y) not in processed:
                    stone, territory = self.territory(x, y)
                    if territory:
                        for (tx, ty) in territory:
                            processed.add((tx, ty))
                        territories[stone].update(territory)
        
        return territories