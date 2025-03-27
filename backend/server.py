import os
import uuid
import json
import asyncio
import logging
from typing import Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from game_logic import Connect4Game
from agent_loader import load_agent, get_agent_move

# Cấu hình logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Path to the trained model
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models/connect4_ppo_agent.zip")

# Dict to store active games
games: Dict[str, Dict] = {}

# Dict to store active connections
connections: Dict[str, List[WebSocket]] = {}

# Ensure models directory exists
os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)

# Load the AI agent once at startup if it exists
ai_agent = None
try:
    logger.info(f"Attempting to load AI agent from {MODEL_PATH}")
    ai_agent = load_agent(MODEL_PATH)
    logger.info(f"AI agent loaded successfully")
except Exception as e:
    logger.error(f"Error loading AI agent: {e}")
    logger.info("A fallback agent will be used for AI gameplay")

# WebSocket connection manager
class ConnectionManager:
    async def connect(self, websocket: WebSocket, game_id: str):
        await websocket.accept()
        if game_id not in connections:
            connections[game_id] = []
        connections[game_id].append(websocket)
        
        # Create game if it doesn't exist
        if game_id not in games:
            logger.info(f"Creating new game with ID: {game_id}")
            games[game_id] = {
                "game": Connect4Game(),
                "player_count": 0,
                "agent_mode": False
            }
            
        # Assign player number
        player_num = 0
        if games[game_id]["player_count"] < 2:
            games[game_id]["player_count"] += 1
            player_num = games[game_id]["player_count"]
            logger.info(f"Player {player_num} joined game {game_id}")
            
        # Send initial game state
        game_state = games[game_id]["game"].get_state()
        logger.info(f"Sending initial state to player {player_num}: {game_state}")
        await self.send_personal_message(
            {
                "type": "game_state",
                "state": game_state,
                "your_player": player_num,
                "agent_mode": games[game_id]["agent_mode"]
            },
            websocket
        )
        
        # Notify others
        await self.broadcast(
            {
                "type": "player_joined",
                "player": player_num
            },
            game_id,
            websocket
        )
        
        return player_num
    
    async def disconnect(self, websocket: WebSocket, game_id: str, player_num: int):
        if game_id in connections and websocket in connections[game_id]:
            connections[game_id].remove(websocket)
            logger.info(f"Player {player_num} disconnected from game {game_id}")
            
            # If no connections left, remove the game
            if not connections[game_id]:
                if game_id in games:
                    del games[game_id]
                del connections[game_id]
                logger.info(f"Removed game {game_id} as no players remaining")
            else:
                # Notify others
                await self.broadcast(
                    {
                        "type": "player_left",
                        "player": player_num
                    },
                    game_id,
                    None
                )
    
    async def send_personal_message(self, message, websocket: WebSocket):
        await websocket.send_json(message)
    
    async def broadcast(self, message, game_id: str, exclude: Optional[WebSocket] = None):
        if game_id in connections:
            for connection in connections[game_id]:
                if connection != exclude:
                    await connection.send_json(message)

# Initialize connection manager
manager = ConnectionManager()

@app.websocket("/ws/{game_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str):
    player_num = await manager.connect(websocket, game_id)
    
    try:
        while True:
            data = await websocket.receive_json()
            logger.info(f"Received from player {player_num} in game {game_id}: {data}")
            
            if data["type"] == "make_move":
                column = data["column"]
                logger.info(f"Player {player_num} attempting move in column {column}")
                
                # Check if it's player's turn
                if game_id not in games:
                    logger.error(f"Game ID {game_id} not found")
                    continue
                    
                game = games[game_id]["game"]
                logger.info(f"Current game state: player={game.current_player}, game_over={game.game_over}")
                
                # In agent mode, player 1 can always make a move
                is_valid_player = (game.current_player == player_num) or \
                                 (games[game_id]["agent_mode"] and player_num == 1 and game.current_player == 1)
                
                if is_valid_player and player_num > 0 and not game.game_over:
                    logger.info(f"Valid move attempt from player {player_num}")
                    
                    # Make the move
                    if game.make_move(column):
                        logger.info(f"Move successful, new state: {game.get_state()}")
                        # Send updated game state to all players
                        await manager.broadcast(
                            {
                                "type": "game_update",
                                "state": game.get_state()
                            },
                            game_id
                        )
                        
                        # If playing against AI and it's AI's turn
                        if (games[game_id]["agent_mode"] and 
                            not game.game_over and 
                            game.current_player == 2):
                            
                            logger.info("AI's turn, calculating move...")
                            # Add a small delay to make it seem like the AI is thinking
                            await asyncio.sleep(0.5)
                            
                            # Get AI move
                            valid_moves = game.get_valid_moves()
                            logger.info(f"Valid moves for AI: {valid_moves}")
                            
                            if valid_moves and ai_agent:
                                try:
                                    ai_column = get_agent_move(ai_agent, game.get_board(), valid_moves)
                                    logger.info(f"AI chose column {ai_column}")
                                    
                                    # Make AI move
                                    if game.make_move(ai_column):
                                        logger.info(f"AI move successful, new state: {game.get_state()}")
                                        await manager.broadcast(
                                            {
                                                "type": "game_update",
                                                "state": game.get_state(),
                                                "ai_move": ai_column
                                            },
                                            game_id
                                        )
                                except Exception as e:
                                    logger.error(f"Error during AI move: {e}")
                    else:
                        logger.warning(f"Invalid move attempt by player {player_num} in column {column}")
                else:
                    if player_num <= 0:
                        logger.warning(f"Spectator tried to make a move")
                    else:
                        logger.warning(f"Not player {player_num}'s turn. Current player: {game.current_player}")
            
            elif data["type"] == "start_agent_game":
                # Set up game with AI
                if game_id in games:
                    logger.info(f"Starting AI game mode for game {game_id}")
                    games[game_id]["agent_mode"] = True
                    games[game_id]["game"].reset()
                    
                    # Send updated game state with agent mode flag
                    await manager.broadcast(
                        {
                            "type": "game_state",  # Use game_state instead of game_update
                            "state": games[game_id]["game"].get_state(),
                            "your_player": player_num,
                            "agent_mode": True
                        },
                        game_id
                    )
                    logger.info("Sent updated state with agent_mode=True")
            
            elif data["type"] == "reset_game":
                # Reset the game
                if game_id in games:
                    logger.info(f"Resetting game {game_id}")
                    games[game_id]["game"].reset()
                    
                    # Preserve agent mode when resetting
                    agent_mode = games[game_id]["agent_mode"]
                    
                    # Send updated game state
                    await manager.broadcast(
                        {
                            "type": "game_state",  # Use game_state to include agent_mode
                            "state": games[game_id]["game"].get_state(),
                            "your_player": player_num,
                            "agent_mode": agent_mode
                        },
                        game_id
                    )
    
    except WebSocketDisconnect:
        await manager.disconnect(websocket, game_id, player_num)
    except Exception as e:
        logger.error(f"Error in websocket handler: {e}")
        await manager.disconnect(websocket, game_id, player_num)

# REST API for game operations
@app.post("/api/create-game")
async def create_game():
    game_id = str(uuid.uuid4())
    games[game_id] = {
        "game": Connect4Game(),
        "player_count": 0,
        "agent_mode": False
    }
    logger.info(f"Created new game via API: {game_id}")
    return {"game_id": game_id}

@app.get("/api/game/{game_id}/state")
async def get_game_state(game_id: str):
    if game_id not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    
    return games[game_id]["game"].get_state()

@app.post("/api/game/{game_id}/move")
async def make_move(game_id: str, move: dict):
    if game_id not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    
    column = move.get("column")
    player = move.get("player")
    
    if not isinstance(column, int) or not isinstance(player, int):
        raise HTTPException(status_code=400, detail="Invalid move parameters")
    
    game = games[game_id]["game"]
    
    # Verify it's correct player's turn
    if game.current_player != player:
        raise HTTPException(status_code=400, detail="Not your turn")
    
    # Make move
    if game.make_move(column):
        # Broadcast update via WebSocket if connections exist
        if game_id in connections:
            await manager.broadcast(
                {
                    "type": "game_update",
                    "state": game.get_state()
                },
                game_id
            )
        
        return {
            "success": True, 
            "state": game.get_state()
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid move")

