class ConnectGame:
    def __init__(self, board):
        self.board = self._parse_board(board)
    
    def _parse_board(self, board):
        """Parse the board string into a 2D list."""
        lines = board.strip().split('\n')
        parsed = []
        for line in lines:
            # Remove leading spaces (each row is indented by one more space than previous)
            # The indentation represents the hexagonal grid structure
            stripped = line.lstrip()
            parsed.append(list(stripped))
        return parsed
    
    def get_winner(self):
        """Determine the winner of the game."""
        if not self.board:
            return ""
        
        rows = len(self.board)
        if rows == 0:
            return ""
        
        cols = len(self.board[0])
        if cols == 0:
            return ""
        
        # Check if board is 1x1
        if rows == 1 and cols == 1:
            if self.board[0][0] == 'X':
                return 'X'
            elif self.board[0][0] == 'O':
                return 'O'
        
        # Check for X winner (left to right)
        x_winner = self._check_x_winner()
        if x_winner:
            return 'X'
        
        # Check for O winner (top to bottom)
        o_winner = self._check_o_winner()
        if o_winner:
            return 'O'
        
        return ""
    
    def _check_x_winner(self):
        """Check if X has connected from left to right."""
        rows = len(self.board)
        if rows == 0:
            return False
        
        cols = len(self.board[0])
        if cols == 0:
            return False
        
        # For X, we need to find a path from left edge to right edge
        # Use BFS to find connected components
        
        # Start from all X cells on the left edge (column 0)
        visited = set()
        queue = []
        
        for r in range(rows):
            if cols > 0 and self.board[r][0] == 'X':
                queue.append((r, 0))
                visited.add((r, 0))
        
        if not queue:
            return False
        
        # BFS to find if any X reaches the right edge
        while queue:
            r, c = queue.pop(0)
            
            # Check if we reached the right edge
            if c == cols - 1:
                return True
            
            # Get valid neighbors for hexagonal grid
            # Neighbors: (r-1, c-1), (r-1, c), (r, c-1), (r, c+1), (r+1, c-1), (r+1, c)
            neighbors = [
                (r - 1, c - 1),
                (r - 1, c),
                (r, c - 1),
                (r, c + 1),
                (r + 1, c - 1),
                (r + 1, c),
            ]
            
            for nr, nc in neighbors:
                if 0 <= nr < rows and 0 <= nc < len(self.board[nr]):
                    if self.board[nr][nc] == 'X' and (nr, nc) not in visited:
                        visited.add((nr, nc))
                        queue.append((nr, nc))
        
        return False
    
    def _check_o_winner(self):
        """Check if O has connected from top to bottom."""
        rows = len(self.board)
        if rows == 0:
            return False
        
        cols = len(self.board[0])
        if cols == 0:
            return False
        
        # For O, we need to find a path from top edge to bottom edge
        # Start from all O cells on the top edge (row 0)
        visited = set()
        queue = []
        
        for c in range(len(self.board[0])):
            if self.board[0][c] == 'O':
                queue.append((0, c))
                visited.add((0, c))
        
        if not queue:
            return False
        
        # BFS to find if any O reaches the bottom edge
        while queue:
            r, c = queue.pop(0)
            
            # Check if we reached the bottom edge
            if r == rows - 1:
                return True
            
            # Get valid neighbors for hexagonal grid
            neighbors = [
                (r - 1, c - 1),
                (r - 1, c),
                (r, c - 1),
                (r, c + 1),
                (r + 1, c - 1),
                (r + 1, c),
            ]
            
            for nr, nc in neighbors:
                if 0 <= nr < rows and 0 <= nc < len(self.board[nr]):
                    if self.board[nr][nc] == 'O' and (nr, nc) not in visited:
                        visited.add((nr, nc))
                        queue.append((nr, nc))
        
        return False