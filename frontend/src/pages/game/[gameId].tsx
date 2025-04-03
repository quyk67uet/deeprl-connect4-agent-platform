import React, { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/router';
import Head from 'next/head';
import Link from 'next/link';
import { toast, ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import Board from '../../app/components/Board';
import GameControls from '../../app/components/GameControls';
import styles from '../../../styles/Game.module.css';

// WebSocket server URL
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';

interface GameState {
  board: number[][];
  currentPlayer: number;
  winner: number | null;
  draw: boolean;
}

const GamePage: React.FC = () => {
  const router = useRouter();
  const { gameId } = router.query;
  
  const [gameState, setGameState] = useState<GameState>({
    board: Array(6).fill(0).map(() => Array(7).fill(0)),
    currentPlayer: 1,
    winner: null,
    draw: false
  });
  
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [playerNumber, setPlayerNumber] = useState<number>(0);
  const [connected, setConnected] = useState<boolean>(false);
  const [againstAgent, setAgainstAgent] = useState<boolean>(false);
  const [spectatorCount, setSpectatorCount] = useState<number>(1);
  
  // Connect to WebSocket
  useEffect(() => {
    if (!gameId) return;
    
    const ws = new WebSocket(`${WS_URL}/ws/${gameId}`);
    
    ws.onopen = () => {
      setConnected(true);
      console.log('Connected to the game server');
    };
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log('Received:', data);
      
      switch (data.type) {
        case 'game_state':
          console.log("Raw state from server:", data.state);
          
          // Đảm bảo cập nhật đúng cấu trúc của gameState
          const newState = {
            board: data.state.board || Array(6).fill(0).map(() => Array(7).fill(0)),
            currentPlayer: data.state.current_player || 1,
            winner: data.state.winner,
            draw: data.state.game_over && !data.state.winner,
          };
          
          console.log("Parsed state:", newState);
          setGameState(newState);
          setPlayerNumber(data.your_player);
          setAgainstAgent(data.agent_mode);
          if (data.spectator_count) {
            setSpectatorCount(data.spectator_count);
          }
          console.log("Updated game state:", newState);
          console.log("Your player:", data.your_player);
          console.log("Agent mode:", data.agent_mode);
          break;
          
        case 'game_update':
          // Đảm bảo cập nhật đúng cấu trúc của gameState
          const updatedState = {
            board: data.state.board || gameState.board,
            currentPlayer: data.state.current_player || gameState.currentPlayer,
            winner: data.state.winner,
            draw: data.state.game_over && !data.state.winner,
          };
          
          console.log("Parsed update:", updatedState);
          setGameState(updatedState);
          console.log("Game updated:", updatedState);
          if (data.ai_move !== undefined) {
            toast.info(`AI played in column ${data.ai_move + 1}`);
            console.log("AI move:", data.ai_move);
          }
          break;
          
        case 'player_joined':
          toast.success(`Player ${data.player} joined the game`);
          break;
          
        case 'player_left':
          toast.info(`Player ${data.player} left the game`);
          break;
          
        case 'spectator_count':
          setSpectatorCount(data.count);
          toast.info(`${data.count} players/spectators are connected`);
          break;
      }
    };
    
    ws.onclose = () => {
      setConnected(false);
      console.log('Disconnected from the game server');
    };
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      toast.error('Connection error. Please try again later.');
    };
    
    setSocket(ws);
    
    return () => {
      ws.close();
    };
  }, [gameId]);
  
  // Make a move
  const makeMove = useCallback((column: number) => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      console.log("Sending move command:", column);
      socket.send(JSON.stringify({
        type: 'make_move',
        column: column
      }));
    } else {
      console.error("Socket not ready:", socket ? socket.readyState : "no socket");
    }
  }, [socket]);
  
  // Reset game
  const resetGame = useCallback(() => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({
        type: 'reset_game'
      }));
    }
  }, [socket]);
  
  // Start game against AI
  const startAgentGame = useCallback(() => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({
        type: 'start_agent_game'
      }));
      setAgainstAgent(true);
    }
  }, [socket]);
  
  // Copy game ID to clipboard
  const copyGameId = useCallback(() => {
    if (gameId) {
      navigator.clipboard.writeText(gameId.toString())
        .then(() => toast.success('Game ID copied to clipboard!'))
        .catch(err => toast.error('Failed to copy Game ID'));
    }
  }, [gameId]);
  
  // Game status message
  const getStatusMessage = () => {
    if (gameState.winner) {
      return `Player ${gameState.winner} wins!`;
    } else if (gameState.draw) {
      return 'Game ended in a draw!';
    } else {
      const currentPlayerText = gameState.currentPlayer === playerNumber ? 'Your' : `Player ${gameState.currentPlayer}'s`;
      return `${currentPlayerText} turn`;
    }
  };
  
  // Check if it's player's turn - allow player 1 to make moves in agent mode
  const isPlayerTurn = 
    // Điều kiện thông thường: người chơi hiện tại là player đang đăng nhập
    (gameState.currentPlayer === playerNumber && !gameState.winner && !gameState.draw) ||
    // Hoặc trong chế độ agent: player 1 và lượt hiện tại là player 1
    (againstAgent && playerNumber === 1 && gameState.currentPlayer === 1 && !gameState.winner && !gameState.draw);
  
  // Debug thông tin trước khi render
  console.log("Rendering with gameState:", gameState);
  console.log("Current player from gameState:", gameState.currentPlayer);
  console.log("Player number:", playerNumber);
  console.log("Agent mode:", againstAgent);
  console.log("Is player turn:", isPlayerTurn);
  
  // Loading state
  if (!gameId) {
    return <div className={styles.loading}>Loading...</div>;
  }
  
  return (
    <>
      <Head>
        <title>Connect 4 - Game {gameId}</title>
      </Head>
      
      <div className={styles.gameContainer}>
        <div className={styles.status}>
          <div className={styles.statusText}>{getStatusMessage()}</div>
          <div className={styles.connectionStatus} style={{ backgroundColor: connected ? '#28a745' : '#dc3545' }}>
            {connected ? 'Connected' : 'Disconnected'}
            {connected && (
              <span style={{ 
                display: 'inline-flex', 
                alignItems: 'center', 
                fontSize: '0.8rem', 
                opacity: 0.9 
              }}>
                <span style={{ marginRight: '3px' }}>👁️</span> {spectatorCount} watching
              </span>
            )}
          </div>
        </div>
        
        <div className={styles.gameContent}>
          <div className={styles.gameBoard}>
            <Board
              board={gameState.board}
              currentPlayer={gameState.currentPlayer}
              playerTurn={isPlayerTurn}
              makeMove={makeMove}
              againstAgent={againstAgent}
            />
          </div>
          
          <div className={styles.gameControlsContainer}>
            <GameControls
              gameId={gameId.toString()}
              againstAgent={againstAgent}
              onStartAgentGame={startAgentGame}
              onResetGame={resetGame}
              copyGameId={copyGameId}
            />
            
            <div className={styles.navigation}>
              <Link href="/" className={styles.backLink}>
                ← Back to Home
              </Link>
            </div>
          </div>
        </div>
      </div>
      
      <ToastContainer position="bottom-right" autoClose={3000} />
    </>
  );
};

export default GamePage;