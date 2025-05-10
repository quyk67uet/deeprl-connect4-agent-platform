import React from 'react';
import styles from '../../../styles/Game.module.css';

interface CellProps {
  value: number;
  onClick: () => void;
  highlight: boolean; 
  isLastMove?: boolean;
}

const Cell: React.FC<CellProps> = ({ value, onClick, highlight, isLastMove }) => {
  const getCellContent = () => {
    if (value === -1) {
      return '🚫'; // Blocked cell
    }
    if (value === 1) {
      return '🔴'; // Red player
    }
    if (value === 2) {
      return '🟡'; // Yellow player
    }
    return '';
  };

  const cellClassName = `${styles.cell} ${highlight ? styles.highlight : ''} ${isLastMove ? styles.lastMove : ''}`;

  return (
    <div className={cellClassName} onClick={onClick}>
      {getCellContent()}
    </div>
  );
};

export default Cell;