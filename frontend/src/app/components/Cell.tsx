import React from 'react';
import styles from '../../../styles/Game.module.css';

interface CellProps {
  value: number;
  onClick: () => void;
  highlight: boolean;
  isLastMove?: boolean;
}

const Cell: React.FC<CellProps> = ({ value, onClick, highlight, isLastMove }) => {
  const getCellClass = () => {
    if (value === -1) {
      return styles.cellBlocked; // Class mới cho ô bị chặn
    }
    if (value === 1) {
      return styles.cellRed; // Class mới cho quân đỏ
    }
    if (value === 2) {
      return styles.cellYellow; // Class mới cho quân vàng
    }
    return '';
  };

  const cellClassName = `${styles.cell} ${highlight ? styles.highlight : ''} ${isLastMove ? styles.lastMove : ''} ${getCellClass()}`;

  return (
    <div className={cellClassName} onClick={onClick}></div>
  );
};

export default Cell;