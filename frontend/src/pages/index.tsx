import React, { useState } from 'react';
import { useRouter } from 'next/router';
import Head from 'next/head';
import { toast, ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import styles from '../../styles/Game.module.css';

const HomePage: React.FC = () => {
  const router = useRouter();
  const [gameId, setGameId] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);

  // Create a new game
  const createGame = async () => {
    try {
      setLoading(true);
      const response = await fetch('http://localhost:8000/api/create-game', {
        method: 'POST',
      });
      
      if (!response.ok) {
        throw new Error('Failed to create game');
      }
      
      const data = await response.json();
      router.push(`/game/${data.game_id}`);
    } catch (error) {
      console.error('Error creating game:', error);
      toast.error('Failed to create game. Please try again.');
      setLoading(false);
    }
  };

  // Join an existing game
  const joinGame = () => {
    if (!gameId.trim()) {
      toast.error('Please enter a game ID');
      return;
    }
    
    router.push(`/game/${gameId}`);
  };

  return (
    <>
      <Head>
        <title>Connect 4 - Home</title>
      </Head>
      
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className={styles.homeContent}>
          <h1 className={styles.title}>Connect 4</h1>
          
          <div className={styles.actions}>
            <button 
              className={styles.button} 
              onClick={createGame}
              disabled={loading}
            >
              {loading ? 'Creating...' : 'Create New Game'}
            </button>
            
            <div className={styles.joinSection}>
              <input
                type="text"
                value={gameId}
                onChange={(e) => setGameId(e.target.value)}
                placeholder="Enter Game ID"
                className={styles.input}
              />
              <button 
                className={styles.button}
                onClick={joinGame}
                disabled={loading}
              >
                Join Game
              </button>
            </div>
          </div>
        </div>
      </div>
      
      <ToastContainer position="bottom-right" autoClose={3000} />
    </>
  );
};

export default HomePage;