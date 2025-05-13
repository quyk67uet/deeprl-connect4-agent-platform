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
      return styles.cellBlocked; // Ô bị chặn
    }
    if (value === 1) {
      return styles.cellRed; // Quân đỏ
    }
    if (value === 2) {
      return styles.cellYellow; // Quân vàng
    }
    return styles.cellEmpty; // Ô trống
  };

  const cellClassName = `${styles.cell} ${highlight ? styles.highlight : ''} ${isLastMove ? styles.lastMove : ''} ${getCellClass()}`;

  return (
    <div className={cellClassName} onClick={onClick}></div>
  );
};

export default Cell;