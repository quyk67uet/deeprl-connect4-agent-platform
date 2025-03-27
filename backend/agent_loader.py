import os
import numpy as np
import warnings
import torch as th
import torch.nn as nn
import gymnasium as gym
from gymnasium import spaces
from stable_baselines3 import PPO
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
import random

# Suppress warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', category=FutureWarning)

# Neural network for predicting action values
class CustomCNN(BaseFeaturesExtractor):
    def __init__(self, observation_space: gym.spaces.Box, features_dim: int=128):
        super(CustomCNN, self).__init__(observation_space, features_dim)
        n_input_channels = observation_space.shape[0]
        self.cnn = nn.Sequential(
            nn.Conv2d(n_input_channels, 32, kernel_size=3, stride=1, padding=0),
            nn.ReLU(),
            nn.Conv2d(32, 64, kernel_size=3, stride=1, padding=0),
            nn.ReLU(),
            nn.Flatten(),
        )

        with th.no_grad():
            n_flatten = self.cnn(
                th.as_tensor(observation_space.sample()[None]).float()
            ).shape[1]

        self.linear = nn.Sequential(nn.Linear(n_flatten, features_dim), nn.ReLU())

    def forward(self, observations: th.Tensor) -> th.Tensor:
        return self.linear(self.cnn(observations))

# Class for modeling connect4 env for loading the model
class ConnectFourEnv(gym.Env):
    def __init__(self):
        self.rows = 6
        self.columns = 7
        self.action_space = spaces.Discrete(self.columns)
        self.observation_space = spaces.Box(low=0, high=2, 
                                         shape=(1, self.rows, self.columns), dtype=np.int8)
        self.board = np.zeros((self.rows, self.columns), dtype=np.int8)
        self.done = False
        self.current_player = 1  # 1 for player 1, 2 for player 2
    
    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.board = np.zeros((self.rows, self.columns), dtype=np.int8)
        self.done = False
        self.current_player = 1
        return self._get_observation(), {}
        
    def _get_observation(self):
        return self.board.reshape(1, self.rows, self.columns)
    
    def step(self, action):
        # Placeholder implementation to satisfy Gymnasium interface
        observation = self._get_observation()
        reward = 0
        terminated = False
        truncated = False
        info = {}
        return observation, reward, terminated, truncated, info

# Function to load the agent
def load_agent(model_path):
    global _loaded_model
    try:
        print(f"Attempting to load agent from {model_path}")
        if not os.path.exists(model_path):
            print(f"Model path not found: {model_path}")
            raise FileNotFoundError(f"Model path not found: {model_path}")
        if not os.access(model_path, os.R_OK):
            print(f"No read permissions for model: {model_path}")
            raise PermissionError(f"No read permissions for model: {model_path}")
        
        env = ConnectFourEnv()
        policy_kwargs = dict(features_extractor_class=CustomCNN)
        
        custom_objects = {
            "policy_kwargs": policy_kwargs  
        }
        
        print("Creating PPO model...")
        model = PPO.load(model_path, env=env, custom_objects=custom_objects)
        
        print("Model loaded successfully!")
        _loaded_model = model
        return model
    except Exception as e:
        print(f"Error loading agent: {e}")
        print("Using random agent fallback")
        return None

# Fallback agent that makes random moves
def get_random_move(board, valid_moves):
    """Get a random move from the valid moves."""
    if valid_moves:
        return random.choice(valid_moves)
    return 0  # Fallback to column 0 if no valid moves

# Global variable to store loaded model
_loaded_model = None

# Function to get agent's move
def get_agent_move(model, board, valid_moves):
    """Get a move from the agent for the current game state."""
    if model is None:
        print("Using random agent because model could not be loaded")
        return get_random_move(board, valid_moves)
        
    try:
        # Convert board to numpy array in correct shape
        board_array = np.array(board).reshape(1, 6, 7)
        
        # Get model prediction
        action, _ = model.predict(board_array)
        
        # Check if action is valid
        if action in valid_moves:
            return int(action)
        else:
            # Choose random valid move if model's choice is invalid
            print(f"Model predicted invalid action {action}, choosing random from {valid_moves}")
            return get_random_move(board, valid_moves)
    except Exception as e:
        print(f"Error in get_agent_move: {e}")
        return get_random_move(board, valid_moves)