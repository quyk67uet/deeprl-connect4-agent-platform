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
  
  // Championship match state
  const [isChampionshipMatch, setIsChampionshipMatch] = useState<boolean>(false);
  const [championshipData, setChampionshipData] = useState<{
    teamA: string;
    teamB: string;
    status: string;
    round: number;
    currentGame: number;
    teamAPoints: number;
    teamBPoints: number;
  }>({
    teamA: '',
    teamB: '',
    status: '',
    round: 0,
    currentGame: 0,
    teamAPoints: 0,
    teamBPoints: 0
  });
  const [championshipGameData, setChampionshipGameData] = useState<{
    gameNumber: number;
    firstPlayer: string;
    status: string;
    teamAColor?: string;
    teamBColor?: string;
    currentTeam?: number;
  }>({
    gameNumber: 0,
    firstPlayer: '',
    status: ''
  });

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
            
            // Handle championship match info
            if (data.type === 'championship_match_info') {
              // This is a championship match
              setIsChampionshipMatch(true);
              setChampionshipData({
                teamA: data.team_a,
                teamB: data.team_b,
                status: data.status,
                round: data.round,
                currentGame: data.current_game,
                teamAPoints: data.team_a_points,
                teamBPoints: data.team_b_points
              });
              
              // Update spectator count
              setSpectatorCount(data.spectator_count);
              
              return;
            }
            
            // Handle game info for championship matches
            if (data.type === 'game_info') {
              setChampionshipGameData({
                gameNumber: data.game_number,
                firstPlayer: data.first_player,
                status: data.status
              });
              
              if (data.state) {
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
                  gameState
                }));
              }
              
              return;
            }
            
            // Handle regular battle updates
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
            // Handle championship match updates
            else if (data.type === 'game_start') {
              // Update championship game data
              setChampionshipGameData({
                gameNumber: data.game_number,
                firstPlayer: data.first_player,
                status: 'in_progress',
                teamAColor: data.team_a_color,
                teamBColor: data.team_b_color
              });
              
              // Update game state
              if (data.state) {
                const gameState = {
                  board: data.state.board,
                  currentPlayer: data.state.current_player,
                  winner: data.state.winner,
                  draw: data.state.game_over && !data.state.winner
                };
                
                setBattleState(prev => ({
                  ...prev,
                  gameState
                }));
              }
              
              toast.info(`Game ${data.game_number} starting - ${data.first_player === 'team_a' ? championshipData.teamA : championshipData.teamB} goes first`);
            }
            else if (data.type === 'game_update') {
              // Update game state
              if (data.state) {
                const gameState = {
                  board: data.state.board,
                  currentPlayer: data.state.current_player,
                  winner: data.state.winner,
                  draw: data.state.game_over && !data.state.winner
                };
                
                setBattleState(prev => ({
                  ...prev,
                  gameState
                }));
              }
              
              // Update championship game turn info
              setChampionshipGameData(prev => ({
                ...prev,
                currentTeam: data.current_player
              }));
            }
            else if (data.type === 'move_made') {
              // A move was made in a championship game
              if (data.state) {
                const gameState = {
                  board: data.state.board,
                  currentPlayer: data.state.current_player,
                  winner: data.state.winner,
                  draw: data.state.game_over && !data.state.winner
                };
                
                setBattleState(prev => ({
                  ...prev,
                  gameState
                }));
              }
              
              const teamName = data.team === 'team_a' ? championshipData.teamA : championshipData.teamB;
              toast.info(`${teamName} played in column ${data.column + 1}`);
            }
            else if (data.type === 'game_complete') {
              // A game in the championship match finished
              setChampionshipData(prev => ({
                ...prev,
                teamAPoints: data.team_a_points,
                teamBPoints: data.team_b_points
              }));
              
              setChampionshipGameData(prev => ({
                ...prev,
                status: 'finished'
              }));
              
              // Show winner notification
              if (data.winner === 'team_a') {
                toast.success(`${championshipData.teamA} wins Game ${data.game_number}!`);
              } else if (data.winner === 'team_b') {
                toast.success(`${championshipData.teamB} wins Game ${data.game_number}!`);
              } else {
                toast.info(`Game ${data.game_number} ended in a draw!`);
              }
            }
            else if (data.type === 'spectator_count') {
              // Update spectator count
              setSpectatorCount(data.count);
              toast.info(`${data.count} spectators are watching this battle`);
            }
            else if (data.type === 'player_joined') {
              // Display notification when a new spectator joins
              toast.info(`Someone joined to watch the battle`);
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
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(battleId.toString())
          .then(() => toast.success('Battle ID copied to clipboard!'))
          .catch(err => {
            fallbackCopyTextToClipboard(battleId.toString());
          });
      } else {
        fallbackCopyTextToClipboard(battleId.toString());
      }
    }
  }, [battleId]);

  const fallbackCopyTextToClipboard = (text: string) => {
    try {
      const textArea = document.createElement('textarea');
      textArea.value = text;
      
      textArea.style.position = 'fixed';
      textArea.style.top = '0';
      textArea.style.left = '0';
      textArea.style.width = '2em';
      textArea.style.height = '2em';
      textArea.style.padding = '0';
      textArea.style.border = 'none';
      textArea.style.outline = 'none';
      textArea.style.boxShadow = 'none';
      textArea.style.background = 'transparent';
      
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      
      const successful = document.execCommand('copy');
      
      document.body.removeChild(textArea);
      
      if (successful) {
        toast.success('Battle ID copied to clipboard!');
      } else {
        toast.error('Failed to copy Battle ID. Please copy it manually.');
      }
    } catch (err) {
      toast.error('Failed to copy Battle ID. Please copy it manually.');
    }
  };
  
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
  
  // Get championship status message
  const getChampionshipStatusMessage = () => {
    if (championshipData.status === 'waiting') {
      return 'Waiting for match to start';
    } else if (championshipData.status === 'in_progress') {
      return `Game ${championshipGameData.gameNumber}/4: ` + 
        (championshipGameData.status === 'in_progress' 
          ? `${championshipGameData.currentTeam === 1 ? championshipData.teamA : championshipData.teamB}'s turn` 
          : 'Preparing next game');
    } else if (championshipData.status === 'finished') {
      let winner = '';
      if (championshipData.teamAPoints > championshipData.teamBPoints) {
        winner = championshipData.teamA;
      } else if (championshipData.teamBPoints > championshipData.teamAPoints) {
        winner = championshipData.teamB;
      } else {
        winner = 'Draw';
      }
      return `Match finished - ${winner}`;
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
          <div className={styles.statusText}>
            {isChampionshipMatch ? getChampionshipStatusMessage() : getStatusMessage()}
          </div>
          <div className={`${styles.connectionStatus} ${!connected ? styles.disconnected : ''}`}>
            {connected ? 'Connected' : 'Disconnected'}
            {connected && <span className={styles.viewerCount}>{spectatorCount} watching</span>}
          </div>
        </div>
        
        <div className={styles.battleContent}>
          {/* Championship match info header, only shown for championship matches */}
          {isChampionshipMatch && (
            <div className={styles.championshipInfo}>
              <div className={styles.matchDetails}>
                <h2>Championship Match</h2>
                <div className={styles.round}>Round {championshipData.round}</div>
                
                <div className={styles.teamsScore}>
                  <div className={styles.teamInfo}>
                    <div className={styles.teamName}>
                      <span className={styles.redTeam}>{championshipData.teamA}</span>
                    </div>
                    <div className={styles.teamPoints}>{championshipData.teamAPoints}</div>
                  </div>
                  
                  <div className={styles.scoreSeparator}>vs</div>
                  
                  <div className={styles.teamInfo}>
                    <div className={styles.teamName}>
                      <span className={styles.yellowTeam}>{championshipData.teamB}</span>
                    </div>
                    <div className={styles.teamPoints}>{championshipData.teamBPoints}</div>
                  </div>
                </div>
                
                <div className={styles.gameInfo}>
                  {championshipGameData.gameNumber > 0 && (
                    <>
                      <div className={styles.gameNumber}>
                        Game {championshipGameData.gameNumber}/4
                      </div>
                      <div className={styles.firstPlayer}>
                        {championshipGameData.firstPlayer === 'team_a' 
                          ? championshipData.teamA 
                          : championshipData.teamB} goes first
                        {championshipGameData.teamAColor && (
                          <span className={styles.colorInfo}>
                            ({championshipData.teamA}: {championshipGameData.teamAColor}, 
                            {championshipData.teamB}: {championshipGameData.teamBColor})
                          </span>
                        )}
                      </div>
                    </>
                  )}
                </div>
              </div>
            </div>
          )}
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
            {!isChampionshipMatch ? (
              /* Regular AI battle controls */
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
            ) : (
              /* Championship match controls */
              <div className={styles.championshipControls}>
                <h3>Championship Match</h3>
                
                <div className={styles.matchSummary}>
                  <p>
                    You are watching a championship match between <strong>{championshipData.teamA}</strong> and <strong>{championshipData.teamB}</strong>.
                  </p>
                  
                  <p>
                    This match consists of 4 games with alternating first player. 
                    Each game win is worth 1 point, a draw is 0.5 points.
                  </p>
                  
                  {championshipData.status === 'finished' && (
                    <div className={styles.matchResult}>
                      <h4>Match Result</h4>
                      <p className={styles.finalScore}>
                        {championshipData.teamA}: {championshipData.teamAPoints} - {championshipData.teamB}: {championshipData.teamBPoints}
                      </p>
                      <p className={styles.winner}>
                        {championshipData.teamAPoints > championshipData.teamBPoints 
                          ? `${championshipData.teamA} wins the match!` 
                          : championshipData.teamBPoints > championshipData.teamAPoints 
                            ? `${championshipData.teamB} wins the match!`
                            : 'The match ended in a draw!'}
                      </p>
                    </div>
                  )}
                </div>
                
                <div className={styles.championshipActions}>
                  <Link href="/championship/dashboard" className={styles.dashboardLink}>
                    Return to Dashboard
                  </Link>
                </div>
              </div>
            )}
            
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
                <span className={styles.statusValue}>
                  {isChampionshipMatch ? championshipData.status : battleState.status}
                </span>
              </div>
              
              <div className={styles.infoItem}>
                <span>{isChampionshipMatch ? 'Game:' : 'Turn:'}</span>
                <span>
                  {isChampionshipMatch 
                    ? `${championshipGameData.gameNumber}/4` 
                    : battleState.currentTurn}
                </span>
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