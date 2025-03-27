import os
import uuid
import json
import asyncio
import logging
from typing import Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from game_logic import Connect4Game
from agent_loader import load_agent, get_agent_move

# logging config
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
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

# Dict to store AI battle games
ai_battles: Dict[str, Dict] = {}

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

# Make a move with external AI
async def make_external_ai_move(game_id: str, ai_url: str):
    if game_id not in games:
        return False
    
    game = games[game_id]["game"]
    if game.game_over:
        return False
    
    try:
        # Get current game state
        game_state = game.get_state()
        
        # Prepare data for external AI
        data = {
            "board": game_state["board"],
            "current_player": game_state["current_player"],
            "valid_moves": game.get_valid_moves()
        }
        
        # Make request to external AI
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(ai_url, json=data, timeout=5.0)
            
            if response.status_code == 200:
                ai_data = response.json()
                column = ai_data.get("move")
                
                if column is not None and game.is_valid_move(column):
                    return column
            
        # Fallback to random move if request fails
        import random
        valid_moves = game.get_valid_moves()
        if valid_moves:
            return random.choice(valid_moves)
    except Exception as e:
        logger.error(f"Error getting external AI move: {e}")
        # Fallback to random move
        import random
        valid_moves = game.get_valid_moves()
        if valid_moves:
            return random.choice(valid_moves)
    
    return None

# Simulate AI vs AI game
async def simulate_ai_battle(battle_id: str, ai1_url: Optional[str], ai2_url: Optional[str], max_turns: int = 50):
    if battle_id not in ai_battles:
        return
    
    battle = ai_battles[battle_id]
    game = battle["game"]
    
    # Reset game
    game.reset()
    
    # Update battle state
    battle["status"] = "in_progress"
    battle["current_turn"] = 0
    battle["moves"] = []
    
    # Broadcast initial state
    if battle_id in connections:
        await manager.broadcast(
            {
                "type": "battle_state",
                "state": game.get_state(),
                "status": battle["status"],
                "current_turn": battle["current_turn"],
                "battle_id": battle_id
            },
            battle_id
        )
    
    # Run simulation
    while not game.game_over and battle["current_turn"] < max_turns:
        # Add a delay to make it easier to follow
        await asyncio.sleep(1.0)
        
        # Get current player
        current_player = game.current_player
        
        # Determine which AI to use
        ai_url = ai1_url if current_player == 1 else ai2_url
        
        # If no external AI URL, use internal AI
        if not ai_url:
            valid_moves = game.get_valid_moves()
            if valid_moves and ai_agent:
                try:
                    column = get_agent_move(ai_agent, game.get_board(), valid_moves)
                except Exception as e:
                    logger.error(f"Error during AI move: {e}")
                    # If error, make random valid move
                    import random
                    column = random.choice(valid_moves)
            else:
                # Make random valid move
                import random
                column = random.choice(game.get_valid_moves())
        else:
            # Get move from external AI
            column = await make_external_ai_move(battle_id, ai_url)
            
            # If failed to get move, make random valid move
            if column is None:
                import random
                column = random.choice(game.get_valid_moves())
        
        # Make move
        if game.make_move(column):
            # Record move
            battle["moves"].append(column)
            battle["current_turn"] += 1
            
            # Broadcast update
            if battle_id in connections:
                await manager.broadcast(
                    {
                        "type": "battle_update",
                        "state": game.get_state(),
                        "status": battle["status"],
                        "current_turn": battle["current_turn"],
                        "last_move": column,
                        "moving_player": current_player,
                        "battle_id": battle_id
                    },
                    battle_id
                )
    
    # Update battle status
    if game.winner:
        battle["status"] = f"player{game.winner}_win"
    else:
        battle["status"] = "draw"
    
    # Broadcast final state
    if battle_id in connections:
        await manager.broadcast(
            {
                "type": "battle_complete",
                "state": game.get_state(),
                "status": battle["status"],
                "battle_id": battle_id,
                "moves": battle["moves"],
                "total_turns": battle["current_turn"]
            },
            battle_id
        )

@app.websocket("/ws/battle/{battle_id}")
async def websocket_battle(websocket: WebSocket, battle_id: str):
    await websocket.accept()
    
    # Add connection
    if battle_id not in connections:
        connections[battle_id] = []
    connections[battle_id].append(websocket)
    
    # Create battle if it doesn't exist
    if battle_id not in ai_battles:
        ai_battles[battle_id] = {
            "game": Connect4Game(),
            "status": "waiting",
            "current_turn": 0,
            "moves": [],
            "ai1_url": None,
            "ai2_url": None
        }
    
    # Send current battle state
    battle = ai_battles[battle_id]
    await websocket.send_json({
        "type": "battle_state",
        "state": battle["game"].get_state(),
        "status": battle["status"],
        "current_turn": battle["current_turn"],
        "battle_id": battle_id,
        "ai1_url": battle["ai1_url"],
        "ai2_url": battle["ai2_url"]
    })
    
    try:
        while True:
            data = await websocket.receive_json()
            
            if data["type"] == "start_battle":
                ai1_url = data.get("ai1_url")
                ai2_url = data.get("ai2_url")
                
                # Update AI URLs
                battle["ai1_url"] = ai1_url
                battle["ai2_url"] = ai2_url
                
                # Start simulation
                asyncio.create_task(simulate_ai_battle(
                    battle_id, 
                    ai1_url, 
                    ai2_url, 
                    max_turns=data.get("max_turns", 50)
                ))
            
            elif data["type"] == "reset_battle":
                # Cancel any ongoing battle
                for task in asyncio.all_tasks():
                    if task.get_name() == f"battle_{battle_id}":
                        task.cancel()
                
                # Reset game
                battle["game"].reset()
                battle["status"] = "waiting"
                battle["current_turn"] = 0
                battle["moves"] = []
                
                # Broadcast reset
                await manager.broadcast(
                    {
                        "type": "battle_state",
                        "state": battle["game"].get_state(),
                        "status": battle["status"],
                        "current_turn": battle["current_turn"],
                        "battle_id": battle_id,
                        "ai1_url": battle["ai1_url"],
                        "ai2_url": battle["ai2_url"]
                    },
                    battle_id
                )
    
    except WebSocketDisconnect:
        if battle_id in connections and websocket in connections[battle_id]:
            connections[battle_id].remove(websocket)
            
            # If no connections left, cleanup
            if not connections[battle_id]:
                if battle_id in ai_battles:
                    del ai_battles[battle_id]
                del connections[battle_id]
    except Exception as e:
        logger.error(f"Error in battle websocket: {e}")

# API to create an AI battle
@app.post("/api/create-battle")
async def create_battle():
    battle_id = str(uuid.uuid4())
    ai_battles[battle_id] = {
        "game": Connect4Game(),
        "status": "waiting",
        "current_turn": 0,
        "moves": [],
        "ai1_url": None,
        "ai2_url": None
    }
    return {"battle_id": battle_id}

# API to get battle state
@app.get("/api/battle/{battle_id}/state")
async def get_battle_state(battle_id: str):
    if battle_id not in ai_battles:
        raise HTTPException(status_code=404, detail="Battle not found")
    
    battle = ai_battles[battle_id]
    return {
        "state": battle["game"].get_state(),
        "status": battle["status"],
        "current_turn": battle["current_turn"],
        "battle_id": battle_id,
        "ai1_url": battle["ai1_url"],
        "ai2_url": battle["ai2_url"]
    }

# API for external AI to make a move
@app.post("/api/make-move")
async def external_ai_move(request: Request):
    try:
        data = await request.json()
        board = data.get("board")
        valid_moves = data.get("valid_moves", [])
        
        if not board or not valid_moves:
            raise HTTPException(status_code=400, detail="Invalid request data")
        
        if ai_agent:
            # Use trained AI to make a move
            column = get_agent_move(ai_agent, board, valid_moves)
        else:
            # Fallback to random move
            import random
            column = random.choice(valid_moves)
        
        return {"move": column}
    
    except Exception as e:
        logger.error(f"Error in external AI move: {e}")
        raise HTTPException(status_code=500, detail=str(e))

