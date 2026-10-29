class ConnectGame:
    def __init__(self, board):
        """
        Parse the board string into a 2D grid.
        The board is given with each row indented by one more space than the previous.
        """
        self.grid = []
        lines = board.strip().split('\n')
        
        for line in lines:
            # Remove leading spaces and split by spaces
            # Each cell is separated by a space
            cells = line.strip().split()
            self.grid.append(cells)
    
    def get_winner(self):
        """
        Determine the winner of the game.
        - 'X' wins by connecting left to right
        - 'O' wins by connecting top to bottom
        - '' if no winner
        """
        if not self.grid:
            return ""
        
        rows = len(self.grid)
        cols = len(self.grid[0]) if self.grid else 0
        
        # Check if X wins (left to right)
        if self._has_path('X', cols):
            return "X"
        
        # Check if O wins (top to bottom)
        if self._has_path('O', rows):
            return "O"
        
        return ""
    
    def _has_path(self, player, direction):
        """
        Check if there's a path for the player.
        direction: number of cells in the direction to connect to
        - For X (left to right): need path from col 0 to col (cols-1)
        - For O (top to bottom): need path from row 0 to row (rows-1)
        """
        rows = len(self.grid)
        cols = len(self.grid[0]) if self.grid else 0
        
        if rows == 0 or cols == 0:
            return False
        
        # For X: left to right - need to connect from any cell in col 0 to any cell in col (cols-1)
        # For O: top to bottom - need to connect from any cell in row 0 to any cell in row (rows-1)
        
        if direction == cols:  # X wins (left to right)
            # Start from all cells in the leftmost column
            visited = set()
            queue = []
            
            for r in range(rows):
                if self.grid[r][0] == player:
                    queue.append((r, 0))
                    visited.add((r, 0))
            
            if not queue:
                return False
            
            while queue:
                r, c = queue.pop(0)
                
                # Check if we reached the rightmost column
                if c == cols - 1:
                    return True
                
                # Get neighbors in hex grid
                # For a cell at (r, c), neighbors are:
                # (r-1, c-1), (r-1, c)
                # (r, c-1), (r, c+1)
                # (r+1, c), (r+1, c+1)
                neighbors = [
                    (r - 1, c - 1), (r - 1, c),
                    (r, c - 1), (r, c + 1),
                    (r + 1, c), (r + 1, c + 1)
                ]
                
                for nr, nc in neighbors:
                    if 0 <= nr < rows and 0 <= nc < cols:
                        if self.grid[nr][nc] == player and (nr, nc) not in visited:
                            visited.add((nr, nc))
                            queue.append((nr, nc))
            
            return False
        
        else:  # O wins (top to bottom)
            # Start from all cells in the top row
            visited = set()
            queue = []
            
            for c in range(cols):
                if self.grid[0][c] == player:
                    queue.append((0, c))
                    visited.add((0, c))
            
            if not queue:
                return False
            
            while queue:
                r, c = queue.pop(0)
                
                # Check if we reached the bottom row
                if r == rows - 1:
                    return True
                
                # Get neighbors in hex grid
                neighbors = [
                    (r - 1, c - 1), (r - 1, c),
                    (r, c - 1), (r, c + 1),
                    (r + 1, c), (r + 1, c + 1)
                ]
                
                for nr, nc in neighbors:
                    if 0 <= nr < rows and 0 <= nc < cols:
                        if self.grid[nr][nc] == player and (nr, nc) not in visited:
                            visited.add((nr, nc))
                            queue.append((nr, nc))
            
            return False