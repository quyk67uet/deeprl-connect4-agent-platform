import React, { useState } from 'react';
import { useRouter } from 'next/router';
import Head from 'next/head';
import Link from 'next/link';
import axios from 'axios';
import { toast, ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import styles from '../../styles/Home.module.css';

// API URL
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function Home() {
  const router = useRouter();
  const [isCreating, setIsCreating] = useState(false);
  const [showAIModal, setShowAIModal] = useState(false);
  const [battleId, setBattleId] = useState('');
  const [isResetting, setIsResetting] = useState(false);
  
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

  // Join existing AI battle
  const joinAIBattle = () => {
    if (battleId.trim() === '') {
      alert('Please enter a valid Battle ID');
      return;
    }
    router.push(`/battle/${battleId.trim()}`);
  };

  // Navigate to championship registration
  const joinChampionship = () => {
    router.push('/championship/register');
  };
  
  // Reset cache
  const resetCache = async () => {
    setIsResetting(true);
    try {
      const response = await axios.post(`${API_URL}/api/clear-cache`);
      if (response.data.success) {
        toast.success(response.data.message);
      } else {
        toast.error('Không thể reset cache');
      }
    } catch (error) {
      console.error('Lỗi khi reset cache:', error);
      toast.error('Không thể reset cache. Vui lòng thử lại sau.');
    } finally {
      setIsResetting(false);
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
            onClick={() => setShowAIModal(true)}
            disabled={isCreating}
          >
            AI vs AI Battle
          </button>

          <button
            className={`${styles.button} ${styles.championshipButton}`}
            onClick={joinChampionship}
            disabled={isCreating}
          >
            Join Championship
          </button>
          
          <button
            className={`${styles.button} ${styles.resetButton}`}
            onClick={resetCache}
            disabled={isResetting}
          >
            {isResetting ? 'Đang reset...' : 'Reset Cache'}
          </button>
        </div>
        
        <p className={styles.instruction}>
          Create a new game to play with a friend or against the AI, or join an existing game using a game ID.
        </p>
        
        <p className={styles.aiInstruction}>
          Create an AI vs AI battle to watch two AI agents play against each other. You can use your own AI or the default one.
        </p>

        <p className={styles.championshipInstruction}>
          Join the championship to compete with other AI agents in a round-robin tournament.
        </p>

        {showAIModal && (
          <div className={styles.modalOverlay}>
            <div className={styles.modal}>
              <h2>AI vs AI Battle</h2>
              <div className={styles.modalOptions}>
                <button 
                  className={styles.modalButton}
                  onClick={createAIBattle}
                  disabled={isCreating}
                >
                  Create New Battle
                </button>
                
                <div className={styles.modalDivider}>OR</div>
                
                <div className={styles.joinBattleForm}>
                  <input
                    type="text"
                    placeholder="Enter Battle ID"
                    className={styles.battleInput}
                    value={battleId}
                    onChange={(e) => setBattleId(e.target.value)}
                  />
                  <button 
                    className={styles.modalButton}
                    onClick={joinAIBattle}
                  >
                    Join Existing Battle
                  </button>
                </div>
              </div>
              <button 
                className={styles.closeButton}
                onClick={() => setShowAIModal(false)}
              >
                Close
              </button>
            </div>
          </div>
        )}
      </div>
      
      <ToastContainer position="bottom-right" autoClose={3000} />
    </>
  );
}