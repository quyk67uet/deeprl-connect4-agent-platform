# Connect4 AI Championship Platform

## Championship Demo

![Championship Dashboard](https://drive.google.com/uc?export=view&id=1AO4eKISzMw9VEgmRk4oqwjiEV5de0K_d)

### Game in Progress
![Game in Progress](https://drive.google.com/uc?export=view&id=1G4Cax2mrmRkMhU9m8ZTXBp0hYGpr-h1v)

### Championship Menu
![Game in Progress](https://drive.google.com/file/d/1DUjeOcupxPepgO8YJtEcrQ_bMXpSSkDz)

### Championship Register
![Game in Progress](https://drive.google.com/file/d/1t1frSr1piI2SQp0VdBmkNHmcHjrKh4Br)

## Overview

This repository contains a complete platform for developing, training, and competing with Connect4 AI agents. The platform consists of two main components:

1. **Deep Reinforcement Learning Agent**: A powerful Connect4 AI created using PPO (Proximal Policy Optimization) that learns optimal gameplay strategies.
2. **Championship Platform**: A full-featured competition system that allows multiple AI agents to compete in a tournament-style format.

## Deep Reinforcement Learning Agent

### Agent Architecture

The AI agent is built using state-of-the-art reinforcement learning techniques:

- **Neural Network**: A CNN (Convolutional Neural Network) that takes the game board as input and predicts the best move.
- **Learning Algorithm**: PPO (Proximal Policy Optimization) from Stable-Baselines3, which efficiently trains the agent through self-play.
- **Feature Extraction**: Custom CNN architecture to recognize important board patterns and strategic positions.

### Training Process

The agent is trained through a reward system that reinforces good moves:
- +1 for winning a game
- -10 for invalid moves
- -1 for moves that allow the opponent to win immediately 
- Small positive reward (1/42) for valid moves that keep the game going

This reward structure teaches the agent to:
1. Avoid invalid moves
2. Look ahead to prevent opponent wins
3. Build towards its own victory
4. Make progress when no immediate win is possible

Training involves playing thousands of matches against different opponents (random moves, rule-based AI, and self-play) to develop a robust strategy.

### Agent Capabilities

The trained agent demonstrates strong gameplay with the ability to:
- Recognize and build winning patterns (horizontal, vertical, diagonal)
- Block opponent winning moves
- Set up "traps" with multiple win conditions
- Adapt to different opponent strategies

## Championship Platform

### System Architecture

The platform uses a distributed architecture:
- **Backend**: FastAPI-based server that manages games, matches, and tournament logic
- **Frontend**: React-based dashboard for visualizing games and leaderboards
- **WebSocket Communication**: Real-time updates between AI agents and viewers

### Key Features

1. **Full Tournament Management**:
   - Support for up to 20 teams in a round-robin tournament
   - Automated scheduling and execution of matches
   - Parallel match execution (up to 5 simultaneous matches)

2. **Robust Game Rules**:
   - Standard Connect4 rules (7×6 board, 4-in-a-row to win)
   - Time controls for both turns and overall match duration
   - Handling of timeouts, invalid moves, and other edge cases

3. **Comprehensive Scoring System**:
   - Point-based scoring (1 point for win, 0.5 for draw, 0 for loss)
   - Tiebreakers based on head-to-head results and time usage
   - Complete W/D/L statistics tracking

4. **Real-time Visualization**:
   - Live game board visualization
   - Real-time leaderboard updates
   - Spectator mode for viewing ongoing matches

5. **Fault Tolerance**:
   - Automatic handling of AI crashes or timeouts
   - Match restart capabilities for technical issues
   - Consistent point allocation even in error scenarios

### Championship Format

The championship follows a round-robin format where:
- Each team plays against every other team
- Each match consists of 4 games (alternating first-move advantage)
- Points are awarded per game, with total match points determining the winner
- Teams have a time bank for each match (typically 4 minutes per team)
- Final standings are determined by total points across all matches

## Getting Started

### Prerequisites

- Python 3.8+
- Node.js 14+
- Redis (for state persistence)

### Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/connect4-championship.git
cd connect4-championship
```

2. Install backend dependencies:
```bash
cd backend
pip install -r requirements.txt
```

3. Install frontend dependencies:
```bash
cd frontend
npm install
```

### Running the Platform

1. Start the backend server:
```bash
cd backend
python server.py
```

2. Start the frontend:
```bash
cd frontend
npm run dev
```

3. Access the dashboard at http://localhost:3000

### Training Your Own Agent

To train your own Connect4 agent, use the provided Jupyter notebook:
```bash
jupyter notebook notebook/deep-reinforcement-learning-connect4-agent.ipynb
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Thanks to the Stable-Baselines3 team for their excellent reinforcement learning library
- Inspired by the Kaggle Connect X competition 
