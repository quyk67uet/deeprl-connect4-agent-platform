import os
import uuid
import json
import asyncio
import logging
import time
import random
import httpx
import socket
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl
import redis.asyncio as redis
import platform

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

# Redis configuration
redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
logger.info(f"Attempting to connect to Redis at: {redis_url}")

# Global Redis connection pool
redis_pool = None

class StorageManager:
    """
    Storage manager that provides Redis-like interface with fallback to in-memory storage.
    This allows the application to run even if Redis is not available.
    """
    def __init__(self):
        self.redis_client = None
        self.memory_storage = {}  # In-memory fallback
        self.use_redis = False
    
    async def initialize(self, redis_client=None):
        """Initialize with optional Redis client"""
        self.redis_client = redis_client
        self.use_redis = redis_client is not None
        
        if self.use_redis:
            try:
                await self.redis_client.ping()
                logger.info("Redis storage initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Redis: {e}")
                self.use_redis = False
                self.redis_client = None
        
        if not self.use_redis:
            logger.info("Using in-memory storage")
        
        return self.use_redis
    
    async def keys(self, pattern):
        """Get keys matching the pattern"""
        if self.use_redis:
            try:
                return await self.redis_client.keys(pattern)
            except Exception as e:
                logger.error(f"Redis keys operation failed: {e}")
                # Fall back to memory storage
        
        # Memory storage implementation
        return [key.encode('utf-8') for key in self.memory_storage.keys() 
                if key.startswith(pattern.replace("*", ""))]
    
    async def hgetall(self, key):
        """Get all fields and values in a hash"""
        if self.use_redis:
            try:
                return await self.redis_client.hgetall(key)
            except Exception as e:
                logger.error(f"Redis hgetall operation failed: {e}")
                # Fall back to memory storage
        
        # Memory storage implementation
        key_str = key.decode('utf-8') if isinstance(key, bytes) else key
        if key_str in self.memory_storage:
            result = {}
            for field, value in self.memory_storage[key_str].items():
                field_bytes = field.encode('utf-8') if isinstance(field, str) else field
                value_bytes = value.encode('utf-8') if isinstance(value, str) else value
                result[field_bytes] = value_bytes
            return result
        return {}
    
    async def hset(self, key, field, value):
        """Set field in a hash to value"""
        if self.use_redis:
            try:
                return await self.redis_client.hset(key, field, value)
            except Exception as e:
                logger.error(f"Redis hset operation failed: {e}")
                # Fall back to memory storage
        
        # Memory storage implementation
        key_str = key.decode('utf-8') if isinstance(key, bytes) else key
        field_str = field.decode('utf-8') if isinstance(field, bytes) else field
        value_str = value.decode('utf-8') if isinstance(value, bytes) and not isinstance(value, bool) else value
        
        if key_str not in self.memory_storage:
            self.memory_storage[key_str] = {}
        
        self.memory_storage[key_str][field_str] = value_str
        return 1
    
    async def hmset(self, key, mapping):
        """Set multiple fields in a hash"""
        if self.use_redis:
            try:
                return await self.redis_client.hmset(key, mapping)
            except Exception as e:
                logger.error(f"Redis hmset operation failed: {e}")
                # Fall back to memory storage
                
        # Memory storage implementation
        key_str = key.decode('utf-8') if isinstance(key, bytes) else key
        
        if key_str not in self.memory_storage:
            self.memory_storage[key_str] = {}
            
        for field, value in mapping.items():
            field_str = field.decode('utf-8') if isinstance(field, bytes) else field
            value_str = value.decode('utf-8') if isinstance(value, bytes) and not isinstance(value, bool) else value
            self.memory_storage[key_str][field_str] = value_str
            
        return True
    
    async def delete(self, *keys):
        """Delete one or more keys"""
        if self.use_redis:
            try:
                return await self.redis_client.delete(*keys)
            except Exception as e:
                logger.error(f"Redis delete operation failed: {e}")
                # Fall back to memory storage
                
        # Memory storage implementation
        count = 0
        for key in keys:
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            if key_str in self.memory_storage:
                del self.memory_storage[key_str]
                count += 1
        return count

    async def clear_all(self):
        """Clear all data in storage"""
        self.memory_storage.clear()
        if self.use_redis:
            try:
                await self.redis_client.flushall()
            except Exception as e:
                logger.error(f"Error clearing Redis: {e}")

# Create storage manager instance
storage = StorageManager()

# Create Redis connection pool - will be initialized during startup
async def init_redis_pool():
    """Initialize the Redis connection pool with error handling and retries"""
    global redis_pool
    
    max_retries = 3
    retry_count = 0
    retry_delay = 2  # seconds
    
    while retry_count < max_retries:
        try:
            logger.info(f"Attempting to connect to Redis: {redis_url} (attempt {retry_count + 1}/{max_retries})")
            # Create a connection pool
            redis_pool = redis.ConnectionPool.from_url(redis_url)
            
            # Create a test client to verify the connection
            test_client = redis.Redis(connection_pool=redis_pool)
            await test_client.ping()
            
            # Initialize storage manager with Redis
            redis_success = await storage.initialize(test_client)
            return redis_success
            
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.error(f"Redis connection error: {e}")
            retry_count += 1
            if retry_count < max_retries:
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error("Failed to connect to Redis after maximum retries")
                # Initialize storage manager without Redis
                await storage.initialize()
                return False
                
        except Exception as e:
            logger.error(f"Unexpected error connecting to Redis: {e}")
            # Initialize storage manager without Redis
            await storage.initialize()
            return False
            
    return False

async def get_redis_connection():
    """Get a Redis connection from the pool"""
    if redis_pool is None:
        return None
        
    try:
        redis_conn = redis.Redis(connection_pool=redis_pool)
        # Quick connection check
        await redis_conn.ping()
        return redis_conn
    except Exception as e:
        logger.error(f"Error getting Redis connection: {e}")
        return None

async def clear_redis_cache():
    """Clear all data in Redis cache"""
    try:
        redis_conn = await get_redis_connection()
        if redis_conn is None:
            logger.warning("Cannot clear Redis cache: connection not available")
            return False
            
        # Get all keys and delete them
        keys = await redis_conn.keys("*")
        if keys:
            logger.info(f"Clearing {len(keys)} keys from Redis cache")
            await redis_conn.delete(*keys)
            return True
        else:
            logger.info("Redis cache is already empty")
            return True
    except Exception as e:
        logger.error(f"Error clearing Redis cache: {e}")
        return False

# Championship Data Models
class TeamRegistration(BaseModel):
    team_name: str
    api_endpoint: str

class Match:
    def __init__(self, match_id: str, team_a: str, team_b: str, round_number: int):
        self.match_id = match_id
        self.team_a = team_a
        self.team_b = team_b
        self.round_number = round_number
        self.games = []
        self.status = "scheduled"  # scheduled, in_progress, finished
        self.winner = None  # team_a, team_b, draw, None
        self.team_a_points = 0
        self.team_b_points = 0
        self.start_time = None
        self.end_time = None
        self.current_game = 0  # 0-based index
        self.spectator_count = 0

class Game:
    def __init__(self, game_number: int, first_player: str):
        self.game_number = game_number  # 1, 2, 3, 4
        self.first_player = first_player  # team_a or team_b
        self.winner = None  # team_a, team_b, draw, None
        self.status = "scheduled"  # scheduled, in_progress, finished
        self.game_state = None

# Championship Manager
class ChampionshipManager:
    def __init__(self):
        self.teams = {}  # team_name -> api_endpoint
        self.matches = {}  # match_id -> Match object
        self.leaderboard = {}  # team_name -> points
        self.rounds = []  # list of list of match_ids for each round
        self.current_round = 0
        self.status = "waiting"  # waiting, in_progress, finished
        self.championship_id = str(uuid.uuid4())

    def add_team(self, team_name: str, api_endpoint: str) -> bool:
        if team_name in self.teams:
            return False
        self.teams[team_name] = api_endpoint
        self.leaderboard[team_name] = 0
        return True

    def generate_schedule(self):
        """Generate a round-robin tournament schedule for all teams."""
        if len(self.teams) < 2:
            logger.error("Not enough teams to generate schedule")
            return False
        
        team_names = list(self.teams.keys())
        
        # If odd number of teams, add a dummy team for scheduling
        if len(team_names) % 2 == 1:
            team_names.append(None)
        
        n = len(team_names)
        rounds = []
        
        for i in range(n - 1):
            round_matches = []
            for j in range(n // 2):
                team_a = team_names[j]
                team_b = team_names[n - 1 - j]
                
                # Skip matches involving the dummy team
                if team_a is not None and team_b is not None:
                    match_id = str(uuid.uuid4())
                    match = Match(match_id, team_a, team_b, i)
                    self.matches[match_id] = match
                    round_matches.append(match_id)
            
            rounds.append(round_matches)
            
            # Rotate the teams (keeping the first team fixed)
            team_names = [team_names[0]] + [team_names[-1]] + team_names[1:-1]
        
        self.rounds = rounds
        return True

    def get_team_endpoint(self, team_name: str) -> Optional[str]:
        return self.teams.get(team_name)

    def update_leaderboard(self, match_id: str):
        """Update leaderboard after a match is finished."""
        match = self.matches.get(match_id)
        if not match or match.status != "finished":
            return
        
        # Award match points: 3 for win, 1 for draw, 0 for loss
        if match.winner == "team_a":
            self.leaderboard[match.team_a] += 3
        elif match.winner == "team_b":
            self.leaderboard[match.team_b] += 3
        elif match.winner == "draw":
            self.leaderboard[match.team_a] += 1
            self.leaderboard[match.team_b] += 1

    def get_leaderboard(self) -> List[Dict]:
        """Return leaderboard sorted by points."""
        sorted_teams = sorted(
            self.leaderboard.items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        return [{"team_name": team, "points": points} for team, points in sorted_teams]

    def get_match_by_id(self, match_id: str) -> Optional[Match]:
        return self.matches.get(match_id)

    def all_matches_in_round_finished(self, round_number: int) -> bool:
        """Check if all matches in a round are finished."""
        if round_number >= len(self.rounds):
            return False
        
        for match_id in self.rounds[round_number]:
            match = self.matches.get(match_id)
            if match and match.status != "finished":
                return False
        return True

    def get_current_round_spectator_count(self) -> int:
        """Get total spectator count for all matches in current round."""
        if self.current_round >= len(self.rounds):
            return 0
        
        total_count = 0
        for match_id in self.rounds[self.current_round]:
            match = self.matches.get(match_id)
            if match:
                total_count += match.spectator_count
        return total_count

    def championship_finished(self) -> bool:
        """Check if championship is finished."""
        return self.current_round >= len(self.rounds)

# Initialize championship manager
championship_manager = ChampionshipManager()

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
        else:
            logger.info(f"Spectator joined game {game_id} (connections: {len(connections[game_id])})")
            
        # Send initial game state
        game_state = games[game_id]["game"].get_state()
        logger.info(f"Sending initial state to player {player_num}: {game_state}")
        await self.send_personal_message(
            {
                "type": "game_state",
                "state": game_state,
                "your_player": player_num,
                "agent_mode": games[game_id]["agent_mode"],
                "spectator_count": len(connections[game_id])
            },
            websocket
        )
        
        # Notify others about new player or spectator
        await self.broadcast(
            {
                "type": "player_joined",
                "player": player_num
            },
            game_id,
            websocket
        )
        
        # Send updated spectator count to all
        await self.broadcast(
            {
                "type": "spectator_count",
                "count": len(connections[game_id])
            },
            game_id
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
                
                # Send updated spectator count
                await self.broadcast(
                    {
                        "type": "spectator_count",
                        "count": len(connections[game_id])
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
        logger.error(f"Game ID {game_id} not found")
        return False
    
    game = games[game_id]["game"]
    if game.game_over:
        logger.error(f"Game {game_id} is already over")
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
        
        logger.info(f"Making request to external AI: {ai_url}")
        logger.info(f"Request data: {data}")
        
        # Make request to external AI
        async with httpx.AsyncClient() as client:
            logger.info(f"Sending request to {ai_url}")
            response = await client.post(ai_url, json=data, timeout=10.0)
            
            logger.info(f"Response status code: {response.status_code}")
            
            if response.status_code == 200:
                ai_data = response.json()
                logger.info(f"Response data: {ai_data}")
                column = ai_data.get("move")
                
                if column is not None and game.is_valid_move(column):
                    logger.info(f"Valid move received from AI: {column}")
                    return column
                else:
                    logger.error(f"Invalid move received from AI: {column}")
            else:
                logger.error(f"Error response: {response.text}")
            
        # Fallback to random move if request fails
        valid_moves = game.get_valid_moves()
        if valid_moves:
            random_move = random.choice(valid_moves)
            logger.info(f"Using fallback random move: {random_move}")
            return random_move
    except Exception as e:
        logger.error(f"Error getting external AI move: {e}")
        # Fallback to random move
        valid_moves = game.get_valid_moves()
        if valid_moves:
            random_move = random.choice(valid_moves)
            logger.info(f"Using fallback random move after exception: {random_move}")
            return random_move
    
    return None

# Simulate AI vs AI game
async def simulate_ai_battle(battle_id: str, ai1_url: Optional[str], ai2_url: Optional[str], max_turns: int = 50):
    if battle_id not in ai_battles:
        logger.error(f"Battle {battle_id} not found")
        return
    
    battle = ai_battles[battle_id]
    game = battle["game"]
    
    logger.info(f"Starting AI battle with ai1_url={ai1_url}, ai2_url={ai2_url}")
    
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
        
        logger.info(f"Turn {battle['current_turn']}, Player {current_player}, using AI URL: {ai_url}")
        
        # If no external AI URL, use internal AI
        if not ai_url:
            logger.info("No external AI URL, using internal AI")
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
                logger.info("No valid moves or AI agent, making random move")
                import random
                column = random.choice(game.get_valid_moves())
        else:
            # Prepare data for external AI
            game_state = game.get_state()
            data = {
                "board": game_state["board"],
                "current_player": game_state["current_player"],
                "valid_moves": game.get_valid_moves()
            }
            
            logger.info(f"Making request to external AI: {ai_url}")
            logger.info(f"Request data: {data}")
            
            # Get move from external AI
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(ai_url, json=data, timeout=10.0)
                    
                    logger.info(f"Response status code: {response.status_code}")
                    
                    if response.status_code == 200:
                        ai_data = response.json()
                        logger.info(f"Response data: {ai_data}")
                        column = ai_data.get("move")
                        
                        if column is not None and game.is_valid_move(column):
                            logger.info(f"Valid move received from AI: {column}")
                        else:
                            logger.error(f"Invalid move received from AI: {column}")
                            # If invalid, make random valid move
                            import random
                            column = random.choice(game.get_valid_moves())
                    else:
                        logger.error(f"Error response: {response.text}")
                        # If error, make random valid move
                        import random
                        column = random.choice(game.get_valid_moves())
            except Exception as e:
                logger.error(f"Error calling external AI: {e}")
                # If failed to get move, make random valid move
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
    
    # Check if this is a championship match
    match = championship_manager.get_match_by_id(battle_id)
    if match:
        # This is a championship match
        match.spectator_count += 1
        
        # Send match info
        await websocket.send_json({
            "type": "championship_match_info",
            "team_a": match.team_a,
            "team_b": match.team_b,
            "status": match.status,
            "round": match.round_number + 1,
            "current_game": match.current_game + 1 if match.games else 0,
            "team_a_points": match.team_a_points,
            "team_b_points": match.team_b_points,
            "spectator_count": match.spectator_count
        })
        
        # If match has games, send game info for current game
        if match.games and match.current_game < len(match.games):
            game = match.games[match.current_game]
            await websocket.send_json({
                "type": "game_info",
                "game_number": game.game_number,
                "first_player": game.first_player,
                "status": game.status,
                "state": game.game_state
            })
        
        # Broadcast spectator count update
        await broadcast_battle_update(battle_id, {
            "type": "spectator_count",
            "count": match.spectator_count
        })
    else:
        # Regular AI battle
        if battle_id not in ai_battles:
            ai_battles[battle_id] = {
                "game": Connect4Game(),
                "status": "waiting",
                "current_turn": 0,
                "moves": [],
                "ai1_url": None,
                "ai2_url": None
            }
        
        # Broadcast spectator count to all connections
        spectator_count = len(connections[battle_id])
        await manager.broadcast(
            {
                "type": "spectator_count",
                "count": spectator_count
            },
            battle_id
        )
        
        # Notify others that someone joined
        await manager.broadcast(
            {
                "type": "player_joined",
                "player": 0  # 0 indicates spectator
            },
            battle_id,
            websocket  # Exclude the current connection from receiving this message
        )
        
        # Send current battle state
        battle = ai_battles[battle_id]
        await websocket.send_json({
            "type": "battle_state",
            "state": battle["game"].get_state(),
            "status": battle["status"],
            "current_turn": battle["current_turn"],
            "battle_id": battle_id,
            "ai1_url": battle["ai1_url"],
            "ai2_url": battle["ai2_url"],
            "spectator_count": spectator_count
        })
    
    try:
        # Keep connection open for messages
        while True:
            data = await websocket.receive_json()
            logger.info(f"WebSocket message received for battle {battle_id}: {data}")
            
            # Only process commands if not a championship match
            if not match:
                if data["type"] == "start_battle":
                    logger.info(f"Battle start requested with data: {data}")
                    ai1_url = data.get("ai1_url") 
                    ai2_url = data.get("ai2_url")
                    
                    logger.info(f"AI URLs: ai1_url={ai1_url}, ai2_url={ai2_url}")
                    
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
                            "ai2_url": battle["ai2_url"],
                            "spectator_count": len(connections[battle_id])
                        },
                        battle_id
                    )
    
    except WebSocketDisconnect:
        # Handle disconnect
        if battle_id in connections and websocket in connections[battle_id]:
            connections[battle_id].remove(websocket)
            
            # If this is a championship match, update spectator count
            if match:
                match.spectator_count -= 1
                # Broadcast updated spectator count
                await broadcast_battle_update(battle_id, {
                    "type": "spectator_count",
                    "count": match.spectator_count
                })
            else:
                # Regular AI battle disconnect handling
                # Notify remaining spectators that someone left
                if connections[battle_id]:
                    spectator_count = len(connections[battle_id])
                    await manager.broadcast(
                        {
                            "type": "player_left",
                            "player": 0  # 0 indicates spectator
                        },
                        battle_id
                    )
                    
                    # Update spectator count
                    await manager.broadcast(
                        {
                            "type": "spectator_count",
                            "count": spectator_count
                        },
                        battle_id
                    )
                
                # If no connections left, cleanup
                if not connections[battle_id]:
                    if battle_id in ai_battles:
                        del ai_battles[battle_id]
                    del connections[battle_id]
    except Exception as e:
        logger.error(f"Error in battle websocket for {battle_id}: {e}")

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

# New endpoint for connect4-move
@app.post("/api/connect4-move")
async def connect4_move(request: Request):
    try:
        data = await request.json()
        logger.info(f"Received connect4-move request: {data}")
        
        board = data.get("board")
        valid_moves = data.get("valid_moves", [])
        
        if not board or not valid_moves:
            raise HTTPException(status_code=400, detail="Invalid request data")
        
        if ai_agent:
            # Use trained AI to make a move
            logger.info(f"Using trained AI to make a move")
            column = get_agent_move(ai_agent, board, valid_moves)
            logger.info(f"Returning move: {column}")
        else:
            # Fallback to random move
            import random
            column = random.choice(valid_moves)
            logger.info(f"Returning move: {column}")
        
        return {"move": column}
    
    except Exception as e:
        logger.error(f"Error in connect4 move: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Simple test endpoint
@app.get("/api/test")
async def test_endpoint():
    return {"status": "ok", "message": "Test endpoint is working"}

# Championship Registration API
@app.post("/api/championship/register")
async def register_team(team_data: TeamRegistration, background_tasks: BackgroundTasks):
    # Validate if team name is unique
    if team_data.team_name in championship_manager.teams:
        raise HTTPException(status_code=400, detail="Team name already registered")

    # Validate the endpoint
    test_game_state = {
        "board": [[0]*7 for _ in range(6)],
        "current_player": 1,
        "valid_moves": [0,1,2,3,4,5,6],
        "game_over": False,
        "winner": None
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                team_data.api_endpoint, 
                json=test_game_state, 
                timeout=10.0
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=400, 
                    detail=f"API endpoint returned status code {response.status_code}"
                )
            
            data = response.json()
            if "move" not in data or not isinstance(data["move"], int) or data["move"] not in test_game_state["valid_moves"]:
                raise HTTPException(
                    status_code=400, 
                    detail="API endpoint did not return a valid move"
                )
    except httpx.TimeoutException:
        raise HTTPException(status_code=400, detail="API endpoint timed out")
    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"Error connecting to API endpoint: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error validating API endpoint: {str(e)}")

    # Register the team
    success = championship_manager.add_team(team_data.team_name, team_data.api_endpoint)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to register team")

    # Lưu vào storage
    try:
        await storage.hset(f"team:{team_data.team_name}", "api_endpoint", team_data.api_endpoint)
        logger.info(f"Stored team {team_data.team_name} in storage")
    except Exception as e:
        logger.error(f"Error storing team in storage: {e}")
    
    # Update team count
    team_count = len(championship_manager.teams)
    max_teams = 20  # Giới hạn số đội (có thể điều chỉnh)
    logger.info(f"Team {team_data.team_name} registered. Total teams: {team_count}/{max_teams}")
    
    # Đã bỏ đoạn code tự động bắt đầu championship khi đủ 19 đội
    
    return {"success": True, "message": f"Team registered successfully. {team_count}/{max_teams} teams registered."}

# Get championship status
@app.get("/api/championship/status")
async def get_championship_status():
    team_count = len(championship_manager.teams)
    
    return {
        "status": championship_manager.status,
        "team_count": team_count,
        "current_round": championship_manager.current_round + 1 if championship_manager.rounds else 0,
        "total_rounds": len(championship_manager.rounds) if championship_manager.rounds else 0
    }

# Get championship leaderboard
@app.get("/api/championship/leaderboard")
async def get_championship_leaderboard():
    return championship_manager.get_leaderboard()

# Get championship schedule
@app.get("/api/championship/schedule")
async def get_championship_schedule():
    if not championship_manager.rounds:
        return {"rounds": []}
    
    schedule = []
    for round_idx, round_matches in enumerate(championship_manager.rounds):
        matches = []
        for match_id in round_matches:
            match = championship_manager.matches.get(match_id)
            if match:
                matches.append({
                    "match_id": match.match_id,
                    "team_a": match.team_a,
                    "team_b": match.team_b,
                    "status": match.status,
                    "winner": match.winner,
                    "team_a_points": match.team_a_points,
                    "team_b_points": match.team_b_points
                })
        schedule.append({"round": round_idx + 1, "matches": matches})
    
    return {"rounds": schedule}

# Championship start helper
async def start_championship_after_delay(delay_seconds: int):
    """Start the championship after a delay."""
    await asyncio.sleep(delay_seconds)
    
    # Generate the schedule
    logger.info("Generating championship schedule...")
    championship_manager.generate_schedule()
    
    # Set championship status to in_progress
    championship_manager.status = "in_progress"
    
    # Broadcast status change to dashboard
    await broadcast_dashboard_update("status_update", {
        "status": championship_manager.status,
        "message": "Championship has started!",
        "schedule": await get_championship_schedule()
    })
    
    # Start the first round
    await start_round(0)

async def start_round(round_number: int):
    """Start a round of matches."""
    if round_number >= len(championship_manager.rounds):
        # Championship is finished
        championship_manager.status = "finished"
        await broadcast_dashboard_update("status_update", {
            "status": championship_manager.status,
            "message": "Championship has finished!",
            "leaderboard": championship_manager.get_leaderboard()
        })
        return
    
    championship_manager.current_round = round_number
    logger.info(f"Starting round {round_number + 1}/{len(championship_manager.rounds)}")
    
    # Broadcast round start
    await broadcast_dashboard_update("round_start", {
        "round_number": round_number + 1,
        "total_rounds": len(championship_manager.rounds),
        "message": f"Round {round_number + 1} is starting!"
    })
    
    # Start all matches in this round concurrently
    tasks = []
    for match_id in championship_manager.rounds[round_number]:
        task = asyncio.create_task(execute_match(match_id))
        tasks.append(task)
    
    # Wait for all matches to complete
    await asyncio.gather(*tasks)
    
    # Check spectator count to determine delay before next round
    spectator_count = championship_manager.get_current_round_spectator_count()
    delay = 15 if spectator_count >= 1 else 5
    
    logger.info(f"Round {round_number + 1} completed. Waiting {delay} seconds before starting next round...")
    await broadcast_dashboard_update("round_complete", {
        "round_number": round_number + 1,
        "message": f"Round {round_number + 1} completed. Next round starts in {delay} seconds."
    })
    
    # Wait before starting next round
    await asyncio.sleep(delay)
    
    # Start next round
    await start_round(round_number + 1)

async def execute_match(match_id: str):
    """Execute a single match between two teams."""
    match = championship_manager.get_match_by_id(match_id)
    if not match:
        logger.error(f"Match {match_id} not found")
        return
    
    match.status = "in_progress"
    match.start_time = datetime.now()
    
    # Initialize games in this match
    match.games = [
        Game(1, "team_a"),  # Game 1: Team A starts
        Game(2, "team_b"),  # Game 2: Team B starts
        Game(3, "team_a"),  # Game 3: Team A starts
        Game(4, "team_b")   # Game 4: Team B starts
    ]
    
    # Validate both endpoints before match
    team_a_endpoint = championship_manager.get_team_endpoint(match.team_a)
    team_b_endpoint = championship_manager.get_team_endpoint(match.team_b)
    
    team_a_valid = await validate_endpoint(team_a_endpoint)
    team_b_valid = await validate_endpoint(team_b_endpoint)
    
    if not team_a_valid or not team_b_valid:
        logger.warning(f"Match {match_id}: One or both endpoints failed validation")
    
    # Broadcast match start
    await broadcast_dashboard_update("match_update", {
        "match_id": match_id,
        "status": "in_progress",
        "team_a": match.team_a,
        "team_b": match.team_b,
        "round": match.round_number + 1
    })
    
    # Set match start time for timeout tracking
    match_start_time = time.time()
    match_timeout = 300  # 5 minutes (300 seconds)
    
    # Play all 4 games
    for game_idx, game in enumerate(match.games):
        match.current_game = game_idx
        game.status = "in_progress"
        
        # Check if we've exceeded match timeout
        if time.time() - match_start_time > match_timeout:
            logger.warning(f"Match {match_id} exceeded time limit. Declaring draw.")
            match.winner = "draw"
            break
        
        # Play the game
        game_result = await play_game(match_id, game, team_a_endpoint, team_b_endpoint)
        
        # Update game result
        game.winner = game_result["winner"]
        game.status = "finished"
        
        # Update match points
        if game.winner == "team_a":
            match.team_a_points += 1
        elif game.winner == "team_b":
            match.team_b_points += 1
        elif game.winner == "draw":
            match.team_a_points += 0.5
            match.team_b_points += 0.5
        
        # Broadcast game result
        await broadcast_battle_update(match_id, {
            "type": "game_complete",
            "game_number": game.game_number,
            "winner": game.winner,
            "team_a_points": match.team_a_points,
            "team_b_points": match.team_b_points
        })
    
    # Determine match winner
    match.status = "finished"
    match.end_time = datetime.now()
    
    if match.team_a_points > match.team_b_points:
        match.winner = "team_a"
    elif match.team_b_points > match.team_a_points:
        match.winner = "team_b"
    else:
        match.winner = "draw"
    
    # Update leaderboard
    championship_manager.update_leaderboard(match_id)
    
    # Broadcast match result
    await broadcast_dashboard_update("match_update", {
        "match_id": match_id,
        "status": "finished",
        "winner": match.winner,
        "team_a_points": match.team_a_points,
        "team_b_points": match.team_b_points
    })
    
    # Broadcast updated leaderboard
    await broadcast_dashboard_update("leaderboard_update", {
        "leaderboard": championship_manager.get_leaderboard()
    })
    
    logger.info(f"Match {match_id} completed: {match.team_a} vs {match.team_b}, Winner: {match.winner}")

async def play_game(match_id: str, game: Game, team_a_endpoint: str, team_b_endpoint: str) -> Dict:
    """Play a single game between two teams."""
    match = championship_manager.get_match_by_id(match_id)
    if not match:
        logger.error(f"Match {match_id} not found")
        return {"winner": "draw"}
    
    # Create a new game instance
    connect4_game = Connect4Game()
    game.game_state = connect4_game.get_state()
    
    # Determine which team plays as which player based on first_player
    player1_team = "team_a" if game.first_player == "team_a" else "team_b"
    player2_team = "team_b" if game.first_player == "team_a" else "team_a"
    
    player1_endpoint = team_a_endpoint if player1_team == "team_a" else team_b_endpoint
    player2_endpoint = team_b_endpoint if player2_team == "team_b" else team_a_endpoint
    
    # Broadcast game start
    await broadcast_battle_update(match_id, {
        "type": "game_start",
        "game_number": game.game_number,
        "first_player": game.first_player,
        "team_a_color": "red" if player1_team == "team_a" else "yellow",
        "team_b_color": "red" if player1_team == "team_b" else "yellow",
        "state": connect4_game.get_state()
    })
    
    # Play the game until completion or timeout
    move_count = 0
    max_moves = 42  # Maximum possible moves in a 6x7 board
    
    while not connect4_game.game_over and move_count < max_moves:
        # Get current player's endpoint
        current_team = player1_team if connect4_game.current_player == 1 else player2_team
        endpoint = player1_endpoint if connect4_game.current_player == 1 else player2_endpoint
        
        # Prepare game state for AI
        game_state = {
            "board": connect4_game.get_state()["board"],
            "current_player": connect4_game.current_player,
            "valid_moves": connect4_game.get_valid_moves(),
            "game_over": connect4_game.game_over,
            "winner": connect4_game.winner
        }
        
        # Broadcast current state
        await broadcast_battle_update(match_id, {
            "type": "game_update",
            "game_number": game.game_number,
            "current_player": current_team,
            "state": connect4_game.get_state(),
            "move_count": move_count
        })
        
        # Get move from the AI with timeout
        column = await get_ai_move_with_timeout(endpoint, game_state, 10.0)
        
        # If the AI didn't provide a valid move, use fallback
        if column is None or column not in connect4_game.get_valid_moves():
            valid_moves = connect4_game.get_valid_moves()
            column = valid_moves[0] if valid_moves else None
            logger.warning(f"Using fallback move for {current_team}: {column}")
        
        # Make the move
        if column is not None:
            connect4_game.make_move(column)
            move_count += 1
            
            # Broadcast move
            await broadcast_battle_update(match_id, {
                "type": "move_made",
                "game_number": game.game_number,
                "column": column,
                "team": current_team,
                "state": connect4_game.get_state()
            })
        else:
            # No valid moves available, game is a draw
            logger.warning(f"No valid moves available for {current_team}")
            break
    
    # Determine winner
    if connect4_game.winner == 1:
        winner = player1_team
    elif connect4_game.winner == 2:
        winner = player2_team
    else:
        winner = "draw"
    
    return {"winner": winner, "moves": move_count}

async def get_ai_move_with_timeout(endpoint: str, game_state: Dict, timeout: float) -> Optional[int]:
    """Get a move from an AI endpoint with a timeout."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(endpoint, json=game_state, timeout=timeout)
            
            if response.status_code == 200:
                data = response.json()
                return data.get("move")
    except Exception as e:
        logger.error(f"Error getting AI move: {str(e)}")
    
    return None

async def validate_endpoint(endpoint: str) -> bool:
    """Validate if an endpoint is responsive and returns valid moves."""
    if not endpoint:
        return False
    
    test_game_state = {
        "board": [[0]*7 for _ in range(6)],
        "current_player": 1,
        "valid_moves": [0,1,2,3,4,5,6],
        "game_over": False,
        "winner": None
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(endpoint, json=test_game_state, timeout=10.0)
            
            if response.status_code != 200:
                return False
            
            data = response.json()
            if "move" not in data or not isinstance(data["move"], int) or data["move"] not in test_game_state["valid_moves"]:
                return False
            
            return True
    except Exception as e:
        logger.error(f"Error validating endpoint {endpoint}: {e}")
        return False

# WebSocket broadcast functions
async def broadcast_dashboard_update(update_type: str, data: Dict):
    """Broadcast updates to all dashboard WebSocket connections."""
    message = {"type": update_type, **data}
    
    if "/ws/championship/dashboard" in connections:
        for websocket in connections["/ws/championship/dashboard"]:
            await websocket.send_json(message)

async def broadcast_battle_update(match_id: str, data: Dict):
    """Broadcast updates to all WebSocket connections for a specific battle."""
    # Gửi cho endpoint thường (/ws/battle/{match_id})
    if match_id in connections:
        for websocket in connections[match_id]:
            await websocket.send_json(data)
    
    # Gửi cho endpoint championship (/ws/championship/battle/{match_id})
    championship_channel = f"championship_battle:{match_id}"
    if championship_channel in connections:
        for websocket in connections[championship_channel]:
            await websocket.send_json(data)

# Championship Dashboard WebSocket
@app.websocket("/ws/championship/dashboard")
async def websocket_championship_dashboard(websocket: WebSocket):
    """WebSocket endpoint for championship dashboard."""
    await websocket.accept()
    
    # Add connection
    if "/ws/championship/dashboard" not in connections:
        connections["/ws/championship/dashboard"] = []
    connections["/ws/championship/dashboard"].append(websocket)
    
    # Send initial state
    team_count = len(championship_manager.teams)
    await websocket.send_json({
        "type": "initial_state",
        "status": championship_manager.status,
        "team_count": team_count,
        "current_round": championship_manager.current_round + 1 if championship_manager.rounds else 0,
        "total_rounds": len(championship_manager.rounds) if championship_manager.rounds else 0,
        "leaderboard": championship_manager.get_leaderboard(),
        "schedule": await get_championship_schedule()
    })
    
    try:
        # Keep connection alive
        while True:
            data = await websocket.receive_json()
            logger.info(f"Received dashboard message: {data}")
            # Just acknowledge receipt - no specific actions needed yet
            await websocket.send_json({"type": "ack", "received": True})
    
    except WebSocketDisconnect:
        # Remove connection on disconnect
        if "/ws/championship/dashboard" in connections and websocket in connections["/ws/championship/dashboard"]:
            connections["/ws/championship/dashboard"].remove(websocket)
    except Exception as e:
        logger.error(f"Error in championship dashboard websocket: {e}")

# Utility function to load team data from Redis
async def load_teams_from_redis():
    """
    Load registered teams from storage.
    Retrieves all team data from Redis or in-memory storage.
    """
    try:
        team_keys = await storage.keys("team:*")
        logger.info(f"Found {len(team_keys)} teams in storage")
        
        for key in team_keys:
            team_data = await storage.hgetall(key)
            if not team_data:
                continue
                
            team_id = key.decode('utf-8').split(':')[1] if isinstance(key, bytes) else key.split(':')[1]
            
            # Convert byte strings to Python strings
            team = {}
            for field, value in team_data.items():
                field_name = field.decode('utf-8') if isinstance(field, bytes) else field
                field_value = value.decode('utf-8') if isinstance(value, bytes) else value
                team[field_name] = field_value
            
            # Register team in memory
            championship_manager.add_team(team_id, team.get("api_endpoint"))
            logger.info(f"Loaded team: {team.get('name', team_id)}")
            
        logger.info(f"Successfully loaded {len(championship_manager.teams)} teams from storage")
        return True
    except Exception as e:
        logger.error(f"Error loading teams from storage: {e}")
        return False

# App startup event to initialize Redis and load teams
@app.on_event("startup")
async def startup_event():
    """
    Called on application startup.
    Initialize the Redis connection and load any existing registered teams.
    """
    global redis_pool
    
    # Initialize Redis connection with retries
    redis_connected = await init_redis_pool()
    
    if redis_connected:
        logger.info("Successfully connected to Redis server")
        # Clear Redis cache on startup
        try:
            redis_conn = await get_redis_connection()
            if redis_conn is None:
                raise HTTPException(status_code=500, detail="Redis connection not available")
            
            keys = await redis_conn.keys("*")
            if keys:
                logger.info(f"Clearing {len(keys)} keys from Redis cache on startup")
                await redis_conn.delete(*keys)
        except Exception as e:
            logger.error(f"Error clearing Redis cache on startup: {e}")
    else:
        logger.warning("Using in-memory storage fallback (Redis connection failed)")
    
    # Initialize game state
    await load_teams_from_redis()
    
    logger.info("Server startup complete")

# API endpoint to manually clear Redis cache
@app.post("/api/clear-cache")
async def clear_cache_endpoint():
    """Manually clear all Redis cache and reset championship data"""
    global championship_manager
    
    try:
        # 1. Xóa cache Redis
        redis_conn = await get_redis_connection()
        if redis_conn is None:
            raise HTTPException(status_code=500, detail="Redis connection not available")
            
        # Lấy tất cả keys và xóa chúng
        keys = await redis_conn.keys("*")
        if keys:
            logger.info(f"Manually clearing {len(keys)} keys from Redis cache")
            await redis_conn.delete(*keys)
        
        # 2. Reset championship_manager về trạng thái ban đầu
        championship_manager = ChampionshipManager()
        logger.info("Championship manager đã được reset")
        
        # 3. Xóa toàn bộ dữ liệu từ memory store
        try:
            await storage.clear_all()
            logger.info("Memory storage đã được xóa")
        except Exception as e:
            logger.error(f"Lỗi khi xóa memory storage: {e}")
        
        # 4. Khởi tạo lại storage
        await storage.initialize(redis_conn if redis_conn else None)
        logger.info("Storage đã được khởi tạo lại")
            
        return {
            "success": True, 
            "message": f"Đã xóa thành công {len(keys) if keys else 0} keys từ Redis cache và reset hệ thống"
        }
    except Exception as e:
        logger.error(f"Lỗi khi xóa Redis cache: {e}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi xóa Redis cache: {str(e)}")

# Thêm endpoint mới sau phần các API championship
@app.post("/api/championship/start")
async def start_championship_manually(background_tasks: BackgroundTasks):
    """Manually start the championship"""
    # Kiểm tra số lượng đội
    team_count = len(championship_manager.teams)
    
    if team_count < 2:
        raise HTTPException(status_code=400, detail="Cần ít nhất 2 đội để bắt đầu giải đấu")
    
    if championship_manager.status != "waiting":
        raise HTTPException(status_code=400, detail="Giải đấu đã bắt đầu hoặc đã kết thúc")
    
    # Tạo lịch thi đấu
    logger.info("Đang tạo lịch thi đấu cho giải...")
    championship_manager.generate_schedule()
    
    # Cập nhật trạng thái
    championship_manager.status = "in_progress"
    
    # Broadcast trạng thái
    await broadcast_dashboard_update("status_update", {
        "status": championship_manager.status,
        "message": "Giải đấu đã bắt đầu!",
        "schedule": await get_championship_schedule()
    })
    
    # Bắt đầu vòng đầu tiên trong background
    background_tasks.add_task(start_round, 0)
    
    return {
        "success": True,
        "message": f"Giải đấu bắt đầu với {team_count} đội",
        "team_count": team_count
    }

@app.websocket("/ws/championship/battle/{match_id}")
async def websocket_championship_battle(websocket: WebSocket, match_id: str):
    """WebSocket endpoint dành riêng cho xem trận đấu championship."""
    await websocket.accept()
    
    # Thêm kết nối với key đặc biệt để phân biệt với kết nối battle thông thường
    championship_channel = f"championship_battle:{match_id}"
    if championship_channel not in connections:
        connections[championship_channel] = []
    connections[championship_channel].append(websocket)
    
    # Kiểm tra xem match_id có phải là một trận đấu championship không
    match = championship_manager.get_match_by_id(match_id)
    if not match:
        # Không phải là trận đấu championship
        await websocket.send_json({
            "type": "error",
            "message": "Không tìm thấy trận đấu championship này"
        })
        await websocket.close(code=4004)
        return
    
    # Đây là trận đấu championship, cập nhật spectator count
    match.spectator_count += 1
    
    # Gửi thông tin trận đấu
    await websocket.send_json({
        "type": "championship_match_info",
        "team_a": match.team_a,
        "team_b": match.team_b,
        "status": match.status,
        "round": match.round_number + 1,
        "current_game": match.current_game + 1 if match.games else 0,
        "team_a_points": match.team_a_points,
        "team_b_points": match.team_b_points,
        "spectator_count": match.spectator_count
    })
    
    # Nếu trận đấu có game, gửi thông tin game hiện tại
    if match.games and match.current_game < len(match.games):
        game = match.games[match.current_game]
        await websocket.send_json({
            "type": "game_info",
            "game_number": game.game_number,
            "first_player": game.first_player,
            "status": game.status,
            "state": game.game_state
        })
    
    # Broadcast cập nhật số người xem
    await broadcast_battle_update(match_id, {
        "type": "spectator_count",
        "count": match.spectator_count
    })
    
    try:
        # Giữ kết nối mở để nhận tin nhắn
        while True:
            data = await websocket.receive_json()
            logger.info(f"WebSocket message received for championship battle {match_id}: {data}")
            # Chỉ nhận tin nhắn, không xử lý command cho người xem championship
    
    except WebSocketDisconnect:
        # Xử lý ngắt kết nối
        if championship_channel in connections and websocket in connections[championship_channel]:
            connections[championship_channel].remove(websocket)
            
            # Cập nhật spectator count
            match.spectator_count -= 1
            
            # Broadcast cập nhật số người xem
            await broadcast_battle_update(match_id, {
                "type": "spectator_count",
                "count": match.spectator_count
            })
            
            # Nếu không còn kết nối, xóa channel
            if not connections[championship_channel]:
                del connections[championship_channel]
    
    except Exception as e:
        logger.error(f"Lỗi trong championship battle websocket cho {match_id}: {e}")
        # Dọn dẹp kết nối trong trường hợp lỗi
        if championship_channel in connections and websocket in connections[championship_channel]:
            connections[championship_channel].remove(websocket)
            match.spectator_count -= 1

