import React from 'react';
import styles from '../../../styles/Game.module.css';

interface GameControlsProps {
  gameId: string;
  againstAgent: boolean;
  onStartAgentGame: () => void;
  onResetGame: () => void;
  copyGameId: () => void;
}

const GameControls: React.FC<GameControlsProps> = ({
  gameId,
  againstAgent,
  onStartAgentGame,
  onResetGame,
  copyGameId,
}) => {
  return (
    <div className={styles.controls}>
      <div className={styles.gameInfo}>
        <span>Game ID: {gameId}</span>
        <button className={styles.copyButton} onClick={copyGameId}>
          Copy
        </button>
      </div>
      
      <button className={styles.button} onClick={onResetGame}>
        Reset Game
      </button>
      
      {!againstAgent && (
        <button className={styles.button} onClick={onStartAgentGame}>
          Play Against AI
        </button>
      )}
      
      {againstAgent && (
        <div className={styles.agentModeActive}>
          <div className={styles.aiIndicator}></div>
          Playing against AI
        </div>
      )}
    </div>
  );
};

export default GameControls;