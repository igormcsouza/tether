class ConnectGame:
    def __init__(self, board):
        # Parse the board into a 2D grid
        # Each row is shifted by one space, so we need to handle that
        self.rows = []
        for line in board.strip().split('\n'):
            # Remove leading spaces and split
            # The indentation is one space per row
            stripped = line.strip()
            if stripped:
                # Split by space to get individual cells
                cells = stripped.split()
                self.rows.append(cells)
        
        self.height = len(self.rows)
        self.width = len(self.rows[0]) if self.rows else 0
    
    def get_winner(self):
        if not self.rows:
            return ""
        
        # Check if X wins (left to right)
        if self._check_x_win():
            return "X"
        
        # Check if O wins (top to bottom)
        if self._check_o_win():
            return "O"
        
        return ""
    
    def _get_neighbors(self, row, col):
        """Get valid neighboring cells in hexagonal grid."""
        neighbors = []
        # In hex grid with this layout, neighbors are:
        # (row-1, col-1), (row-1, col), (row, col-1), (row, col+1), (row+1, col), (row+1, col+1)
        # But we need to be careful about bounds
        directions = [(-1, -1), (-1, 0), (0, -1), (0, 1), (1, 0), (1, 1)]
        for dr, dc in directions:
            nr, nc = row + dr, col + dc
            if 0 <= nr < self.height and 0 <= nc < len(self.rows[nr]):
                neighbors.append((nr, nc))
        return neighbors
    
    def _check_x_win(self):
        """Check if X connects from left to right."""
        # X wins by connecting from left edge to right edge
        # Find all X cells on the left edge (column 0)
        start_cells = []
        for row in range(self.height):
            if self.rows[row] and self.rows[row][0] == 'X':
                start_cells.append((row, 0))
        
        if not start_cells:
            return False
        
        # BFS from all starting cells
        visited = set()
        queue = list(start_cells)
        
        while queue:
            row, col = queue.pop(0)
            if (row, col) in visited:
                continue
            visited.add((row, col))
            
            # Check if we reached the right edge
            if col == len(self.rows[row]) - 1:
                return True
            
            # Add neighbors
            for nr, nc in self._get_neighbors(row, col):
                if (nr, nc) not in visited and self.rows[nr][nc] == 'X':
                    queue.append((nr, nc))
        
        return False
    
    def _check_o_win(self):
        """Check if O connects from top to bottom."""
        # O wins by connecting from top edge to bottom edge
        # Find all O cells on the top edge (row 0)
        start_cells = []
        for col in range(len(self.rows[0])):
            if self.rows[0][col] == 'O':
                start_cells.append((0, col))
        
        if not start_cells:
            return False
        
        # BFS from all starting cells
        visited = set()
        queue = list(start_cells)
        
        while queue:
            row, col = queue.pop(0)
            if (row, col) in visited:
                continue
            visited.add((row, col))
            
            # Check if we reached the bottom edge
            if row == self.height - 1:
                return True
            
            # Add neighbors
            for nr, nc in self._get_neighbors(row, col):
                if (nr, nc) not in visited and self.rows[nr][nc] == 'O':
                    queue.append((nr, nc))
        
        return False