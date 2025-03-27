import React, { useState } from 'react';
import { useRouter } from 'next/router';
import Head from 'next/head';
import Link from 'next/link';
import { toast, ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import styles from '../../styles/Join.module.css';

const JoinPage: React.FC = () => {
  const router = useRouter();
  const [gameId, setGameId] = useState<string>('');
  
  // Join a game
  const joinGame = () => {
    if (!gameId.trim()) {
      toast.error('Please enter a game ID');
      return;
    }
    
    router.push(`/game/${gameId}`);
  };
  
  // Handle Enter key press
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      joinGame();
    }
  };
  
  return (
    <>
      <Head>
        <title>Connect 4 - Join Game</title>
      </Head>
      
      <div className={styles.joinContainer}>
        <h1 className={styles.title}>Join Game</h1>
        
        <div className={styles.formContainer}>
          <input
            type="text"
            value={gameId}
            onChange={(e) => setGameId(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Enter Game ID"
            className={styles.input}
            autoFocus
          />
          
          <button 
            className={styles.button}
            onClick={joinGame}
          >
            Join
          </button>
        </div>
        
        <div className={styles.navigation}>
          <Link href="/" className={styles.backLink}>
            ← Back to Home
          </Link>
        </div>
      </div>
      
      <ToastContainer position="bottom-right" autoClose={3000} />
    </>
  );
};

export default JoinPage; 