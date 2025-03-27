import React from 'react';
import Cell from './Cell';
import styles from '../../../styles/Game.module.css';

interface BoardProps {
  board: number[][];
  currentPlayer: number;
  playerTurn: boolean;
  makeMove: (column: number) => void;
  againstAgent?: boolean;
}

const Board: React.FC<BoardProps> = ({ board, currentPlayer, playerTurn, makeMove, againstAgent }) => {
  const handleCellClick = (column: number) => {
    console.log("Cell clicked:", column);
    console.log("Player turn:", playerTurn);
    console.log("Against Agent:", againstAgent);
    console.log("Current player:", currentPlayer);
    
    // Trong chế độ agent, luôn cho phép thực hiện nước đi nếu agent mode = true
    if (playerTurn || (againstAgent === true && currentPlayer === 1)) {
      console.log("Making move:", column);
      makeMove(column);
    } else {
      console.log("Not making move - not player's turn or other condition");
      // Debug thêm thông tin để tìm hiểu tại sao điều kiện không thỏa mãn
      console.log("playerTurn:", playerTurn);
      console.log("againstAgent === true:", againstAgent === true);
      console.log("currentPlayer === 1:", currentPlayer === 1); 
      console.log("Điều kiện đầy đủ:", playerTurn || (againstAgent === true && currentPlayer === 1));
    }
  };

  return (
    <div className={styles.board}>
      {board.map((row, rowIndex) => (
        <div key={rowIndex} className={styles.row}>
          {row.map((cell, colIndex) => (
            <Cell
              key={colIndex}
              value={cell}
              onClick={() => handleCellClick(colIndex)}
              highlight={(playerTurn || (againstAgent === true && currentPlayer === 1)) && board[0][colIndex] === 0}
            />
          ))}
        </div>
      ))}
    </div>
  );
};

export default Board;