import React from 'react';
import styles from '../../../styles/Game.module.css';

interface CellProps {
  value: number;
  onClick: () => void;
  highlight: boolean;
}

const Cell: React.FC<CellProps> = ({ value, onClick, highlight }) => {
  let cellClassName = styles.cell;
  
  if (highlight) {
    cellClassName += ` ${styles.highlight}`;
  }
  
  if (value === 1) {
    cellClassName += ` ${styles.player1}`;
  } else if (value === 2) {
    cellClassName += ` ${styles.player2}`;
  }
  
  return (
    <div className={cellClassName} onClick={onClick}>
      {value !== 0 && <div className={styles.piece} />}
    </div>
  );
};

export default Cell;