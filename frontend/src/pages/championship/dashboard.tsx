import React, { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/router';
import Head from 'next/head';
import Link from 'next/link';
import axios from 'axios';
import { toast, ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import styles from '../../../styles/Championship.module.css';

// API URL and WebSocket URL
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';

// Interface definitions
interface TeamScore {
  team_name: string;
  points: number;
}

interface Match {
  match_id: string;
  team_a: string;
  team_b: string;
  status: string;
  winner: string | null;
  team_a_points: number;
  team_b_points: number;
}

interface Round {
  round: number;
  matches: Match[];
}

interface Schedule {
  rounds: Round[];
}

interface ChampionshipStatus {
  status: string;
  team_count: number;
  current_round: number;
  total_rounds: number;
}

const ChampionshipDashboard: React.FC = () => {
  const router = useRouter();
  
  // State
  const [status, setStatus] = useState<ChampionshipStatus>({
    status: 'waiting',
    team_count: 0,
    current_round: 0,
    total_rounds: 0
  });
  const [leaderboard, setLeaderboard] = useState<TeamScore[]>([]);
  const [schedule, setSchedule] = useState<Schedule>({ rounds: [] });
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [connected, setConnected] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'schedule' | 'leaderboard'>('schedule');
  const [isStarting, setIsStarting] = useState<boolean>(false);
  const [isClearing, setIsClearing] = useState<boolean>(false);
  
  // Hàm khởi động giải đấu
  const startChampionship = async () => {
    if (status.team_count < 2) {
      toast.error('Cần ít nhất 2 đội để bắt đầu giải đấu');
      return;
    }

    if (status.status !== 'waiting') {
      toast.info('Giải đấu đã bắt đầu hoặc đã kết thúc');
      return;
    }

    try {
      setIsStarting(true);
      const response = await axios.post(`${API_URL}/api/championship/start`);
      
      if (response.data.success) {
        toast.success(response.data.message);
      } else {
        toast.error('Không thể bắt đầu giải đấu');
      }
    } catch (error) {
      console.error('Lỗi khi bắt đầu giải đấu:', error);
      toast.error('Không thể bắt đầu giải đấu. Vui lòng thử lại sau.');
    } finally {
      setIsStarting(false);
    }
  };
  
  // Hàm xóa cache Redis
  const clearCache = async () => {
    try {
      setIsClearing(true);
      const response = await axios.post(`${API_URL}/api/clear-cache`);
      
      if (response.data.success) {
        toast.success(response.data.message);
        // Tải lại dữ liệu sau khi xóa cache
        await loadInitialData();
      } else {
        toast.error('Không thể xóa cache Redis');
      }
    } catch (error) {
      console.error('Lỗi khi xóa cache Redis:', error);
      toast.error('Không thể xóa cache Redis. Vui lòng thử lại sau.');
    } finally {
      setIsClearing(false);
    }
  };
  
  // Load initial data
  const loadInitialData = useCallback(async () => {
    try {
      // Get championship status
      const statusResponse = await axios.get(`${API_URL}/api/championship/status`);
      setStatus(statusResponse.data);
      
      // Get leaderboard
      const leaderboardResponse = await axios.get(`${API_URL}/api/championship/leaderboard`);
      setLeaderboard(leaderboardResponse.data || []);
      
      // Get schedule
      const scheduleResponse = await axios.get(`${API_URL}/api/championship/schedule`);
      setSchedule(scheduleResponse.data || { rounds: [] });
    } catch (error) {
      console.error('Error loading dashboard data:', error);
      toast.error('Failed to load dashboard data');
    }
  }, []);
  
  // Connect to WebSocket
  useEffect(() => {
    const ws = new WebSocket(`${WS_URL}/ws/championship/dashboard`);
    
    ws.onopen = () => {
      setConnected(true);
      console.log('Connected to championship dashboard');
    };
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('Received dashboard update:', data);
        
        // Handle different update types
        switch (data.type) {
          case 'initial_state':
            // Initial state has everything
            setStatus({
              status: data.status || 'waiting',
              team_count: data.team_count || 0,
              current_round: data.current_round || 0,
              total_rounds: data.total_rounds || 0
            });
            setLeaderboard(data.leaderboard || []);
            setSchedule(data.schedule || { rounds: [] });
            break;
            
          case 'status_update':
            // Update championship status
            setStatus(prev => ({
              ...prev,
              status: data.status || prev.status
            }));
            
            // If schedule is included, update it
            if (data.schedule) {
              setSchedule(data.schedule);
            }
            
            // If leaderboard is included, update it
            if (data.leaderboard) {
              setLeaderboard(data.leaderboard);
            }
            
            // Show message if included
            if (data.message) {
              toast.info(data.message);
            }
            break;
            
          case 'round_start':
            // Update current round when a new round starts
            setStatus(prev => ({
              ...prev,
              current_round: data.round_number || prev.current_round
            }));
            
            // Show message
            if (data.message) {
              toast.info(data.message);
            }
            break;
            
          case 'round_complete':
            // Show message when a round completes
            if (data.message) {
              toast.info(data.message);
            }
            break;
            
          case 'match_update':
            // Update a single match in the schedule
            setSchedule(prev => {
              if (!prev.rounds || !prev.rounds.length) {
                return prev;
              }
              
              // Find the round this match belongs to
              const roundIndex = prev.rounds.findIndex(r => 
                r.matches && r.matches.some(m => m.match_id === data.match_id)
              );
              
              if (roundIndex >= 0 && prev.rounds[roundIndex].matches) {
                // Find the match in this round
                const matchIndex = prev.rounds[roundIndex].matches.findIndex(
                  m => m.match_id === data.match_id
                );
                
                if (matchIndex >= 0) {
                  // Create a new rounds array
                  const newRounds = [...prev.rounds];
                  
                  // Update the match with the new data
                  newRounds[roundIndex].matches[matchIndex] = {
                    ...newRounds[roundIndex].matches[matchIndex],
                    status: data.status || newRounds[roundIndex].matches[matchIndex].status,
                    winner: data.winner !== undefined ? data.winner : newRounds[roundIndex].matches[matchIndex].winner,
                    team_a_points: data.team_a_points !== undefined ? data.team_a_points : newRounds[roundIndex].matches[matchIndex].team_a_points,
                    team_b_points: data.team_b_points !== undefined ? data.team_b_points : newRounds[roundIndex].matches[matchIndex].team_b_points
                  };
                  
                  return { rounds: newRounds };
                }
              }
              
              return prev;
            });
            break;
            
          case 'leaderboard_update':
            // Update leaderboard
            if (data.leaderboard) {
              setLeaderboard(data.leaderboard);
            }
            break;
        }
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
      }
    };
    
    ws.onclose = () => {
      setConnected(false);
      console.log('Disconnected from championship dashboard');
      
      // Try to reconnect after a delay
      setTimeout(() => {
        console.log('Attempting to reconnect...');
        setSocket(new WebSocket(`${WS_URL}/ws/championship/dashboard`));
      }, 3000);
    };
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
    
    setSocket(ws);
    
    // Load initial data as backup
    loadInitialData();
    
    // Cleanup on unmount
    return () => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
    };
  }, [loadInitialData]);
  
  // Get status message
  const getStatusMessage = () => {
    if (status.status === 'waiting') {
      return `Waiting to start - ${status.team_count}/20 teams registered`;
    } else if (status.status === 'in_progress') {
      return `In Progress - Round ${status.current_round}/${status.total_rounds}`;
    } else if (status.status === 'finished') {
      return 'Championship Finished';
    }
    return 'Unknown status';
  };
  
  // Get match status badge class
  const getMatchStatusClass = (matchStatus: string) => {
    switch (matchStatus) {
      case 'scheduled':
        return styles.statusScheduled;
      case 'in_progress':
        return styles.statusInProgress;
      case 'finished':
        return styles.statusFinished;
      default:
        return '';
    }
  };
  
  return (
    <>
      <Head>
        <title>Championship Dashboard - Connect 4</title>
        <meta name="description" content="Connect 4 Championship Dashboard" />
      </Head>
      
      <div className={styles.dashboardContainer}>
        <div className={styles.dashboardHeader}>
          <h1 className={styles.dashboardTitle}>Championship Dashboard</h1>
          
          <div className={`${styles.connectionStatus} ${!connected ? styles.disconnected : ''}`}>
            {connected ? 'Connected' : 'Disconnected'}
          </div>
        </div>
        
        <div className={styles.statusBar}>
          <div className={styles.statusMessage}>
            Status: {getStatusMessage()}
          </div>
          
          <div className={styles.actions}>
            {status.status === 'waiting' && status.team_count >= 2 && (
              <button 
                className={styles.startButton} 
                onClick={startChampionship}
                disabled={isStarting}
              >
                {isStarting ? 'Starting...' : 'Start Championship'}
              </button>
            )}
            <Link href="/" className={styles.backLink}>
              Back to Home
            </Link>
          </div>
        </div>
        
        <div className={styles.dashboardTabs}>
          <button 
            className={`${styles.tabButton} ${activeTab === 'schedule' ? styles.activeTab : ''}`}
            onClick={() => setActiveTab('schedule')}
          >
            Match Schedule
          </button>
          <button 
            className={`${styles.tabButton} ${activeTab === 'leaderboard' ? styles.activeTab : ''}`}
            onClick={() => setActiveTab('leaderboard')}
          >
            Leaderboard
          </button>
        </div>
        
        <div className={styles.dashboardContent}>
          {activeTab === 'schedule' ? (
            <div className={styles.scheduleContainer}>
              {!schedule.rounds || schedule.rounds.length === 0 ? (
                <div className={styles.emptyMessage}>
                  No matches scheduled yet. The schedule will be generated when the championship starts.
                </div>
              ) : (
                <div className={styles.roundsContainer}>
                  {schedule.rounds.map((round) => (
                    <div key={round.round} className={styles.roundBlock}>
                      <h3 className={styles.roundTitle}>
                        Round {round.round}
                        {status.current_round === round.round && (
                          <span className={styles.currentRound}>(Current)</span>
                        )}
                      </h3>
                      
                      <div className={styles.matchesList}>
                        {round.matches && round.matches.map((match) => (
                          <div key={match.match_id} className={styles.matchCard}>
                            <div className={styles.matchHeader}>
                              <span className={`${styles.statusBadge} ${getMatchStatusClass(match.status)}`}>
                                {match.status}
                              </span>
                            </div>
                            
                            <div className={styles.matchTeams}>
                              <div className={styles.teamBlock}>
                                <span className={styles.teamName}>{match.team_a}</span>
                                <span className={styles.teamScore}>{match.team_a_points}</span>
                              </div>
                              
                              <span className={styles.versus}>vs</span>
                              
                              <div className={styles.teamBlock}>
                                <span className={styles.teamName}>{match.team_b}</span>
                                <span className={styles.teamScore}>{match.team_b_points}</span>
                              </div>
                            </div>
                            
                            {match.winner && (
                              <div className={styles.matchResult}>
                                Winner: {match.winner === 'team_a' 
                                  ? match.team_a 
                                  : match.winner === 'team_b'
                                    ? match.team_b
                                    : 'Draw'}
                              </div>
                            )}
                            
                            <div className={styles.matchActions}>
                              {(match.status === 'in_progress' || match.status === 'scheduled') && (
                                <Link href={`/championship/battle/${match.match_id}`} className={styles.viewButton}>
                                  View Play
                                </Link>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className={styles.leaderboardContainer}>
              {!leaderboard || leaderboard.length === 0 ? (
                <div className={styles.emptyMessage}>
                  No leaderboard data yet. Points will be awarded as matches are played.
                </div>
              ) : (
                <table className={styles.leaderboardTable}>
                  <thead>
                    <tr>
                      <th>Rank</th>
                      <th>Team</th>
                      <th>Points</th>
                    </tr>
                  </thead>
                  <tbody>
                    {leaderboard.map((team, index) => (
                      <tr key={team.team_name} className={index < 3 ? styles.topRank : ''}>
                        <td>{index + 1}</td>
                        <td>{team.team_name}</td>
                        <td>{team.points}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      </div>
      
      <ToastContainer position="bottom-right" autoClose={3000} />
    </>
  );
};

export default ChampionshipDashboard; 