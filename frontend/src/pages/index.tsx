import React, { useState } from 'react';
import { useRouter } from 'next/router';
import Head from 'next/head';
import axios from 'axios';
import styles from '../../styles/Home.module.css';

// API URL
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function Home() {
  const router = useRouter();
  const [isCreating, setIsCreating] = useState(false);
  
  // Create new game
  const createNewGame = async () => {
    setIsCreating(true);
    try {
      const response = await axios.post(`${API_URL}/api/create-game`);
      router.push(`/game/${response.data.game_id}`);
    } catch (error) {
      console.error('Error creating game:', error);
      alert('Failed to create new game. Please try again.');
      setIsCreating(false);
    }
  };
  
  // Create AI battle
  const createAIBattle = async () => {
    setIsCreating(true);
    try {
      const response = await axios.post(`${API_URL}/api/create-battle`);
      router.push(`/battle/${response.data.battle_id}`);
    } catch (error) {
      console.error('Error creating AI battle:', error);
      alert('Failed to create AI battle. Please try again.');
      setIsCreating(false);
    }
  };
  
  return (
    <>
      <Head>
        <title>Connect 4 Game</title>
        <meta name="description" content="Play Connect 4 online - Human vs Human, Human vs AI, or AI vs AI" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>
      
      <div className={styles.container}>
        <h1 className={styles.title}>Connect 4</h1>
        
        <div className={styles.buttonContainer}>
          <button 
            className={styles.button} 
            onClick={createNewGame}
            disabled={isCreating}
          >
            {isCreating ? 'Creating...' : 'New Game'}
          </button>
          
          <button
            className={styles.button}
            onClick={() => router.push('/join')}
            disabled={isCreating}
          >
            Join Game
          </button>
          
          <button
            className={`${styles.button} ${styles.aiButton}`}
            onClick={createAIBattle}
            disabled={isCreating}
          >
            AI vs AI Battle
          </button>
        </div>
        
        <p className={styles.instruction}>
          Create a new game to play with a friend or against the AI, or join an existing game using a game ID.
        </p>
        
        <p className={styles.aiInstruction}>
          Create an AI vs AI battle to watch two AI agents play against each other. You can use your own AI or the default one.
        </p>
      </div>
    </>
  );
}