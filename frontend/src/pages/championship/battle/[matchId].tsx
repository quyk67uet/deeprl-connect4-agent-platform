import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useRouter } from 'next/router';
import Head from 'next/head';
import Link from 'next/link';
import { toast, ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import Board from '../../../app/components/Board';
import styles from '../../../../styles/Championship.module.css';

// WebSocket URL
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';

// Determine if we should use secure WebSocket based on environment - ưu tiên giao thức từ URL
const isSecureConnection = WS_URL.startsWith('wss://') || 
  (typeof window !== 'undefined' && window.location.protocol === 'https:');

// Modified WebSocket endpoint construction - cải thiện để ưu tiên giao thức từ biến môi trường
const getWebSocketUrl = (endpoint: string): string => {
  // Extract base URL without protocol
  const baseUrl = WS_URL.replace(/^wss?:\/\//, '');
  
  // Ưu tiên sử dụng WSS nếu WS_URL đã là WSS
  const protocol = WS_URL.startsWith('wss://') ? 'wss' : (isSecureConnection ? 'wss' : 'ws');
  
  return `${protocol}://${baseUrl}${endpoint}`;
};

// Maximum number of reconnection attempts
const MAX_RECONNECT_ATTEMPTS = 3;
// Reconnection delay in milliseconds
const RECONNECT_DELAY = 2000;

interface GameState {
  board: number[][];
  currentPlayer: number;
  winner: number | null;
  draw: boolean;
}

interface MatchData {
  matchId: string;
  teamA: string;
  teamB: string;
  teamAPoints: number;
  teamBPoints: number;
  status: string;
  round: number;
  currentGame: number;
  spectatorCount: number;
  teamAMatchTime: number;
  teamBMatchTime: number;
  teamAConsumedTime: number;
  teamBConsumedTime: number;
  turnTime: number;
}

interface GameData {
  gameNumber: number;
  firstPlayer: string;
  status: string;
  currentTeam: string;
  teamAColor: string;
  teamBColor: string;
  lastMoveTime?: number;
}

interface MoveData {
  column: number;
  team: string;
}

const ChampionshipBattlePage: React.FC = () => {
  const router = useRouter();
  const { matchId } = router.query;
  
  // Game state
  const [gameState, setGameState] = useState<GameState>({
    board: Array(6).fill(0).map(() => Array(7).fill(0)),
    currentPlayer: 1,
    winner: null,
    draw: false
  });
  
  // Championship match data
  const [matchData, setMatchData] = useState<MatchData>({
    matchId: '',
    teamA: '',
    teamB: '',
    teamAPoints: 0,
    teamBPoints: 0,
    status: 'scheduled',
    round: 0,
    currentGame: 0,
    spectatorCount: 0,
    teamAMatchTime: 240,
    teamBMatchTime: 240,
    teamAConsumedTime: 0,
    teamBConsumedTime: 0,
    turnTime: 10
  });
  
  // Championship game data
  const [gameData, setGameData] = useState<GameData>({
    gameNumber: 1,
    firstPlayer: 'team_a',
    status: 'scheduled',
    currentTeam: 'team_a',
    teamAColor: 'red',
    teamBColor: 'yellow'
  });

  // Last move data for animation and highlighting
  const [lastMove, setLastMove] = useState<MoveData | null>(null);
  
  // Connection state
  const [connected, setConnected] = useState<boolean>(false);
  const [socket, setSocket] = useState<WebSocket | null>(null);
  
  // Refs to track board updates
  const boardRef = useRef<GameState['board']>(Array(6).fill(0).map(() => Array(7).fill(0)));
  const lastMoveRef = useRef<MoveData | null>(null);
  
  // Function to update the board visually with animation
  const updateBoard = useCallback((newBoard: number[][], moveData: MoveData | null) => {
    console.log("Updating board with new state:", newBoard);
    console.log("Last move data:", moveData);
    
    // Always update the board state for championship matches to ensure reactivity
      setGameState(prev => ({
        ...prev,
      board: newBoard.map((row: number[]) => [...row])
      }));
      
      // Update the last move for highlighting
      if (moveData) {
        setLastMove(moveData);
        lastMoveRef.current = moveData;
      console.log(`Highlighted move: Column ${moveData.column} by ${moveData.team}`);
      }
      
      // Update board ref
      boardRef.current = newBoard.map((row: number[]) => [...row]);
  }, []);

  // Connect to WebSocket
  useEffect(() => {
    if (!matchId) return;
    
    // Log detailed environment information to help with debugging
    console.log('Environment details:');
    console.log(' - WS_URL:', WS_URL);
    console.log(' - isSecureConnection:', isSecureConnection);
    console.log(' - Protocol:', typeof window !== 'undefined' ? window.location.protocol : 'unknown');
    console.log(' - matchId:', matchId);
    
    let ws: WebSocket | null = null;
    let reconnectAttempts = 0;
    let reconnectTimeout: NodeJS.Timeout | null = null;
    let forceReload = false; // Biến đánh dấu cần reload trang
    
    const connectWebSocket = () => {
      // Clear any existing reconnection timeout
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
        reconnectTimeout = null;
      }
      
      if (ws) {
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
          ws.close();
        }
        ws = null;
      }
      
      try {
        // Create new WebSocket connection
        const wsUrl = getWebSocketUrl(`/ws/championship/battle/${matchId}`);
        console.log(`Connecting to WebSocket at ${wsUrl} (attempt ${reconnectAttempts + 1}/${MAX_RECONNECT_ATTEMPTS + 1})`);
        
        ws = new WebSocket(wsUrl);
        
        // Set a timeout to detect connection issues
        let connectionTimeoutId = setTimeout(() => {
          if (ws && (ws.readyState === WebSocket.CONNECTING)) {
            console.log('WebSocket connection timeout - forcing close and reconnect');
            ws.close();
            
            // Try to reconnect if under max attempts
            if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
              reconnectAttempts++;
              console.log(`Attempting to reconnect (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`);
              toast.info(`Connection timeout. Reconnecting (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`);
              
              // Set timeout for reconnection with exponential backoff
              const delay = RECONNECT_DELAY * Math.pow(2, reconnectAttempts - 1);
              reconnectTimeout = setTimeout(connectWebSocket, delay);
            } else {
              toast.error('Could not connect to the server. Please refresh the page.', {
                autoClose: false,
                onClick: () => window.location.reload()
              });
            }
          }
        }, 5000);
        
        if (ws) {
          ws.onopen = () => {
            clearTimeout(connectionTimeoutId);
            setConnected(true);
            console.log('Connected to the championship battle server');
            // Reset reconnect attempts on successful connection
            reconnectAttempts = 0;
          };
          
          ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('Received championship battle data:', data);
            
            // Handle match restart message
            if (data.type === 'match_restart') {
              console.log('Match is being restarted, page will reload');
              toast.info(data.message || 'Match is restarting. Page will reload shortly.');
              forceReload = true;
              
              // Delay reload to allow toast to be seen
              setTimeout(() => {
                window.location.reload();
              }, 3000);
              
              return;
            }
            
            // Handle championship match info
            if (data.type === 'championship_match_info') {
              console.log('Updating match info');
              setMatchData({
                matchId: data.match_id,
                teamA: data.team_a,
                teamB: data.team_b,
                teamAPoints: data.team_a_points,
                teamBPoints: data.team_b_points,
                status: data.status,
                round: data.round,
                currentGame: data.current_game,
                spectatorCount: data.spectator_count,
                teamAMatchTime: data.team_a_match_time,
                teamBMatchTime: data.team_b_match_time,
                teamAConsumedTime: data.team_a_consumed_time,
                teamBConsumedTime: data.team_b_consumed_time,
                turnTime: data.turn_time
              });
              return;
            }
            
            // Handle game info for championship matches
            if (data.type === 'game_info') {
              console.log('Updating game info');
              setGameData({
                gameNumber: data.game_number,
                firstPlayer: data.first_player,
                status: data.status,
                currentTeam: data.current_player,
                teamAColor: data.team_a_color,
                teamBColor: data.team_b_color
              });
              
              if (data.state) {
                console.log('Updating game state from game_info');
                // Convert state format
                const gameState = {
                  board: data.state.board,
                  currentPlayer: data.state.current_player,
                  winner: data.state.winner,
                  draw: data.state.game_over && !data.state.winner
                };
                
                // Update the game state and board
                setGameState(gameState);
                boardRef.current = gameState.board.map((row: number[]) => [...row]);
              }
              return;
            }
            
            // Handle game start
            if (data.type === 'game_start') {
              console.log('Game starting:', data.game_number);
              setGameData({
                gameNumber: data.game_number,
                firstPlayer: data.first_player,
                status: 'in_progress',
                currentTeam: data.current_player,
                teamAColor: data.team_a_color,
                teamBColor: data.team_b_color
              });
              
              if (data.state) {
                console.log('Resetting board for new game');
                // Reset board and game state
                const newBoard = data.state.board || Array(6).fill(0).map(() => Array(7).fill(0));
                setGameState({
                  board: newBoard,
                  currentPlayer: data.state.current_player || 1,
                  winner: data.state.winner || null,
                  draw: (data.state.game_over && !data.state.winner) || false
                });
                boardRef.current = newBoard.map((row: number[]) => [...row]);
                setLastMove(null);
                lastMoveRef.current = null;
              }
              
              toast.info(`Game ${data.game_number} started!`);
              return;
            }
            
            // Handle game updates during play
            if (data.type === 'game_update') {
              console.log('Game update received');
              const currentTeam = data.current_player;
              setGameData(prev => ({
                ...prev,
                currentTeam
              }));
              
              if (data.state) {
                console.log('Updating board state from game_update');
                const newBoard = data.state.board;
                const newGameState = {
                  board: newBoard,
                  currentPlayer: data.state.current_player,
                  winner: data.state.winner,
                  draw: data.state.game_over && !data.state.winner
                };
                
                setGameState(newGameState);
                updateBoard(newBoard, null);
              }
              return;
            }
            
            // Handle moves made by teams
            if (data.type === 'move_made') {
              const column = data.column;
              const team = data.team;
              
              console.log(`Move received - ${team} played in column ${column}`);
              
              if (data.state) {
                const newBoard = data.state.board;
                const newGameState = {
                  board: newBoard,
                  currentPlayer: data.state.current_player,
                  winner: data.state.winner,
                  draw: data.state.game_over && !data.state.winner
                };
                
                // Update time data
                if (data.team_a_match_time !== undefined && data.team_b_match_time !== undefined) {
                  setMatchData(prev => ({
                    ...prev,
                    teamAMatchTime: data.team_a_match_time,
                    teamBMatchTime: data.team_b_match_time,
                    teamAConsumedTime: data.team_a_consumed_time,
                    teamBConsumedTime: data.team_b_consumed_time
                  }));
                }
                
                // Explicitly update the board for this move
                updateBoard(newBoard, { column, team });
                setGameState(newGameState);
                
                // Show a toast notification for the move
                const teamName = team === 'team_a' ? matchData.teamA : matchData.teamB;
              }
              return;
            }
            
            // Handle game completion
            if (data.type === 'game_complete') {
              const gameNumber = data.game_number;
              const winner = data.winner;
              
              // Update game data
              setGameData(prev => ({
                ...prev,
                status: 'finished'
              }));
              
              // Update match data with points and time
              setMatchData(prev => ({
                ...prev,
                teamAPoints: data.team_a_points,
                teamBPoints: data.team_b_points,
                teamAMatchTime: data.team_a_match_time,
                teamBMatchTime: data.team_b_match_time,
                teamAConsumedTime: data.team_a_consumed_time,
                teamBConsumedTime: data.team_b_consumed_time
              }));
              
              // Show toast notification
              if (winner === 'team_a') {
                // toast.success(`Game ${gameNumber} won by ${matchData.teamA}!`);
              } else if (winner === 'team_b') {
                // toast.success(`Game ${gameNumber} won by ${matchData.teamB}!`);
              } else {
                // toast.info(`Game ${gameNumber} ended in a draw!`);
              }
              return;
            }
            
            // Handle spectator count updates
            if (data.type === 'spectator_count') {
              setMatchData(prev => ({
                ...prev,
                spectatorCount: data.count
              }));
              console.log(`Spectator count updated: ${data.count}`);
              return;
            }
          };
          
          ws.onclose = (event) => {
            setConnected(false);
            clearTimeout(connectionTimeoutId);
            console.log(`WebSocket closed: ${event.code} ${event.reason || ''}`);
            
            // Nếu đóng kết nối do server yêu cầu reload trang, không thử kết nối lại
            if (forceReload) {
              return;
            }
            
            // Try to reconnect if under max attempts
            if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
              reconnectAttempts++;
              console.log(`WebSocket closed. Reconnecting (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`);
              
              // Set timeout for reconnection with exponential backoff
              const delay = RECONNECT_DELAY * Math.pow(2, reconnectAttempts - 1);
              reconnectTimeout = setTimeout(connectWebSocket, delay);
            } else {
              toast.error('Connection to server lost. Please refresh the page to continue watching.', {
                autoClose: false,
                onClick: () => window.location.reload()
              });
            }
          };
          
          ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            toast.error('Connection error detected. Attempting to reconnect...');
          };
          
          setSocket(ws);
        }
      } catch (error) {
        console.error('Error creating WebSocket connection:', error);
        toast.error('Failed to establish connection. Please refresh the page.', {
          autoClose: false,
          onClick: () => window.location.reload()
        });
      }
    };
    
    // Initial connection
    connectWebSocket();
    
    // Cleanup on component unmount
    return () => {
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
      }
      
      if (ws) {
        ws.close();
      }
    };
  }, [matchId, updateBoard]);
  
  // Function to copy match ID to clipboard
  const copyMatchIdToClipboard = useCallback(() => {
    if (!matchId) return;
    
    if (navigator.clipboard) {
      navigator.clipboard.writeText(String(matchId))
        .then(() => {
          toast.success('Match ID copied to clipboard!');
        })
        .catch(err => {
          console.error('Failed to copy match ID:', err);
          toast.error('Failed to copy match ID.');
        });
    } else {
      // Fallback for browsers that don't support clipboard API
      const textArea = document.createElement('textarea');
      textArea.value = String(matchId);
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      
      try {
        const successful = document.execCommand('copy');
        if (successful) {
          toast.success('Match ID copied to clipboard!');
        } else {
          toast.error('Failed to copy match ID.');
        }
      } catch (err) {
        console.error('Failed to copy match ID:', err);
        toast.error('Failed to copy match ID.');
      }
      
      document.body.removeChild(textArea);
    }
  }, [matchId]);
  
  // Functions to get status messages
  const getStatusMessage = useCallback(() => {
    switch (matchData.status) {
      case 'scheduled':
        return 'Match is scheduled and waiting to start';
      case 'in_progress':
        return `Game ${matchData.currentGame} in progress`;
      case 'finished':
        if (matchData.teamAPoints > matchData.teamBPoints) {
          return `${matchData.teamA} won the match!`;
        } else if (matchData.teamBPoints > matchData.teamAPoints) {
          return `${matchData.teamB} won the match!`;
        } else {
          return 'Match ended in a draw!';
        }
      default:
        return 'Unknown status';
    }
  }, [matchData]);
  
  const getGameStatusMessage = useCallback(() => {
    const { teamA, teamB } = matchData;
    const { gameNumber, firstPlayer, status, currentTeam } = gameData;
    
    if (status === 'scheduled') {
      return `Game ${gameNumber} will start soon`;
    } else if (status === 'in_progress') {
      const currentTeamName = currentTeam === 'team_a' ? teamA : teamB;
      return `Game ${gameNumber}: ${currentTeamName}'s turn`;
    } else if (status === 'finished') {
      if (gameState.winner === 1 && firstPlayer === 'team_a') {
        return `Game ${gameNumber}: ${teamA} won!`;
      } else if (gameState.winner === 1 && firstPlayer === 'team_b') {
        return `Game ${gameNumber}: ${teamB} won!`;
      } else if (gameState.winner === 2 && firstPlayer === 'team_a') {
        return `Game ${gameNumber}: ${teamB} won!`;
      } else if (gameState.winner === 2 && firstPlayer === 'team_b') {
        return `Game ${gameNumber}: ${teamA} won!`;
      } else {
        return `Game ${gameNumber}: Draw!`;
      }
    }
    return '';
  }, [matchData, gameData, gameState]);
  
  // Function to get player colors
  const getPlayerColor = useCallback((playerNumber: number) => {
    const { firstPlayer } = gameData;
    
    if (firstPlayer === 'team_a') {
      return playerNumber === 1 ? gameData.teamAColor : gameData.teamBColor;
    } else {
      return playerNumber === 1 ? gameData.teamBColor : gameData.teamAColor;
    }
  }, [gameData]);
  
  // Function to get player name
  const getPlayerName = useCallback((playerNumber: number) => {
    const { teamA, teamB } = matchData;
    const { firstPlayer } = gameData;
    
    if (firstPlayer === 'team_a') {
      return playerNumber === 1 ? teamA : teamB;
    } else {
      return playerNumber === 1 ? teamB : teamA;
    }
  }, [matchData, gameData]);
  
  return (
    <>
      <Head>
        <title>Championship Match | Connect 4</title>
        <meta name="description" content="Watch a Championship match between AI teams in Connect 4" />
      </Head>
      
      <div className={styles.battleContainer}>
        <div className={styles.header}>
          <h1 className={styles.title}>Championship Match</h1>
          
          <div className={`${styles.connectionStatus} ${!connected ? styles.disconnected : ''}`}>
            {connected ? 'Connected' : 'Disconnected'}
            {connected && <span className={styles.spectatorIndicator}>{matchData.spectatorCount} watching</span>}
          </div>
        </div>
        
        <div className={styles.battleContent}>
          <div className={styles.sidePanel}>
            <div className={styles.matchDetails}>
              <div className={styles.matchRoundCard}>
                <div className={styles.matchRoundLabel}>Round</div>
                <div className={styles.matchRoundValue}>{matchData.round}</div>
              </div>
              
              <div className={styles.spectatorBox}>
                <div className={styles.spectatorLabel}>Spectators</div>
                <div className={styles.spectatorValue}>{matchData.spectatorCount}</div>
              </div>
            </div>
            
            <div className={styles.statusDisplay}>
              <div className={`${styles.statusBadge} ${matchData.status === 'in_progress' ? styles.statusInProgress : 
                              matchData.status === 'finished' ? styles.statusFinished : styles.statusScheduled}`}>
                {matchData.status === 'scheduled' ? 'Scheduled' : 
                matchData.status === 'in_progress' ? 'In Progress' : 'Finished'}
              </div>
              
              <div className={styles.statusMessage}>
                {getStatusMessage()}
              </div>
              
              <div className={styles.gameStatusDetail}>
                {getGameStatusMessage()}
              </div>
            </div>
            
            <div className={styles.movesList}>
              <div className={styles.movesListTitle}>Move History</div>
              <div className={styles.movesListContent}>
                {lastMove ? (
                  <div className={styles.moveItem}>
                    <div className={styles.moveNumber}>Last Move</div>
                    <div className={styles.moveDetails}>
                      <span className={`${styles.moveTeam} ${lastMove.team === 'team_a' ? styles.teamA : styles.teamB}`}>
                        {lastMove.team === 'team_a' ? matchData.teamA : matchData.teamB}
                      </span>
                      <span className={styles.moveAction}>
                        placed in column {lastMove.column + 1}
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className={styles.noMoves}>No moves yet</div>
                )}
              </div>
            </div>
          </div>
          
          <div className={styles.mainContent}>
            <div className={styles.teamsHeader}>
              <div className={`${styles.teamCard} ${gameState.currentPlayer === 1 && gameData.firstPlayer === 'team_a' ? styles.activeTeam : ''}`}>
                <div 
                  className={styles.teamColorBar}
                  style={{ backgroundColor: gameData.teamAColor === 'red' ? '#e74c3c' : '#f1c40f' }}
                ></div>
                <div className={styles.teamInfo}>
              <div 
                className={styles.teamName}
                style={{ color: gameData.teamAColor === 'red' ? '#e74c3c' : '#f1c40f' }}
              >
                {matchData.teamA}
              </div>
                  <div className={styles.teamColorLabel}>
                    {gameData.teamAColor === 'red' ? '🔴 Red' : '🟡 Yellow'}
              </div>
              <div className={styles.teamScore}>{matchData.teamAPoints}</div>
                  <div style={{ fontSize: '0.8rem', marginTop: '0.5rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span>Match Time:</span>
                      <span className={matchData.teamAMatchTime < 60 ? styles.dangerText : ''}>
                        {Math.floor((matchData.teamAMatchTime || 0) / 60)}:
                        {Math.max(0, (matchData.teamAMatchTime || 0) % 60).toFixed(0).padStart(2, '0')}
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span>Time Used:</span>
                      <span>{typeof matchData.teamAConsumedTime === 'number' ? matchData.teamAConsumedTime.toFixed(2) : '0.00'}s</span>
                    </div>
                  </div>
                </div>
                {gameState.currentPlayer === 1 && gameData.firstPlayer === 'team_a' && 
                  <div className={styles.thinkingIndicator}>Thinking...</div>
                }
            </div>
            
              <div className={styles.versusContainer}>
                <div className={styles.versusText}>VS</div>
                <div className={styles.gameCount}>Game {gameData.gameNumber} of 4</div>
                <div className={styles.gameState}>
                  {gameData.status === 'in_progress' ? 
                    <span className={styles.gameInProgress}>In Progress</span> : 
                    gameData.status === 'finished' ? 
                    <span className={styles.gameFinished}>Completed</span> : 
                    <span className={styles.gameScheduled}>Starting Soon</span>
                  }
                </div>
                <div style={{ fontSize: '0.8rem', marginTop: '0.5rem', textAlign: 'center' }}>
                  <span>Turn Time: {matchData.turnTime}s</span>
                </div>
              </div>
              
              <div className={`${styles.teamCard} ${gameState.currentPlayer === 2 && gameData.firstPlayer === 'team_a' ? styles.activeTeam : 
                              gameState.currentPlayer === 1 && gameData.firstPlayer === 'team_b' ? styles.activeTeam : ''}`}>
                <div 
                  className={styles.teamColorBar}
                  style={{ backgroundColor: gameData.teamBColor === 'red' ? '#e74c3c' : '#f1c40f' }}
                ></div>
                <div className={styles.teamInfo}>
              <div 
                className={styles.teamName}
                style={{ color: gameData.teamBColor === 'red' ? '#e74c3c' : '#f1c40f' }}
              >
                {matchData.teamB}
              </div>
                  <div className={styles.teamColorLabel}>
                    {gameData.teamBColor === 'red' ? '🔴 Red' : '🟡 Yellow'}
              </div>
              <div className={styles.teamScore}>{matchData.teamBPoints}</div>
                  <div style={{ fontSize: '0.8rem', marginTop: '0.5rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span>Match Time:</span>
                      <span className={matchData.teamBMatchTime < 60 ? styles.dangerText : ''}>
                        {Math.floor((matchData.teamBMatchTime || 0) / 60)}:
                        {Math.max(0, (matchData.teamBMatchTime || 0) % 60).toFixed(0).padStart(2, '0')}
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span>Time Used:</span>
                      <span>{typeof matchData.teamBConsumedTime === 'number' ? matchData.teamBConsumedTime.toFixed(2) : '0.00'}s</span>
                    </div>
                  </div>
                </div>
                {(gameState.currentPlayer === 2 && gameData.firstPlayer === 'team_a' || 
                  gameState.currentPlayer === 1 && gameData.firstPlayer === 'team_b') && 
                  <div className={styles.thinkingIndicator}>Thinking...</div>
                }
              </div>
            </div>
            
            <div className={styles.boardArea}>
              <div className={styles.boardContainer}>
                <div className={styles.gameBanner}>
                  Game {gameData.gameNumber} of 4 • 
                  {gameData.status === 'in_progress' ? 
                    <span> Playing • Turn: {gameState.currentPlayer === 1 ? 
                      (gameData.firstPlayer === 'team_a' ? matchData.teamA : matchData.teamB) : 
                      (gameData.firstPlayer === 'team_a' ? matchData.teamB : matchData.teamA)}</span> : 
                    gameData.status === 'finished' ? ' Completed' : ' Starting soon'}
          </div>
          
                <Board
                  board={gameState.board}
                  currentPlayer={gameState.currentPlayer}
                  playerTurn={false}
                  makeMove={() => {}} // No moves allowed - this is a view-only component
                  againstAgent={false}
                  lastMoveColumn={lastMove?.column}
                />
                
                <div className={styles.gameInfo}>
                  <div className={styles.teamLegend}>
                    <div className={styles.legendItem}>
                      <div 
                        className={styles.colorIndicator}
                        style={{ backgroundColor: gameData.teamAColor === 'red' ? '#e74c3c' : '#f1c40f' }}
                      ></div>
                      <span>{matchData.teamA} {gameData.teamAColor === 'red' ? '(Red)' : '(Yellow)'}</span>
            </div>
                    <div className={styles.legendItem}>
                      <div 
                        className={styles.colorIndicator}
                        style={{ backgroundColor: gameData.teamBColor === 'red' ? '#e74c3c' : '#f1c40f' }}
                      ></div>
                      <span>{matchData.teamB} {gameData.teamBColor === 'red' ? '(Red)' : '(Yellow)'}</span>
            </div>
          </div>
          
                  <div className={styles.moveHistory}>
                    {lastMove && (
                      <div className={styles.lastMoveInfo}>
                        <span className={styles.moveLabel}>Last move:</span> 
                        <span className={styles.moveDetail}>
                          {lastMove.team === 'team_a' ? matchData.teamA : matchData.teamB} placed in column {lastMove.column + 1}
                        </span>
            </div>
                    )}
            </div>
          </div>
        </div>
            </div>
          </div>
        </div>
        
        <div className={styles.championshipActions}>
          <Link href="/championship/dashboard" className={styles.backLink}>
            Back to Dashboard
          </Link>
        </div>
      </div>
      
      <ToastContainer position="bottom-right" autoClose={500} />
    </>
  );
};

export default ChampionshipBattlePage; 