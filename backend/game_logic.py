import numpy as np
import random

class Connect4Game:
    def __init__(self):
        self.rows = 6
        self.columns = 7
        self.board = np.zeros((self.rows, self.columns), dtype=np.int8)
        self.current_player = 1
        self.winner = None
        self.game_over = False
        self.blocked_cells = []  # List to store blocked cell coordinates
    
    def reset(self):
        self.board = np.zeros((self.rows, self.columns), dtype=np.int8)
        self.current_player = 1
        self.winner = None
        self.game_over = False
        self.blocked_cells = []
        
    def block_random_cells(self):
        """Block 2 random cells in the board that are not already blocked."""
        # Get all valid positions (not blocked and empty)
        valid_positions = []
        for row in range(self.rows):
            for col in range(self.columns):
                if self.board[row][col] == 0 and (row, col) not in self.blocked_cells:
                    valid_positions.append((row, col))
        
        # If we have less than 2 valid positions, return False
        if len(valid_positions) < 2:
            return False
            
        # Randomly select 2 positions to block
        selected_positions = random.sample(valid_positions, 2)
        
        # Block the selected positions
        for row, col in selected_positions:
            self.board[row][col] = -1  # Use -1 to represent blocked cells
            self.blocked_cells.append((row, col))
            
        return True
    
    def is_valid_move(self, column):
        """Check if a move is valid.
        A move is valid if:
        1. The column is within bounds
        2. There is at least one empty cell in the column (not all cells are occupied by players or blocked)
        """
        # First check if column is within bounds
        if not (0 <= column < self.columns):
            return False
        
        # Check if there's at least one empty cell in the column
        for row in range(self.rows):
            if self.board[row][column] == 0:
                return True
            
        # If we reach here, the column is either full or all cells are blocked
        return False
    
    def get_valid_moves(self):
        return [col for col in range(self.columns) if self.is_valid_move(col)]
    
    def make_move(self, column):
        if self.game_over or not self.is_valid_move(column):
            return False
            
        # Find the lowest empty row in the selected column
        for row in range(self.rows-1, -1, -1):
            # Skip blocked cells
            if self.board[row][column] == -1:
                continue
            
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
            "is_new_game": self.is_new_game(),
            "blocked_cells": self.blocked_cells
        }
