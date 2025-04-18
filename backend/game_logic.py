import numpy as np

class Connect4Game:
    def __init__(self):
        self.rows = 6
        self.columns = 7
        self.board = np.zeros((self.rows, self.columns), dtype=np.int8)
        self.current_player = 1
        self.winner = None
        self.game_over = False
    
    def reset(self):
        self.board = np.zeros((self.rows, self.columns), dtype=np.int8)
        self.current_player = 1
        self.winner = None
        self.game_over = False
        
    def is_valid_move(self, column):
        return 0 <= column < self.columns and self.board[0][column] == 0
    
    def get_valid_moves(self):
        return [col for col in range(self.columns) if self.is_valid_move(col)]
    
    def make_move(self, column):
        if self.game_over or not self.is_valid_move(column):
            return False
            
        # Find the lowest empty row in the selected column
        for row in range(self.rows-1, -1, -1):
            if self.board[row][column] == 0:
                self.board[row][column] = self.current_player
                break
                
        # Check for a win
        if self.check_win(self.current_player):
            self.winner = self.current_player
            self.game_over = True
        # Check for a draw
        elif len(self.get_valid_moves()) == 0:
            self.game_over = True
        else:
            # Switch players
            self.current_player = 3 - self.current_player  # 1 -> 2, 2 -> 1
            
        return True
    
    def check_win(self, player):
        # Check horizontal
        for row in range(self.rows):
            for col in range(self.columns - 3):
                if (self.board[row][col] == player and
                    self.board[row][col+1] == player and
                    self.board[row][col+2] == player and
                    self.board[row][col+3] == player):
                    return True
                    
        # Check vertical
        for row in range(self.rows - 3):
            for col in range(self.columns):
                if (self.board[row][col] == player and
                    self.board[row+1][col] == player and
                    self.board[row+2][col] == player and
                    self.board[row+3][col] == player):
                    return True
                    
        # Check diagonal (down-right)
        for row in range(self.rows - 3):
            for col in range(self.columns - 3):
                if (self.board[row][col] == player and
                    self.board[row+1][col+1] == player and
                    self.board[row+2][col+2] == player and
                    self.board[row+3][col+3] == player):
                    return True
                    
        # Check diagonal (up-right)
        for row in range(3, self.rows):
            for col in range(self.columns - 3):
                if (self.board[row][col] == player and
                    self.board[row-1][col+1] == player and
                    self.board[row-2][col+2] == player and
                    self.board[row-3][col+3] == player):
                    return True
                    
        return False
    
    def get_board(self):
        return self.board.tolist()
    
    def is_new_game(self):
        """Check if the game is new by counting non-zero cells in the board."""
        return sum(1 for row in self.board for cell in row if cell != 0) <= 1
    
    def get_state(self):
        return {
            "board": self.get_board(),
            "current_player": self.current_player,
            "game_over": self.game_over,
            "winner": self.winner,
            "is_new_game": self.is_new_game()
        }
