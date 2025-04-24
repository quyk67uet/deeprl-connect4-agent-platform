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
        self.status = "scheduled"  # scheduled, in_progress, finished
        self.winner = None  # team_a, team_b, or draw
        self.team_a_points = 0
        self.team_b_points = 0
        self.previous_team_a_points = 0  # Lưu trữ điểm số trước đó để tránh cập nhật trùng lặp
        self.previous_team_b_points = 0  # Lưu trữ điểm số trước đó để tránh cập nhật trùng lặp
        self.round_number = round_number
        self.current_game = 0  # 0-based index of current game
        self.start_time = None
        self.end_time = None
        self.games = []  # List of Game objects
        self.spectator_count = 0
        self.turn_time = 10.0  # Turn timeout in seconds (default 10s)
        self.team_a_match_time = 240.0  # Total match time for team A (default 4 minutes)
        self.team_b_match_time = 240.0  # Total match time for team B
        self.team_a_consumed_time = 0.0  # Time consumed so far by team A
        self.team_b_consumed_time = 0.0  # Time consumed so far by team B

class Game:
    def __init__(self, game_number: int, first_player: str):
        self.game_number = game_number  # 1, 2, 3, 4
        self.first_player = first_player  # team_a or team_b
        self.winner = None  # team_a, team_b, draw, None
        self.status = "scheduled"  # scheduled, in_progress, finished
        self.game_state = None
        
        # Thêm biến theo dõi thời gian cho từng nước đi
        self.last_move_time = None  # Thời gian của nước đi cuối cùng
        
        # Thêm biến để đánh dấu đã tính vào thống kê W/D/L chưa
        self._stats_counted = False

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
        self.team_consumed_times = {}  # team_name -> total_consumed_time
        # Thêm thống kê thắng/thua/hòa
        self.team_stats = {}  # team_name -> {wins, losses, draws}
        
        # Additional logging setup for time tracking
        logger.info("Championship manager initialized")

    def add_team(self, team_name: str, api_endpoint: str) -> bool:
        if team_name in self.teams:
            return False
        self.teams[team_name] = api_endpoint
        self.leaderboard[team_name] = 0
        self.team_consumed_times[team_name] = 0.0  # Initialize to 0.0 to ensure float
        # Khởi tạo thống kê thắng/thua/hòa
        self.team_stats[team_name] = {"wins": 0, "losses": 0, "draws": 0}
        logger.info(f"Team {team_name} added with initial consumed time: 0.0s")
        return True

    def generate_schedule(self):
        """Generate the championship schedule using a round-robin tournament format."""
        team_names = list(self.teams.keys())
        if len(team_names) < 2:
            logger.warning("Cannot generate schedule with less than 2 teams")
            return
        
        random.shuffle(team_names)  # Shuffle teams for randomness
        
        # Calculate number of rounds and matches per round
        num_teams = len(team_names)
        if num_teams % 2 == 1:
            team_names.append("BYE")  # Add a dummy team if odd number of teams
            num_teams += 1
        
        num_rounds = num_teams - 1
        num_matches_per_round = num_teams // 2
        
        # Generate matches for each round using the "circle method" for round-robin scheduling
        self.rounds = []
        
        # Fix positions for all teams
        positions = list(range(num_teams))
        
        for round_num in range(num_rounds):
            round_matches = []
            
            # Rotate positions - keep position[0] fixed, rotate all others clockwise
            if round_num > 0:
                positions = [positions[0]] + [positions[-1]] + positions[1:-1]
            
            # Create matches for this round based on positions
            for i in range(num_matches_per_round):
                position1 = positions[i]
                position2 = positions[num_teams - 1 - i]
                
                team1 = team_names[position1]
                team2 = team_names[position2]
                
                # Skip matches involving the dummy "BYE" team
                if team1 == "BYE" or team2 == "BYE":
                    continue
                
                # Verify teams are different
                if team1 == team2:
                    logger.error(f"Scheduling error: team {team1} matched against itself in round {round_num+1}")
                    continue
                
                # Create match with alternating home/away
                if round_num % 2 == 0 or i % 2 == 0:
                    home_team, away_team = team1, team2
                else:
                    home_team, away_team = team2, team1
                
                match_id = f"{self.championship_id}_{round_num}_{i}"
                match = Match(match_id, home_team, away_team, round_num)
                
                # Initialize time settings with floating point
                match.team_a_match_time = 240.0  # 4 minutes
                match.team_b_match_time = 240.0  # 4 minutes
                match.team_a_consumed_time = 0.0
                match.team_b_consumed_time = 0.0
                
                self.matches[match_id] = match
                round_matches.append(match_id)
            
            if round_matches:  # Only add rounds with actual matches
                self.rounds.append(round_matches)
        
        # Log the generated schedule
        logger.info(f"Championship schedule generated with {len(self.rounds)} rounds")
        for r_idx, round_matches in enumerate(self.rounds):
            matches_info = []
            for m_id in round_matches:
                match = self.matches.get(m_id)
                if match:
                    matches_info.append(f"{match.team_a} vs {match.team_b}")
            logger.info(f"Round {r_idx+1}: {', '.join(matches_info)}")

    def get_team_endpoint(self, team_name: str) -> Optional[str]:
        return self.teams.get(team_name)

    def update_leaderboard(self, match_id: str):
        """Update leaderboard after a match is finished or game is completed."""
        match = self.matches.get(match_id)
        if not match:
            return
        
        # Khởi tạo điểm số trong bảng xếp hạng nếu chưa có
        if match.team_a not in self.leaderboard:
            self.leaderboard[match.team_a] = 0
        if match.team_b not in self.leaderboard:
            self.leaderboard[match.team_b] = 0
            
        # Cập nhật điểm - chỉ cộng thêm phần chênh lệch so với trước
        delta_team_a = match.team_a_points - match.previous_team_a_points
        delta_team_b = match.team_b_points - match.previous_team_b_points
        
        # Cập nhật điểm số mới
        self.leaderboard[match.team_a] += delta_team_a
        self.leaderboard[match.team_b] += delta_team_b
        
        # Cập nhật giá trị previous_points cho lần cập nhật tiếp theo
        match.previous_team_a_points = match.team_a_points
        match.previous_team_b_points = match.team_b_points
        
        logger.info(f"Updated leaderboard: {match.team_a}={self.leaderboard[match.team_a]}, {match.team_b}={self.leaderboard[match.team_b]}")
        logger.info(f"Delta points: {match.team_a}+{delta_team_a}, {match.team_b}+{delta_team_b}")
        
        # Cộng dồn thời gian qua các trận đấu
        if match.status == "finished":
            # Lấy thời gian hiện có và cộng thêm thời gian từ trận này
            current_a_time = self.team_consumed_times.get(match.team_a, 0)
            current_b_time = self.team_consumed_times.get(match.team_b, 0)
            
            # Cộng dồn thời gian
            self.team_consumed_times[match.team_a] = current_a_time + match.team_a_consumed_time
            self.team_consumed_times[match.team_b] = current_b_time + match.team_b_consumed_time
            
            logger.info(f"Accumulated team consumed times: {match.team_a}={self.team_consumed_times[match.team_a]:.2f}s, {match.team_b}={self.team_consumed_times[match.team_b]:.2f}s")
        else:
            # Log thời gian hiện tại mà không cập nhật vào bảng xếp hạng
            logger.info(f"Current match time values: {match.team_a}={match.team_a_consumed_time:.2f}s, {match.team_b}={match.team_b_consumed_time:.2f}s")
        
        # Cập nhật thống kê win/loss/draw theo từng GAME (không phải trận đấu)
        for game in match.games:
            if game.status == "finished" and game.winner:
                # Kiểm tra xem game đã được tính vào thống kê chưa (để tránh cộng trùng lặp)
                if not hasattr(game, '_stats_counted') or not game._stats_counted:
                    if game.winner == "team_a":
                        self.team_stats[match.team_a]["wins"] += 1
                        self.team_stats[match.team_b]["losses"] += 1
                    elif game.winner == "team_b":
                        self.team_stats[match.team_b]["wins"] += 1
                        self.team_stats[match.team_a]["losses"] += 1
                    elif game.winner == "draw":
                        self.team_stats[match.team_a]["draws"] += 1
                        self.team_stats[match.team_b]["draws"] += 1
                    
                    # Đánh dấu game đã được tính vào thống kê
                    game._stats_counted = True
                    
        # Đảm bảo tổng điểm đúng - kiểm tra và điều chỉnh nếu cần
        if match.status == "finished":
            total_points = match.team_a_points + match.team_b_points
            # Nếu đây là trận đã hoàn thành và tổng số điểm không bằng 4
            if total_points != 4.0 and len(match.games) == 4:
                logger.warning(f"Match {match_id} has incorrect total points: {total_points}, fixing...")
                
                # Đếm số ván đã hoàn thành
                completed_games = sum(1 for g in match.games if g.status == "finished")
                
                # Nếu đã chơi hết tất cả các ván nhưng tổng điểm không đúng, điều chỉnh lại
                if completed_games == 4:
                    # Xem có bao nhiêu điểm còn thiếu
                    missing_points = 4.0 - total_points
                    
                    if missing_points > 0:
                        logger.info(f"Adding {missing_points} missing points to match winner")
                        # Cộng điểm cho đội thắng, nếu hòa thì chia đều
                        if match.winner == "team_a":
                            match.team_a_points += missing_points
                            # Cập nhật thống kê wins cho team_a và losses cho team_b
                            self.team_stats[match.team_a]["wins"] += int(missing_points)
                            self.team_stats[match.team_b]["losses"] += int(missing_points)
                        elif match.winner == "team_b":
                            match.team_b_points += missing_points
                            # Cập nhật thống kê wins cho team_b và losses cho team_a
                            self.team_stats[match.team_b]["wins"] += int(missing_points)
                            self.team_stats[match.team_a]["losses"] += int(missing_points)
                        else:
                            # Trường hợp hiếm gặp: không có người chiến thắng
                            match.team_a_points += missing_points / 2
                            match.team_b_points += missing_points / 2
                            # Cập nhật thống kê draws cho cả hai team
                            if missing_points >= 1:
                                draw_games = int(missing_points)
                                self.team_stats[match.team_a]["draws"] += draw_games
                                self.team_stats[match.team_b]["draws"] += draw_games
                        
                        # Cập nhật lại điểm số trên bảng xếp hạng
                        delta_team_a = match.team_a_points - match.previous_team_a_points
                        delta_team_b = match.team_b_points - match.previous_team_b_points
                        
                        self.leaderboard[match.team_a] += delta_team_a
                        self.leaderboard[match.team_b] += delta_team_b
                        
                        # Cập nhật lại giá trị previous_points
                        match.previous_team_a_points = match.team_a_points
                        match.previous_team_b_points = match.team_b_points
                        
                        logger.info(f"After correction: {match.team_a}={match.team_a_points}, {match.team_b}={match.team_b_points}")

    def get_leaderboard(self) -> List[Dict]:
        """Return leaderboard sorted by points, then by consumed time (ascending)."""
        # Sort by points (descending) and then by consumed time (ascending)
        sorted_teams = sorted(
            [(team, points, self.team_consumed_times.get(team, 0), self.team_stats.get(team, {"wins": 0, "losses": 0, "draws": 0})) 
             for team, points in self.leaderboard.items()],
            key=lambda x: (x[1], -x[2]),  # First by points (descending), then by -consumed_time (ascending)
            reverse=True
        )
        
        # Tạo danh sách kết quả với thứ hạng và các thông số
        result = []
        for rank, (team, points, consumed_time, stats) in enumerate(sorted_teams, 1):
            result.append({
                "rank": rank,
                "team_name": team, 
                "points": points, 
                "consumed_time": max(0, consumed_time),  # Đảm bảo giá trị không âm 
                "wins": stats["wins"],
                "losses": stats["losses"],
                "draws": stats["draws"]
            })
        
        return result

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
            "valid_moves": game.get_valid_moves(),
            "is_new_game": game.is_new_game()
        }
        
        logger.info(f"Making request to external AI: {ai_url}")
        logger.info(f"Request data: {data} (is_new_game: {game.is_new_game()})")
        
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
                "valid_moves": game.get_valid_moves(),
                "is_new_game": game.is_new_game()
            }
            
            logger.info(f"Making request to external AI: {ai_url}")
            logger.info(f"Request data: {data} (is_new_game: {game.is_new_game()})")
            
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
        is_new_game = data.get("is_new_game", False)
        
        if not board or not valid_moves:
            raise HTTPException(status_code=400, detail="Invalid request data")
        
        logger.info(f"Received request for move: board={len(board)}x{len(board[0])}, is_new_game={is_new_game}")
        
        if ai_agent:
            # Use trained AI to make a move
            column = get_agent_move(ai_agent, board, valid_moves)
        else:
            # Fallback to random move
            import random
            column = random.choice(valid_moves)
        
        logger.info(f"Sending move response: {column}")
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


# Championship Registration API
@app.post("/api/championship/register")
async def register_team(team_data: TeamRegistration, background_tasks: BackgroundTasks):
    # Giới hạn tối đa 20 đội tham gia
    MAX_TEAMS = 20
    if len(championship_manager.teams) >= MAX_TEAMS:
        raise HTTPException(status_code=400, detail=f"Maximum number of teams ({MAX_TEAMS}) already registered")
        
    # Validate if team name is unique
    if team_data.team_name in championship_manager.teams:
        raise HTTPException(status_code=400, detail="Team name already registered")

    # Validate the endpoint
    is_valid = await validate_endpoint(team_data.api_endpoint)
    if not is_valid:
        raise HTTPException(status_code=400, detail="API endpoint validation failed")

    # Register the team
    success = championship_manager.add_team(team_data.team_name, team_data.api_endpoint)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to register team")
        
    # Cập nhật Redis nếu cần
    try:
        key = f"team:{team_data.team_name}"
        await storage.hset(key, "api_endpoint", team_data.api_endpoint)
    except Exception as e:
        logger.error(f"Error saving team to Redis: {e}")
    
    # Trả về thông tin thành công và số đội hiện tại
    team_count = len(championship_manager.teams)
    return {
        "success": True, 
        "team_name": team_data.team_name,
        "message": f"Team registered successfully. {team_count}/{MAX_TEAMS} teams registered."
    }

# Get championship status
@app.get("/api/championship/status")
async def get_championship_status():
    team_count = len(championship_manager.teams)
    total_rounds = len(championship_manager.rounds)
    
    # Tính toán số trận đấu đồng thời dựa trên số đội
    concurrent_matches = 5 if team_count > 10 else (min(team_count // 2, 5) if team_count > 0 else 2)
    
    return {
        "status": championship_manager.status,
        "team_count": team_count,
        "current_round": championship_manager.current_round + 1 if championship_manager.rounds else 0,
        "total_rounds": total_rounds,
        "turn_time": 10,  # Default turn time in seconds
        "match_time": 240,  # Default match time per team in seconds (4 minutes)
        "concurrent_matches": concurrent_matches  # Thêm thông tin số trận đồng thời
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
                    "team_b_points": match.team_b_points,
                    "team_a_consumed_time": match.team_a_consumed_time,
                    "team_b_consumed_time": match.team_b_consumed_time,
                    "team_a_match_time": match.team_a_match_time,
                    "team_b_match_time": match.team_b_match_time
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

# Giới hạn chạy tối đa 5 trận đấu đồng thời nếu có nhiều đội, còn không thì giới hạn theo số trận mỗi vòng
async def update_match_semaphore():
    """Cập nhật số lượng trận đấu đồng thời dựa trên số lượng đội tham gia"""
    team_count = len(championship_manager.teams)
    if team_count > 10:
        # Nếu có hơn 10 đội, cho phép chạy tối đa 5 trận đồng thời
        return asyncio.Semaphore(5)
    elif team_count > 0:
        # Tính số trận mỗi vòng: team_count // 2 (làm tròn xuống)
        matches_per_round = team_count // 2
        # Nếu ít hơn 10 đội, giới hạn số trận đồng thời bằng số trận mỗi vòng
        # nhưng không vượt quá 5
        return asyncio.Semaphore(min(matches_per_round, 5))
    else:
        # Mặc định nếu chưa có đội nào
        return asyncio.Semaphore(2)

# Khởi tạo ban đầu với giá trị mặc định
match_semaphore = asyncio.Semaphore(2)

# Tạo dictionary để lưu trữ lock cho mỗi match
match_locks = {}

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
    
    # Broadcast round start với thông tin cập nhật về tổng số round
    await broadcast_dashboard_update("round_start", {
        "round_number": round_number + 1,
        "total_rounds": len(championship_manager.rounds),
        "message": f"Round {round_number + 1} is starting!"
    })
    
    # Cập nhật semaphore dựa trên số lượng đội tham gia
    global match_semaphore
    match_semaphore = await update_match_semaphore()
    
    # Lấy số lượng trận đấu đồng thời hiện tại để hiển thị log
    current_limit = match_semaphore._value
    
    # Thực hiện tất cả các trận đấu song song, với số lượng tối đa phụ thuộc vào số đội
    async def execute_match_with_semaphore(match_id):
        async with match_semaphore:
            logger.info(f"Executing match {match_id} (in parallel, limit: {current_limit})")
            try:
                await execute_match(match_id)
            except Exception as e:
                logger.error(f"Error executing match {match_id}: {e}")
                raise  # Re-raise để asyncio.gather có thể thu thập lỗi
    
    # Tạo task cho mỗi trận đấu
    match_tasks = []
    for match_id in championship_manager.rounds[round_number]:
        # Tạo lock riêng cho mỗi match
        if match_id not in match_locks:
            match_locks[match_id] = asyncio.Lock()
            
        logger.info(f"Scheduling match {match_id} for parallel execution")
        match_task = asyncio.create_task(execute_match_with_semaphore(match_id))
        match_tasks.append(match_task)
    
    # Đợi tất cả các trận đấu trong round hoàn thành, xử lý các ngoại lệ 
    if match_tasks:
        logger.info(f"Waiting for {len(match_tasks)} matches to complete in parallel (max {current_limit} concurrently)")
        try:
            await asyncio.gather(*match_tasks)
            logger.info(f"All {len(match_tasks)} matches in round {round_number + 1} have completed")
        except Exception as e:
            logger.error(f"Error in one or more matches in round {round_number + 1}: {e}")
            # Tiếp tục thực hiện round tiếp theo ngay cả khi có lỗi
    
    # Giảm thời gian chờ giữa các vòng xuống còn 5 giây
    delay = 5
    
    logger.info(f"Round {round_number + 1} completed. Waiting {delay} seconds before starting next round...")
    
    # Đảm bảo gửi leaderboard mới nhất cùng với thông báo kết thúc vòng
    await broadcast_dashboard_update("round_complete", {
        "round_number": round_number + 1,
        "message": f"Round {round_number + 1} completed. Next round starts in {delay} seconds.",
        "leaderboard": championship_manager.get_leaderboard()  # Gửi leaderboard sau mỗi vòng
    })
    
    # Wait before starting next round
    await asyncio.sleep(delay)
    
    # Start next round
    await start_round(round_number + 1)

async def execute_match(match_id: str):
    """Execute a single match between two teams."""
    match_lock = match_locks.get(match_id)
    if not match_lock:
        match_lock = asyncio.Lock()
        match_locks[match_id] = match_lock
        
    try:
        # Lấy match thông qua hàm getter để tránh xung đột
        match = championship_manager.get_match_by_id(match_id)
        if not match:
            logger.error(f"Match {match_id} not found")
            return
        
        async with match_lock:
            # Đóng tất cả các kết nối WebSocket cũ tới trận đấu này (nếu có)
            championship_channel = f"championship_battle:{match_id}"
            if championship_channel in connections and connections[championship_channel]:
                close_count = len(connections[championship_channel])
                logger.info(f"Closing {close_count} existing connections to match {match_id} before starting")
                
                # Gửi thông báo trận đấu kết thúc và sẽ bắt đầu lại
                websockets_to_close = connections[championship_channel].copy()  # Tạo bản sao để tránh sửa đổi trong khi lặp
                for websocket in websockets_to_close:
                    try:
                        await websocket.send_json({
                            "type": "match_restart",
                            "message": "Trận đấu đang được khởi động lại. Vui lòng làm mới trang."
                        })
                        await websocket.close(code=1000)
                    except Exception as e:
                        logger.error(f"Error closing WebSocket connection: {e}")
                
                # Xóa danh sách kết nối cũ
                connections[championship_channel] = []
            
            match.status = "in_progress"
            match.start_time = datetime.now()
            
            # Initialize games in this match
            match.games = [
                Game(1, "team_a"),  # Game 1: Team A starts
                Game(2, "team_b"),  # Game 2: Team B starts
                Game(3, "team_a"),  # Game 3: Team A starts
                Game(4, "team_b")   # Game 4: Team B starts
            ]
            
            # Reset time counters for this match with consistent float values
            match.team_a_match_time = 240.0  # 4 minutes = 240 seconds
            match.team_b_match_time = 240.0  # 4 minutes = 240 seconds
            match.team_a_consumed_time = 0.0
            match.team_b_consumed_time = 0.0
            
            # Log initial time values 
            logger.info(f"Match {match_id} started with initial time values: A={match.team_a_match_time}s, B={match.team_b_match_time}s")
            
            # Validate both endpoints before match
            team_a_endpoint = championship_manager.get_team_endpoint(match.team_a)
            team_b_endpoint = championship_manager.get_team_endpoint(match.team_b)
            
        # Validate endpoints song song bên ngoài lock để tăng hiệu suất
        team_a_valid_task = asyncio.create_task(validate_endpoint(team_a_endpoint))
        team_b_valid_task = asyncio.create_task(validate_endpoint(team_b_endpoint))
        
        # Đợi kết quả validate
        team_a_valid, team_b_valid = await asyncio.gather(team_a_valid_task, team_b_valid_task)
        
        async with match_lock:
            match = championship_manager.get_match_by_id(match_id)  # Lấy lại match để đảm bảo dữ liệu mới nhất
            if not match:
                logger.error(f"Match {match_id} not found after endpoint validation")
                return
                
            if not team_a_valid or not team_b_valid:
                logger.warning(f"Match {match_id}: One or both endpoints failed validation")
            
            # Broadcast match start with correct time information
            await broadcast_dashboard_update("match_update", {
                "match_id": match_id,
                "status": "in_progress",
                "team_a": match.team_a,
                "team_b": match.team_b,
                "round": match.round_number + 1,
                "team_a_match_time": match.team_a_match_time,
                "team_b_match_time": match.team_b_match_time,
                "team_a_consumed_time": match.team_a_consumed_time,
                "team_b_consumed_time": match.team_b_consumed_time,
                "turn_time": match.turn_time
            })
        
        # Flag to track if the match should end early
        should_end_early = False
        team_out_of_time = None
        
        # Play all 4 games
        for game_idx, game in enumerate(match.games):
            # Kiểm tra và đảm bảo các giá trị thời gian hợp lệ trước khi bắt đầu game mới
            async with match_lock:
                match = championship_manager.get_match_by_id(match_id)  # Lấy lại match để đảm bảo dữ liệu mới nhất
                if not match:
                    logger.error(f"Match {match_id} not found before starting game {game.game_number}")
                    break
                    
                if match.team_a_match_time < 0 or match.team_a_match_time > 240.0:
                    logger.warning(f"Invalid team A match time before game {game.game_number}: {match.team_a_match_time}. Resetting to valid value.")
                    match.team_a_match_time = max(0.0, min(match.team_a_match_time, 240.0))
                
                if match.team_b_match_time < 0 or match.team_b_match_time > 240.0:
                    logger.warning(f"Invalid team B match time before game {game.game_number}: {match.team_b_match_time}. Resetting to valid value.")
                    match.team_b_match_time = max(0.0, min(match.team_b_match_time, 240.0))
                    
                if match.team_a_consumed_time < 0:
                    logger.warning(f"Invalid team A consumed time before game {game.game_number}: {match.team_a_consumed_time}. Resetting to 0.")
                    match.team_a_consumed_time = 0.0
                    
                if match.team_b_consumed_time < 0:
                    logger.warning(f"Invalid team B consumed time before game {game.game_number}: {match.team_b_consumed_time}. Resetting to 0.")
                    match.team_b_consumed_time = 0.0
                
                # Check if we should end early due to score difference
                match_winner_decided = False
                if game_idx > 0:  # Only check after the first game
                    remaining_games = len(match.games) - game_idx
                    # If one team can't mathematically win anymore, mark match winner but continue playing
                    if match.team_a_points > match.team_b_points + remaining_games:
                        match_winner_decided = True
                        match.winner = "team_a"
                        logger.info(f"Match {match_id} winner decided early: {match.team_a} (points: {match.team_a_points} vs {match.team_b_points})")
                    elif match.team_b_points > match.team_a_points + remaining_games:
                        match_winner_decided = True
                        match.winner = "team_b"
                        logger.info(f"Match {match_id} winner decided early: {match.team_b} (points: {match.team_b_points} vs {match.team_a_points})")
                    
                    # Notify clients if the match winner is decided, but don't end early
                    if match_winner_decided:
                        await broadcast_battle_update(match_id, {
                            "type": "winner_decided_early",
                            "reason": "score_difference",
                            "winner": match.winner,
                            "team_a_points": match.team_a_points,
                            "team_b_points": match.team_b_points,
                            "team_a_match_time": max(0, match.team_a_match_time),
                            "team_b_match_time": max(0, match.team_b_match_time),
                            "team_a_consumed_time": match.team_a_consumed_time,
                            "team_b_consumed_time": match.team_b_consumed_time,
                            "remaining_games": remaining_games
                        })
                        # Continue playing all games, don't break early
                
                # Check if a team has run out of match time (non-negative check) - this is the only case where we end early
                if match.team_a_match_time <= 0:
                    team_out_of_time = "team_a"
                    logger.info(f"Team A ({match.team_a}) has run out of total match time")
                    
                    # Award points to team B for all remaining games
                    remaining_games = len(match.games) - game_idx
                    match.team_b_points += remaining_games
                    
                    # Update team stats for each remaining game
                    for _ in range(remaining_games):
                        championship_manager.team_stats[match.team_a]["losses"] += 1
                        championship_manager.team_stats[match.team_b]["wins"] += 1
                    
                    match.winner = "team_b"
                    
                    # Broadcast time out message
                    await broadcast_battle_update(match_id, {
                        "type": "match_time_out",
                        "team": match.team_a,
                        "remaining_games": remaining_games,
                        "team_a_points": match.team_a_points,
                        "team_b_points": match.team_b_points,
                        "team_a_match_time": 0,  # Set explicitly to 0
                        "team_b_match_time": max(0, match.team_b_match_time),
                        "team_a_consumed_time": match.team_a_consumed_time,
                        "team_b_consumed_time": match.team_b_consumed_time
                    })
                    
                    # End match early in case of time out
                    should_end_early = True
                    break
                
                if match.team_b_match_time <= 0:
                    team_out_of_time = "team_b"
                    logger.info(f"Team B ({match.team_b}) has run out of total match time")
                    
                    # Award points to team A for all remaining games
                    remaining_games = len(match.games) - game_idx
                    match.team_a_points += remaining_games
                    
                    # Update team stats for each remaining game
                    for _ in range(remaining_games):
                        championship_manager.team_stats[match.team_b]["losses"] += 1
                        championship_manager.team_stats[match.team_a]["wins"] += 1
                    
                    match.winner = "team_a"
                    
                    # Broadcast time out message
                    await broadcast_battle_update(match_id, {
                        "type": "match_time_out",
                        "team": match.team_b,
                        "remaining_games": remaining_games,
                        "team_a_points": match.team_a_points,
                        "team_b_points": match.team_b_points,
                        "team_a_match_time": max(0, match.team_a_match_time),
                        "team_b_match_time": 0,  # Set explicitly to 0
                        "team_a_consumed_time": match.team_a_consumed_time,
                        "team_b_consumed_time": match.team_b_consumed_time
                    })
                    
                    # End match early in case of time out
                    should_end_early = True
                    break
                
                # Cập nhật trạng thái trận đấu
                match.current_game = game_idx
                game.status = "in_progress"
                
                # Lấy thông tin endpoint mới nhất
                team_a_endpoint = championship_manager.get_team_endpoint(match.team_a)
                team_b_endpoint = championship_manager.get_team_endpoint(match.team_b)
                
                # Log thời gian trước khi bắt đầu ván
                logger.info(f"Game {game.game_number} starting with time values: A={match.team_a_match_time}s, B={match.team_b_match_time}s")
            
            # Play the game - không cần lock vì hàm play_game sẽ xử lý khóa nội bộ
            try:
                game_result = await play_game(match_id, game, team_a_endpoint, team_b_endpoint)
            except Exception as e:
                logger.error(f"Error in play_game for match {match_id}, game {game.game_number}: {e}")
                # Tiếp tục với game tiếp theo thay vì dừng toàn bộ trận đấu
                continue
            
            # Cập nhật kết quả game
            async with match_lock:
                # Lấy lại match object để đảm bảo có thông tin mới nhất
                match = championship_manager.get_match_by_id(match_id)
                if not match:
                    logger.error(f"Match {match_id} not found after playing game {game.game_number}")
                    break
                
                # Log thời gian sau khi kết thúc ván
                logger.info(f"Game {game.game_number} completed with time values: A={match.team_a_match_time}s, B={match.team_b_match_time}s")
                logger.info(f"Consumed time after game {game.game_number}: A={match.team_a_consumed_time}s, B={match.team_b_consumed_time}s")
                
                # Update game result
                game.winner = game_result["winner"]
                game.status = "finished"
                
                # Lưu điểm số trước đó
                match.previous_team_a_points = match.team_a_points
                match.previous_team_b_points = match.team_b_points
                
                # Update points based on game result
                if game.winner == "team_a":
                    match.team_a_points += 1
                    logger.info(f"Game {game.game_number}: {match.team_a} wins (+1 point)")
                elif game.winner == "team_b":
                    match.team_b_points += 1
                    logger.info(f"Game {game.game_number}: {match.team_b} wins (+1 point)")
                elif game.winner == "draw":
                    match.team_a_points += 0.5
                    match.team_b_points += 0.5
                    logger.info(f"Game {game.game_number}: Draw (+0.5 points each)")
                
                # Log additional information about the reason if available
                if game_result.get("reason") in ["turn_time_exceeded", "match_time_exceeded", "invalid_move"]:
                    loser_team = "team_a" if game.winner == "team_b" else "team_b"
                    logger.info(f"Game {game.game_number}: {loser_team} lost due to {game_result.get('reason')}")
                    
                # Đánh dấu game chưa được tính thống kê W/D/L
                game._stats_counted = False
                
                # Cập nhật tạm thời leaderboard sau mỗi game
                match.status = "in_progress"  # Đảm bảo trạng thái vẫn là "in_progress"
                championship_manager.update_leaderboard(match_id)
                
                # Broadcast game result with time information
                await broadcast_battle_update(match_id, {
                    "type": "game_complete",
                    "game_number": game.game_number,
                    "winner": game.winner,
                    "reason": game_result.get("reason", "game_completed"),
                    "team_a_points": match.team_a_points,
                    "team_b_points": match.team_b_points,
                    "team_a_match_time": max(0, match.team_a_match_time),
                    "team_b_match_time": max(0, match.team_b_match_time),
                    "team_a_consumed_time": match.team_a_consumed_time,
                    "team_b_consumed_time": match.team_b_consumed_time,
                    "game_over": game_result.get("game_over", True),
                    "winner_player": game_result.get("winner_player", None)
                })
                
                # Broadcast leaderboard update sau mỗi game
                await broadcast_dashboard_update("leaderboard_update", {
                    "leaderboard": championship_manager.get_leaderboard()
                })
            
            # Add delay between games if this isn't the last game
            if game_idx < len(match.games) - 1 and not should_end_early:
                logger.info(f"Adding 1.5-second delay before starting game {game_idx + 2}")
                await broadcast_battle_update(match_id, {
                    "type": "game_transition",
                    "message": "Transitioning to next game...",
                    "delay_seconds": 1.5
                })
                await asyncio.sleep(1.5)
        
        # Hoàn thành trận đấu và cập nhật kết quả
        async with match_lock:
            match = championship_manager.get_match_by_id(match_id)
            if not match:
                logger.error(f"Match {match_id} not found during finalization")
                return
                
            match.status = "completed"
            match.end_time = datetime.now()
            
            # Calculate total duration
            match_duration = (match.end_time - match.start_time).total_seconds()
            
            # Count actual completed games
            completed_games = sum(1 for g in match.games if g.status == "finished")
            
            # Find winner if not determined yet
            if not match.winner:
                if match.team_a_points > match.team_b_points:
                    match.winner = "team_a"
                elif match.team_b_points > match.team_a_points:
                    match.winner = "team_b"
                else:
                    # If points are equal, use consumed time as tie-breaker
                    if match.team_a_consumed_time < match.team_b_consumed_time:
                        match.winner = "team_a"
                    else:
                        match.winner = "team_b"
            
            # Đánh dấu trận đấu đã hoàn thành
            match.status = "finished"
            
            # Update leaderboard
            championship_manager.update_leaderboard(match_id)
            
            # Build result message with additional info
            result_message = {
                "match_id": match_id,
                "status": "completed",
                "team_a": match.team_a,
                "team_b": match.team_b,
                "team_a_points": match.team_a_points,
                "team_b_points": match.team_b_points,
                "winner": match.winner,
                "team_a_match_time": max(0, match.team_a_match_time),
                "team_b_match_time": max(0, match.team_b_match_time),
                "team_a_consumed_time": match.team_a_consumed_time,
                "team_b_consumed_time": match.team_b_consumed_time,
                "games_played": completed_games,
                "total_games": len(match.games),
                "match_duration": match_duration
            }
            
            # Add early termination info if applicable
            if should_end_early:
                result_message["early_termination"] = True
                result_message["reason"] = "time_out"
                result_message["team_out_of_time"] = team_out_of_time
            
            # Broadcast match complete
            await broadcast_dashboard_update("match_update", result_message)
            
            # Broadcast updated leaderboard
            await broadcast_dashboard_update("leaderboard_update", {
                "leaderboard": championship_manager.get_leaderboard()
            })
            
            # Log match result
            logger.info(f"Match {match_id} completed. Winner: {match.winner}, Score: {match.team_a} {match.team_a_points} - {match.team_b_points} {match.team_b}")
            logger.info(f"Time remaining: {match.team_a}: {match.team_a_match_time:.2f}s, {match.team_b}: {match.team_b_match_time:.2f}s")
            logger.info(f"Time consumed: {match.team_a}: {match.team_a_consumed_time:.2f}s, {match.team_b}: {match.team_b_consumed_time:.2f}s")
    
    except Exception as e:
        logger.error(f"Unhandled error in execute_match({match_id}): {e}")
        # Try to mark the match as completed with error
        try:
            match = championship_manager.get_match_by_id(match_id)
            if match and match.status != "completed":
                match.status = "completed"
                match.winner = "error"
                
                # Broadcast match error
                await broadcast_dashboard_update("match_update", {
                    "match_id": match_id,
                    "status": "error",
                    "team_a": match.team_a,
                    "team_b": match.team_b,
                    "error": str(e)
                })
        except Exception as inner_e:
            logger.error(f"Error handling match failure for {match_id}: {inner_e}")

async def play_game(match_id: str, game: Game, team_a_endpoint: str, team_b_endpoint: str) -> Dict:
    """Play a game between two teams."""
    logger.info(f"Starting game {game.game_number} for match {match_id}: {team_a_endpoint} vs {team_b_endpoint}")
    
    # Thêm sleep nhỏ trước khi bắt đầu game để tránh quá tải server
    await asyncio.sleep(0.5)
    
    match = championship_manager.get_match_by_id(match_id)
    if not match:
        logger.error(f"Match {match_id} not found in play_game")
        return {"winner": "error", "moves": 0, "reason": "match_not_found"}
    
    # Determine player assignments
    if game.first_player == "team_a":
        player1_team = "team_a"
        player2_team = "team_b"
        player1_endpoint = team_a_endpoint
        player2_endpoint = team_b_endpoint
    else:
        player1_team = "team_b"
        player2_team = "team_a"
        player1_endpoint = team_b_endpoint
        player2_endpoint = team_a_endpoint
    
    # Create a new game instance
    connect4_game = Connect4Game()
    game.game_state = connect4_game.get_state()
    
    # Đảm bảo thời gian mặc định không vượt quá 240s và không bị âm
    match.team_a_match_time = min(max(0, match.team_a_match_time), 240)
    match.team_b_match_time = min(max(0, match.team_b_match_time), 240)
    
    # Broadcast game start with time information
    await broadcast_battle_update(match_id, {
        "type": "game_start",
        "game_number": game.game_number,
        "first_player": game.first_player,
        "team_a_color": "red" if player1_team == "team_a" else "yellow",
        "team_b_color": "red" if player1_team == "team_b" else "yellow",
        "state": connect4_game.get_state(),
        "team_a_match_time": match.team_a_match_time,
        "team_b_match_time": match.team_b_match_time,
        "team_a_consumed_time": match.team_a_consumed_time,
        "team_b_consumed_time": match.team_b_consumed_time,
        "turn_time": match.turn_time
    })
    
    # Play the game until completion or timeout
    move_count = 0
    max_moves = 42  # Maximum possible moves in a 6x7 board
    
    while not connect4_game.game_over and move_count < max_moves:
        # Get current player's endpoint
        current_team = player1_team if connect4_game.current_player == 1 else player2_team
        endpoint = player1_endpoint if connect4_game.current_player == 1 else player2_endpoint
        
        # Check if the team has enough match time left
        current_match_time = match.team_a_match_time if current_team == "team_a" else match.team_b_match_time
        
        if current_match_time <= 0:
            # Team has run out of match time, they lose this game and all remaining games
            logger.warning(f"Team {current_team} has run out of match time")
            
            # Set winner to the other team
            winner = "team_b" if current_team == "team_a" else "team_a"
            winner_player = 2 if connect4_game.current_player == 1 else 1
            
            # Broadcast time-out with correct time values
            await broadcast_battle_update(match_id, {
                "type": "time_out",
                "game_number": game.game_number,
                "team": current_team,
                "reason": "match_time_exceeded",
                "winner": winner,
                "team_a_match_time": max(0, match.team_a_match_time),
                "team_b_match_time": max(0, match.team_b_match_time),
                "team_a_consumed_time": match.team_a_consumed_time,
                "team_b_consumed_time": match.team_b_consumed_time
            })
            
            return {
                "winner": winner, 
                "moves": move_count, 
                "reason": "match_time_exceeded", 
                "game_over": True,
                "winner_player": winner_player
            }
        
        # Prepare game state for AI using the is_new_game method from the game class
        game_state = {
            "board": connect4_game.get_state()["board"],
            "current_player": connect4_game.current_player,
            "valid_moves": connect4_game.get_valid_moves(),
            "is_new_game": connect4_game.is_new_game()
        }
        
        # Log the state being sent to API
        logger.info(f"Game state sent to API: is_new_game={connect4_game.is_new_game()}, move_count={move_count}")
        
        # Broadcast current state with time information
        await broadcast_battle_update(match_id, {
            "type": "game_update",
            "game_number": game.game_number,
            "current_player": current_team,
            "state": connect4_game.get_state(),
            "move_count": move_count,
            "team_a_match_time": max(0, match.team_a_match_time),
            "team_b_match_time": max(0, match.team_b_match_time),
            "team_a_consumed_time": match.team_a_consumed_time,
            "team_b_consumed_time": match.team_b_consumed_time,
            "turn_time": match.turn_time
        })
        
        # Thêm thông báo match_update để cập nhật trận đấu realtime trên dashboard
        await broadcast_dashboard_update("match_update", {
            "match_id": match_id,
            "status": "in_progress",
            "team_a": match.team_a,
            "team_b": match.team_b,
            "team_a_points": match.team_a_points,
            "team_b_points": match.team_b_points,
            "current_game": game.game_number
        })
        
        # Record move start time
        move_start_time = time.time()
        game.last_move_time = move_start_time
        
        # Get move from the AI with turn time limit
        column = await get_ai_move_with_timeout(endpoint, game_state, match.turn_time)
        
        # Calculate time taken for this move
        move_time = time.time() - move_start_time
        move_time = min(move_time, match.turn_time)  # Cap at maximum turn time
        
        # Kiểm tra và đảm bảo move_time là giá trị hợp lệ
        if move_time < 0:
            logger.warning(f"Detected negative move time: {move_time}. Setting to 0.")
            move_time = 0.0
        
        # Update team's match time and consumed time
        if current_team == "team_a":
            old_match_time = match.team_a_match_time
            old_consumed_time = match.team_a_consumed_time
            
            # Cập nhật thời gian với bảo vệ giá trị
            match.team_a_match_time = max(0.0, match.team_a_match_time - move_time)
            match.team_a_consumed_time += move_time
            
            # Kiểm tra xem giá trị đã được cập nhật có hợp lệ không
            if match.team_a_match_time > 240.0:
                logger.error(f"Invalid team_a_match_time: {match.team_a_match_time}. Resetting to 240.0")
                match.team_a_match_time = 240.0
            if match.team_a_consumed_time < 0:
                logger.error(f"Invalid team_a_consumed_time: {match.team_a_consumed_time}. Resetting to previous value + move_time")
                match.team_a_consumed_time = max(0.0, old_consumed_time + move_time)
            
            logger.info(f"Team A used {move_time:.2f}s for this move. Remaining: {match.team_a_match_time:.2f}s, Total consumed: {match.team_a_consumed_time:.2f}s")
        else:
            old_match_time = match.team_b_match_time
            old_consumed_time = match.team_b_consumed_time
            
            # Cập nhật thời gian với bảo vệ giá trị
            match.team_b_match_time = max(0.0, match.team_b_match_time - move_time)
            match.team_b_consumed_time += move_time
            
            # Kiểm tra xem giá trị đã được cập nhật có hợp lệ không
            if match.team_b_match_time > 240.0:
                logger.error(f"Invalid team_b_match_time: {match.team_b_match_time}. Resetting to 240.0")
                match.team_b_match_time = 240.0
            if match.team_b_consumed_time < 0:
                logger.error(f"Invalid team_b_consumed_time: {match.team_b_consumed_time}. Resetting to previous value + move_time")
                match.team_b_consumed_time = max(0.0, old_consumed_time + move_time)
                
            logger.info(f"Team B used {move_time:.2f}s for this move. Remaining: {match.team_b_match_time:.2f}s, Total consumed: {match.team_b_consumed_time:.2f}s")
        
        # Check if move was made within turn time
        if column is None or column not in connect4_game.get_valid_moves():
            # Turn timeout or invalid move, team loses this game
            logger.warning(f"Team {current_team} made an invalid move or exceeded turn time: {column}")
            
            # Set winner to the other team
            winner = "team_b" if current_team == "team_a" else "team_a"
            winner_player = 2 if connect4_game.current_player == 1 else 1
            
            # Broadcast turn timeout with correct time values
            await broadcast_battle_update(match_id, {
                "type": "time_out",
                "game_number": game.game_number,
                "team": current_team,
                "reason": "turn_time_exceeded",
                "winner": winner,
                "team_a_match_time": max(0, match.team_a_match_time),
                "team_b_match_time": max(0, match.team_b_match_time),
                "team_a_consumed_time": match.team_a_consumed_time,
                "team_b_consumed_time": match.team_b_consumed_time
            })
            
            return {
                "winner": winner, 
                "moves": move_count, 
                "reason": "turn_time_exceeded", 
                "game_over": True,
                "winner_player": winner_player
            }
        
        # Make the move
        connect4_game.make_move(column)
        move_count += 1
        
        # Broadcast move with updated time information
        await broadcast_battle_update(match_id, {
            "type": "move_made",
            "game_number": game.game_number,
            "column": column,
            "team": current_team,
            "state": connect4_game.get_state(),
            "move_time": move_time,
            "team_a_match_time": max(0, match.team_a_match_time),
            "team_b_match_time": max(0, match.team_b_match_time),
            "team_a_consumed_time": match.team_a_consumed_time,
            "team_b_consumed_time": match.team_b_consumed_time
        })
    
    # Determine winner based on game result
    if connect4_game.winner == 1:
        winner = player1_team
    elif connect4_game.winner == 2:
        winner = player2_team
    else:
        winner = "draw"
    
    return {
        "winner": winner, 
        "moves": move_count, 
        "reason": "game_completed",
        "game_over": connect4_game.game_over,
        "winner_player": connect4_game.winner
    }

async def validate_endpoint(endpoint: str) -> bool:
    """Validate if an endpoint responds correctly to a test request."""
    if not endpoint:
        return False
    
    # Thêm sleep để tránh quá tải server khi validate nhiều endpoint cùng lúc
    await asyncio.sleep(0.5)
    
    test_game_state = {
        "board": [[0]*7 for _ in range(6)],
        "current_player": 1,
        "valid_moves": [0,1,2,3,4,5,6],
        "is_new_game": True
    }
    
    try:
        # Tạo httpx client với verify=False để bỏ qua lỗi SSL
        async with httpx.AsyncClient(verify=False) as client:
            # Thử HTTPS trước
            try:
                # Đảm bảo endpoint có protocol
                if not endpoint.startswith(('http://', 'https://')):
                    endpoint = 'https://' + endpoint
                
                response = await client.post(
                    endpoint, 
                    json=test_game_state, 
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if "move" in data and isinstance(data["move"], int) and data["move"] in test_game_state["valid_moves"]:
                        return True
            except Exception as e:
                logger.warning(f"HTTPS attempt failed for {endpoint}: {e}")
                
                # Thêm thời gian chờ trước khi thử lại với HTTP
                await asyncio.sleep(0.5)
                
                # Thử lại với HTTP nếu HTTPS thất bại
                try:
                    # Chuyển sang HTTP
                    http_endpoint = endpoint.replace('https://', 'http://')
                    if not http_endpoint.startswith('http://'):
                        http_endpoint = 'http://' + http_endpoint.replace('https://', '')
                    
                    response = await client.post(
                        http_endpoint, 
                        json=test_game_state, 
                        timeout=10.0
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        if "move" in data and isinstance(data["move"], int) and data["move"] in test_game_state["valid_moves"]:
                            logger.info(f"HTTP endpoint validated successfully: {http_endpoint}")
                            return True
                except Exception as e:
                    logger.error(f"HTTP attempt also failed for {http_endpoint}: {e}")
        
        return False
    except Exception as e:
        logger.error(f"Error validating endpoint {endpoint}: {e}")
        return False

async def get_ai_move_with_timeout(endpoint: str, game_state: Dict, timeout: float) -> Optional[int]:
    """Get a move from an AI endpoint with a timeout."""
    if not endpoint:
        logger.error("No endpoint provided")
        return None
    
    # Thêm sleep để tránh quá tải server khi gọi API đồng thời
    await asyncio.sleep(0.5)
        
    try:
        # Log the request to help with debugging
        logger.info(f"Sending request to AI endpoint with game state: board shape={len(game_state['board'])}x{len(game_state['board'][0])}, "
                   f"current_player={game_state['current_player']}, "
                   f"valid_moves={game_state['valid_moves']}, "
                   f"is_new_game={game_state.get('is_new_game', False)}")
        
        # Create httpx client with verify=False to skip SSL errors
        async with httpx.AsyncClient(verify=False) as client:
            # Ensure endpoint has protocol
            if not endpoint.startswith(('http://', 'https://')):
                endpoint = 'https://' + endpoint
                
            try:
                response = await client.post(endpoint, json=game_state, timeout=timeout)
                
                if response.status_code == 200:
                    data = response.json()
                    if "move" in data and isinstance(data["move"], int):
                        logger.info(f"Received valid move from API: {data['move']}")
                        return data["move"]
                    else:
                        logger.warning(f"Received invalid move format: {data}")
            except Exception as e:
                logger.warning(f"HTTPS attempt failed: {str(e)}")
                
                # Thêm thời gian chờ trước khi thử lại với HTTP
                await asyncio.sleep(0.5)
                
                # Try again with HTTP if HTTPS fails
                try:
                    # Switch to HTTP
                    http_endpoint = endpoint.replace('https://', 'http://')
                    if not http_endpoint.startswith('http://'):
                        http_endpoint = 'http://' + http_endpoint.replace('https://', '')
                    
                    logger.info(f"Retrying with HTTP endpoint: {http_endpoint}")
                    response = await client.post(http_endpoint, json=game_state, timeout=timeout)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if "move" in data and isinstance(data["move"], int):
                            logger.info(f"Received valid move from API (HTTP): {data['move']}")
                            return data["move"]
                        else:
                            logger.warning(f"Received invalid move format (HTTP): {data}")
                except Exception as e:
                    logger.error(f"HTTP attempt also failed: {str(e)}")
    except Exception as e:
        logger.error(f"Error getting AI move: {str(e)}")
    
    logger.error("Failed to get valid move from API")
    return None

# WebSocket broadcast functions
async def broadcast_dashboard_update(update_type: str, data: Dict):
    """Broadcast updates to all dashboard WebSocket connections."""
    # Ensure all time values are non-negative
    for key in ["team_a_match_time", "team_b_match_time", "team_a_consumed_time", "team_b_consumed_time"]:
        if key in data and data[key] is not None:
            data[key] = max(0.0, float(data[key]))
    
    # If this is a match update, log the time values
    if update_type == "match_update" and ("team_a_match_time" in data or "team_b_match_time" in data):
        logger.info(f"Broadcasting dashboard time values: A-match={data.get('team_a_match_time', 'N/A')}, " +
                   f"B-match={data.get('team_b_match_time', 'N/A')}, " +
                   f"A-consumed={data.get('team_a_consumed_time', 'N/A')}, " +
                   f"B-consumed={data.get('team_b_consumed_time', 'N/A')}")
    
    # Process consumed_time values in leaderboard data
    if update_type == "leaderboard_update" and "leaderboard" in data:
        for team_data in data["leaderboard"]:
            if "consumed_time" in team_data and team_data["consumed_time"] is not None:
                team_data["consumed_time"] = max(0.0, float(team_data["consumed_time"]))
    
    message = {"type": update_type, **data}
    
    if "/ws/championship/dashboard" in connections:
        for websocket in connections["/ws/championship/dashboard"]:
            await websocket.send_json(message)

async def broadcast_battle_update(match_id: str, data: Dict):
    """Broadcast updates to all WebSocket connections for a specific battle."""
    # Ensure game_state contains game_over and winner information if state is present
    if "state" in data and isinstance(data["state"], dict):
        # If game_over or winner aren't already included in the state
        if "game_over" not in data["state"] or "winner" not in data["state"]:
            # Add these fields with default values if not present
            if "game_over" not in data["state"]:
                data["state"]["game_over"] = data.get("game_over", False)
            if "winner" not in data["state"]:
                data["state"]["winner"] = data.get("winner", None)
    
    # Ensure all time values are non-negative
    for key in ["team_a_match_time", "team_b_match_time", "team_a_consumed_time", "team_b_consumed_time"]:
        if key in data and data[key] is not None:
            data[key] = max(0.0, float(data[key]))
    
    # Log the time values being sent
    if "team_a_match_time" in data or "team_b_match_time" in data:
        logger.info(f"Broadcasting time values: A-match={data.get('team_a_match_time', 'N/A')}, " +
                   f"B-match={data.get('team_b_match_time', 'N/A')}, " +
                   f"A-consumed={data.get('team_a_consumed_time', 'N/A')}, " +
                   f"B-consumed={data.get('team_b_consumed_time', 'N/A')}")
    
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
    
    # Tính toán số trận đấu đồng thời dựa trên số đội
    team_count = len(championship_manager.teams)
    concurrent_matches = 5 if team_count > 10 else (min(team_count // 2, 5) if team_count > 0 else 2)
    
    # Send initial state with time information
    await websocket.send_json({
        "type": "initial_state",
        "status": championship_manager.status,
        "team_count": team_count,
        "current_round": championship_manager.current_round + 1 if championship_manager.rounds else 0,
        "total_rounds": len(championship_manager.rounds) if championship_manager.rounds else 0,
        "leaderboard": championship_manager.get_leaderboard(),
        "schedule": await get_championship_schedule(),
        "turn_time": 10,  # Default turn_time for all matches
        "concurrent_matches": concurrent_matches  # Thêm thông tin số trận đồng thời
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
async def clear_cache_endpoint(request: Request):
    """Manually clear all Redis cache and reset championship data"""
    global championship_manager
    
    # Kiểm tra header bảo mật đơn giản
    admin_token = request.headers.get("Admin-Token")
    if not admin_token or admin_token != "2302":
        raise HTTPException(status_code=403, detail="Không có quyền truy cập API này")
    
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
    """Start the championship manually."""
    # Kiểm tra nếu giải đấu đã bắt đầu rồi
    if championship_manager.status == "in_progress":
        raise HTTPException(status_code=400, detail="Championship is already in progress")
    
    # Cần ít nhất 2 đội để bắt đầu
    if len(championship_manager.teams) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 teams to start")
    
    # Cập nhật semaphore dựa trên số lượng đội
    global match_semaphore
    match_semaphore = await update_match_semaphore()
        
    # Bắt đầu giải đấu sau 10 giây
    background_tasks.add_task(start_championship_after_delay, 10)
    
    return {
        "status": "starting",
        "message": "Championship will start in 10 seconds",
        "team_count": len(championship_manager.teams),
        "concurrent_matches": match_semaphore._value  # Thêm thông tin về số trận đồng thời
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
    
    # Gửi thông tin trận đấu với time data - đảm bảo giá trị không âm
    await websocket.send_json({
        "type": "championship_match_info",
        "team_a": match.team_a,
        "team_b": match.team_b,
        "status": match.status,
        "round": match.round_number + 1,
        "current_game": match.current_game + 1 if match.games else 0,
        "team_a_points": match.team_a_points,
        "team_b_points": match.team_b_points,
        "spectator_count": match.spectator_count,
        "team_a_match_time": max(0, match.team_a_match_time),
        "team_b_match_time": max(0, match.team_b_match_time),
        "team_a_consumed_time": match.team_a_consumed_time,
        "team_b_consumed_time": match.team_b_consumed_time,
        "turn_time": match.turn_time
    })
    
    # Nếu trận đấu có game, gửi thông tin game hiện tại với game_over và winner
    if match.games and match.current_game < len(match.games):
        game = match.games[match.current_game]
        
        # Determine colors based on first_player
        team_a_color = "red" if game.first_player == "team_a" else "yellow"
        team_b_color = "yellow" if game.first_player == "team_a" else "red"
        
        await websocket.send_json({
            "type": "game_info",
            "game_number": game.game_number,
            "first_player": game.first_player,
            "status": game.status,
            "state": game.game_state,
            "game_over": game.game_state.get("game_over", False) if game.game_state else False,
            "winner": game.game_state.get("winner", None) if game.game_state else None,
            "team_a_color": team_a_color,
            "team_b_color": team_b_color
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

@app.get("/api/test")
async def health_check():
    return {"status": "ok", "message": "Server is running"}

# API endpoint to restart a specific round in championship
@app.post("/api/championship/restart-round/{round_number}")
async def restart_championship_round(round_number: int, request: Request, background_tasks: BackgroundTasks):
    """Restart a specific round in the championship, keeping all previous rounds' data."""
    global championship_manager
    
    # Kiểm tra header bảo mật đơn giản
    admin_token = request.headers.get("Admin-Token")
    if not admin_token or admin_token != "2302":
        raise HTTPException(status_code=403, detail="Không có quyền truy cập API này")
    
    try:
        # Kiểm tra số round hợp lệ
        if round_number < 0 or round_number >= len(championship_manager.rounds):
            raise HTTPException(status_code=400, detail=f"Số round không hợp lệ. Hệ thống có {len(championship_manager.rounds)} rounds (0-{len(championship_manager.rounds)-1})")
        
        # Cho phép restart bất kỳ round nào, không chỉ round hiện tại
        # Đặt current_round thành round_number để đảm bảo hệ thống sẽ tiếp tục từ round này
        championship_manager.current_round = round_number
        
        logger.info(f"Đang restart round {round_number} của championship")
        
        # Reset trạng thái của các trận đấu trong round này
        for match_id in championship_manager.rounds[round_number]:
            match = championship_manager.matches.get(match_id)
            if match:
                # Lưu lại kết quả trước khi reset
                old_status = match.status
                old_team_a_points = match.team_a_points
                old_team_b_points = match.team_b_points
                
                # Reset status và kết quả
                match.status = "scheduled"
                
                # Nếu trận đấu đã hoàn thành, điều chỉnh điểm số trên bảng xếp hạng
                if old_status == "finished":
                    # Trừ điểm đã cộng trước đó
                    championship_manager.leaderboard[match.team_a] -= old_team_a_points
                    championship_manager.leaderboard[match.team_b] -= old_team_b_points
                    
                    # Reset điểm số và số liệu thống kê của trận đấu
                    match.team_a_points = 0
                    match.team_b_points = 0
                    match.previous_team_a_points = 0
                    match.previous_team_b_points = 0
                    match.winner = None
                    
                    # Điều chỉnh thống kê thắng/thua/hòa
                    for game in match.games:
                        if game.status == "finished" and hasattr(game, '_stats_counted') and game._stats_counted:
                            if game.winner == "team_a":
                                championship_manager.team_stats[match.team_a]["wins"] -= 1
                                championship_manager.team_stats[match.team_b]["losses"] -= 1
                            elif game.winner == "team_b":
                                championship_manager.team_stats[match.team_b]["wins"] -= 1
                                championship_manager.team_stats[match.team_a]["losses"] -= 1
                            elif game.winner == "draw":
                                championship_manager.team_stats[match.team_a]["draws"] -= 1
                                championship_manager.team_stats[match.team_b]["draws"] -= 1
                            
                            # Reset trạng thái game
                            game.status = "scheduled"
                            game.winner = None
                            game._stats_counted = False
                            game.game_state = None
                
                # Reset thời gian
                match.team_a_match_time = 240.0
                match.team_b_match_time = 240.0
                match.team_a_consumed_time = 0.0
                match.team_b_consumed_time = 0.0
                match.start_time = None
                match.end_time = None
                match.current_game = 0
                
                # Đảm bảo các game đều được reset
                for game in match.games:
                    game.status = "scheduled"
                    game.winner = None
                    if hasattr(game, '_stats_counted'):
                        game._stats_counted = False
                    game.game_state = None
                
                logger.info(f"Đã reset trận đấu {match_id}: {match.team_a} vs {match.team_b}")
        
        # Cập nhật trạng thái championship
        championship_manager.status = "in_progress"
        
        # Bắt đầu lại round sau 5 giây
        background_tasks.add_task(start_round, round_number)
        
        return {
            "success": True,
            "message": f"Đã restart round {round_number}. Round sẽ bắt đầu lại sau 5 giây.",
            "current_round": round_number,
            "matches": [
                {
                    "match_id": match_id,
                    "team_a": championship_manager.matches[match_id].team_a if match_id in championship_manager.matches else "unknown",
                    "team_b": championship_manager.matches[match_id].team_b if match_id in championship_manager.matches else "unknown",
                    "status": championship_manager.matches[match_id].status if match_id in championship_manager.matches else "unknown"
                }
                for match_id in championship_manager.rounds[round_number]
            ]
        }
    except Exception as e:
        logger.error(f"Lỗi khi restart round {round_number}: {e}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi restart round: {str(e)}")

