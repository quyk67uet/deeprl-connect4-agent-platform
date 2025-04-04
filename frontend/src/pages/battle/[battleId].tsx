import React, { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/router';
import Head from 'next/head';
import Link from 'next/link';
import { toast, ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import Board from '../../app/components/Board';
import styles from '../../../styles/Battle.module.css';

// WebSocket URL
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';

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

interface BattleState {
  gameState: GameState;
  status: string;
  currentTurn: number;
  ai1Url: string | null;
  ai2Url: string | null;
  lastMove?: number;
  movingPlayer?: number;
}

const BattlePage: React.FC = () => {
  const router = useRouter();
  const { battleId } = router.query;
  
  // Battle state
  const [battleState, setBattleState] = useState<BattleState>({
    gameState: {
      board: Array(6).fill(0).map(() => Array(7).fill(0)),
      currentPlayer: 1,
      winner: null,
      draw: false
    },
    status: 'waiting',
    currentTurn: 0,
    ai1Url: null,
    ai2Url: null
  });
  
  // Form inputs
  const [ai1Input, setAi1Input] = useState<string>('');
  const [ai2Input, setAi2Input] = useState<string>('');
  const [maxTurns, setMaxTurns] = useState<number>(50);

  // Connection state
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [connected, setConnected] = useState<boolean>(false);
  
  // Spectator count
  const [spectatorCount, setSpectatorCount] = useState<number>(1);
  
  // Connect to WebSocket
  useEffect(() => {
    if (!battleId) return;
    
    let ws: WebSocket | null = null;
    let reconnectAttempts = 0;
    let reconnectTimeout: NodeJS.Timeout | null = null;
    
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
        console.log(`Connecting to WebSocket at ${WS_URL}/ws/battle/${battleId}`);
        ws = new WebSocket(`${WS_URL}/ws/battle/${battleId}`);
        
        // Set a timeout to detect connection issues
        const connectionTimeout = setTimeout(() => {
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
            }
          }
        }, 5000); // 5 second timeout
        
        if (ws) {
          ws.onopen = () => {
            clearTimeout(connectionTimeout);
            setConnected(true);
            console.log('Connected to the battle server');
            // Reset reconnect attempts on successful connection
            reconnectAttempts = 0;
          };
          
          ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('Received battle data:', data);
            
            if (data.type === 'battle_state' || data.type === 'battle_update' || data.type === 'battle_complete') {
              // Convert state format
              const gameState = {
                board: data.state.board,
                currentPlayer: data.state.current_player,
                winner: data.state.winner,
                draw: data.state.game_over && !data.state.winner
              };
              
              // Update battle state
              setBattleState(prev => ({
                ...prev,
                gameState,
                status: data.status,
                currentTurn: data.current_turn,
                ai1Url: data.ai1_url,
                ai2Url: data.ai2_url,
                lastMove: data.last_move,
                movingPlayer: data.moving_player
              }));
              
              // Update spectator count if provided
              if (data.spectator_count) {
                setSpectatorCount(data.spectator_count);
              }
              
              // Show notifications for events
              if (data.type === 'battle_update' && data.last_move !== undefined) {
                const player = data.moving_player === 1 ? 'Red' : 'Yellow';
                toast.info(`${player} played in column ${data.last_move + 1}`);
              }
              
              if (data.type === 'battle_complete') {
                if (data.status === 'player1_win') {
                  toast.success('Red AI wins!');
                } else if (data.status === 'player2_win') {
                  toast.success('Yellow AI wins!');
                } else if (data.status === 'draw') {
                  toast.info('Game ended in a draw!');
                }
              }
            }
            else if (data.type === 'player_joined') {
              toast.info(`Someone joined to watch the battle`);
            }
            else if (data.type === 'spectator_count') {
              setSpectatorCount(data.count);
              toast.info(`${data.count} spectators are watching this battle`);
            }
            else if (data.type === 'player_left') {
              toast.info(`Someone left the battle`);
            }
          };
          
          ws.onclose = (event) => {
            setConnected(false);
            console.log(`Disconnected from the battle server: ${event.code} ${event.reason}`);
            
            // Attempt to reconnect if not cleanly closed and under max attempts
            if (!event.wasClean && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
              reconnectAttempts++;
              console.log(`Attempting to reconnect (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`);
              toast.info(`Connection lost. Reconnecting (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`);
              
              // Set timeout for reconnection with exponential backoff
              const delay = RECONNECT_DELAY * Math.pow(2, reconnectAttempts - 1);
              reconnectTimeout = setTimeout(connectWebSocket, delay);
            } else if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
              toast.error('Failed to connect after multiple attempts. Please refresh the page.');
            }
          };
          
          ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            // Don't show toast here as onclose will also be called
          };
        }
        
        setSocket(ws);
      } catch (error) {
        console.error('WebSocket connection error:', error);
        // Don't show toast here as onclose will also be called
      }
    };
    
    // Start the initial connection
    connectWebSocket();
    
    return () => {
      // Clean up
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
      }
      
      if (ws) {
        // Set a flag to prevent reconnection attempts on intentional closure
        ws.onclose = null;
        ws.close();
      }
    };
  }, [battleId]);
  
  // Start battle
  const startBattle = useCallback(() => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      // Get AI URLs and ensure they are correctly formatted
      let ai1Url: string | null = ai1Input.trim();
      let ai2Url: string | null = ai2Input.trim();
      
      if (ai1Url && !ai1Url.includes('/api/connect4-move')) {
        if (ai1Url.endsWith('/')) {
          ai1Url = ai1Url.slice(0, -1);
        }
        ai1Url = `${ai1Url}/api/connect4-move`;
      }
      
      if (ai2Url && !ai2Url.includes('/api/connect4-move')) {
        if (ai2Url.endsWith('/')) {
          ai2Url = ai2Url.slice(0, -1);
        }
        ai2Url = `${ai2Url}/api/connect4-move`;
      }
      
      // Empty strings to null
      ai1Url = ai1Url === '' ? null : ai1Url;
      ai2Url = ai2Url === '' ? null : ai2Url;
      
      // Log for debugging
      console.log("Sending AI URLs:", { ai1_url: ai1Url, ai2_url: ai2Url });
      
      // Send start battle command
      const message = {
        type: 'start_battle',
        ai1_url: ai1Url,
        ai2_url: ai2Url,
        max_turns: maxTurns
      };
      
      console.log("Sending WebSocket message:", message);
      socket.send(JSON.stringify(message));
      
      toast.info('Starting AI battle!');
    }
  }, [socket, ai1Input, ai2Input, maxTurns]);
  
  // Reset battle
  const resetBattle = useCallback(() => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({
        type: 'reset_battle'
      }));
      
      toast.info('Battle reset!');
    }
  }, [socket]);
  
  // Copy battle ID to clipboard
  const copyBattleId = useCallback(() => {
    if (battleId) {
      navigator.clipboard.writeText(battleId.toString())
        .then(() => toast.success('Battle ID copied to clipboard!'))
        .catch(err => toast.error('Failed to copy Battle ID'));
    }
  }, [battleId]);
  
  // Get status message
  const getStatusMessage = () => {
    if (battleState.status === 'waiting') {
      return 'Waiting to start...';
    } else if (battleState.status === 'in_progress') {
      return `Turn ${battleState.currentTurn}: ${battleState.gameState.currentPlayer === 1 ? 'Red' : 'Yellow'} thinking...`;
    } else if (battleState.status === 'player1_win') {
      return 'Red AI wins!';
    } else if (battleState.status === 'player2_win') {
      return 'Yellow AI wins!';
    } else if (battleState.status === 'draw') {
      return 'Game ended in a draw!';
    }
    return 'Unknown state';
  };
  
  // Loading state
  if (!battleId) {
    return <div className={styles.loading}>Loading...</div>;
  }
  
  return (
    <>
      <Head>
        <title>Connect 4 - AI Battle {battleId}</title>
      </Head>
      
      <div className={styles.battleContainer}>
        <div className={styles.status}>
          <div className={styles.statusText}>{getStatusMessage()}</div>
          <div className={`${styles.connectionStatus} ${!connected ? styles.disconnected : ''}`}>
            {connected ? 'Connected' : 'Disconnected'}
            {connected && <span className={styles.viewerCount}>{spectatorCount} watching</span>}
          </div>
        </div>
        
        <div className={styles.battleContent}>
          <div className={styles.gameBoard}>
            <Board
              board={battleState.gameState.board}
              currentPlayer={battleState.gameState.currentPlayer}
              playerTurn={false} // No player moves in AI battle
              makeMove={() => {}} // No-op
              againstAgent={false}
            />
          </div>
          
          <div className={styles.battleControlsContainer}>
            <div className={styles.aiSetup}>
              <h3>Configure AI Battle</h3>
              
              <div className={styles.aiConfig}>
                <div className={styles.formGroup}>
                  <label htmlFor="ai1">Red AI Endpoint (Optional):</label>
                  <input
                    id="ai1"
                    type="text"
                    value={ai1Input}
                    onChange={(e) => setAi1Input(e.target.value)}
                    placeholder="https://your-ai-endpoint.com/move"
                    className={styles.input}
                    disabled={battleState.status === 'in_progress'}
                  />
                </div>
                
                <div className={styles.formGroup}>
                  <label htmlFor="ai2">Yellow AI Endpoint (Optional):</label>
                  <input
                    id="ai2"
                    type="text"
                    value={ai2Input}
                    onChange={(e) => setAi2Input(e.target.value)}
                    placeholder="https://your-ai-endpoint.com/move"
                    className={styles.input}
                    disabled={battleState.status === 'in_progress'}
                  />
                </div>
                
                <div className={styles.formGroup}>
                  <label htmlFor="maxTurns">Max Turns:</label>
                  <input
                    id="maxTurns"
                    type="number"
                    min="10"
                    max="100"
                    value={maxTurns}
                    onChange={(e) => setMaxTurns(parseInt(e.target.value) || 50)}
                    className={styles.input}
                    disabled={battleState.status === 'in_progress'}
                  />
                </div>
                
                <div className={styles.aiNote}>
                  <p>
                    <strong>Note:</strong> If no AI endpoint is provided, the default server AI will be used.
                    Your AI endpoint should accept POST requests with:
                  </p>
                  <div className={styles.jsonDisplay}>
                    <span className={styles.jsonSymbol}>{"{"}</span>
                    <br />
                    <span className={styles.jsonKey}>"board"</span><span className={styles.jsonSymbol}>: </span><span className={styles.jsonValue}>[[0,0,0,...], [...], ...]</span>,
                    <br />
                    <span className={styles.jsonKey}>"current_player"</span><span className={styles.jsonSymbol}>: </span><span className={styles.jsonValue}>1|2</span>,
                    <br />
                    <span className={styles.jsonKey}>"valid_moves"</span><span className={styles.jsonSymbol}>: </span><span className={styles.jsonValue}>[0,1,2,...]</span>
                    <br />
                    <span className={styles.jsonSymbol}>{"}"}</span>
                  </div>
                  <p>and return:</p>
                  <div className={styles.jsonDisplay}>
                    <span className={styles.jsonSymbol}>{"{"}</span>
                    <br />
                    <span className={styles.jsonKey}>"move"</span><span className={styles.jsonSymbol}>: </span><span className={styles.jsonValue}>columnIndex</span>
                    <br />
                    <span className={styles.jsonSymbol}>{"}"}</span>
                  </div>
                </div>
              </div>
              
              <div className={styles.battleActions}>
                <button
                  className={`${styles.button} ${styles.startButton}`}
                  onClick={startBattle}
                  disabled={!connected || battleState.status === 'in_progress'}
                >
                  {battleState.status === 'waiting' ? 'Start Battle' : 'Restart Battle'}
                </button>
                
                <button
                  className={styles.button}
                  onClick={resetBattle}
                  disabled={!connected || battleState.status === 'waiting'}
                >
                  Reset Board
                </button>
              </div>
            </div>
            
            <div className={styles.battleInfo}>
              <div className={styles.infoItem}>
                <span>Battle ID:</span>
                <div className={styles.idContainer}>
                  <span className={styles.id}>{battleId}</span>
                  <button className={styles.copyButton} onClick={copyBattleId}>
                    Copy
                  </button>
                </div>
              </div>
              
              <div className={styles.infoItem}>
                <span>Status:</span>
                <span className={styles.statusValue}>{battleState.status}</span>
              </div>
              
              <div className={styles.infoItem}>
                <span>Turn:</span>
                <span>{battleState.currentTurn}</span>
              </div>
            </div>
            
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

export default BattlePage; 