import os
import numpy as np
from agent_loader import load_agent, get_agent_move
from game_logic import Connect4Game

def test_agent():
    # Đường dẫn đến model
    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models/connect4_ppo_agent.zip")
    
    # Load agent
    print(f"Đang tải agent từ {model_path}...")
    try:
        agent = load_agent(model_path)
        print("Đã tải agent thành công!")
    except Exception as e:
        print(f"Lỗi khi tải agent: {e}")
        return False
    
    # Tạo game mới để test
    game = Connect4Game()
    
    # Test agent với trạng thái bàn cờ ban đầu
    valid_moves = game.get_valid_moves()
    print(f"Các nước đi hợp lệ: {valid_moves}")
    
    # Lấy nước đi từ agent
    ai_move = get_agent_move(agent, game.get_board(), valid_moves)
    print(f"Agent đã chọn cột: {ai_move}")
    
    # Kiểm tra xem nước đi có hợp lệ không
    if ai_move in valid_moves:
        print("Nước đi của Agent hợp lệ.")
    else:
        print("LỖI: Nước đi của Agent không hợp lệ!")
        return False
    
    # Test với một số trạng thái bàn cờ khác nhau
    print("\nTest với trạng thái bàn cờ đã có một số nước đi:")
    
    # Tạo một trạng thái bàn cờ giả lập
    test_board = np.zeros((6, 7), dtype=np.int8)
    test_board[5][3] = 1  # Player 1 đã đánh ở cột giữa, hàng dưới cùng
    
    valid_moves = [col for col in range(7) if test_board[0][col] == 0]
    print(f"Bàn cờ test:\n{test_board}")
    print(f"Các nước đi hợp lệ: {valid_moves}")
    
    ai_move = get_agent_move(agent, test_board.tolist(), valid_moves)
    print(f"Agent đã chọn cột: {ai_move}")
    
    if ai_move in valid_moves:
        print("Nước đi của Agent hợp lệ.")
    else:
        print("LỖI: Nước đi của Agent không hợp lệ!")
        return False
    
    print("\nMô phỏng 3 lượt đầu tiên của trò chơi:")
    game.reset()
    
    for _ in range(3):
        # Player 1 (người chơi) đi trước
        valid_moves = game.get_valid_moves()
        player_move = valid_moves[0]  # Giả sử người chơi luôn chọn nước đi đầu tiên trong danh sách
        print(f"Người chơi chọn cột: {player_move}")
        game.make_move(player_move)
        
        if game.game_over:
            break
            
        # Player 2 (AI) đi sau
        valid_moves = game.get_valid_moves()
        ai_move = get_agent_move(agent, game.get_board(), valid_moves)
        print(f"AI chọn cột: {ai_move}")
        game.make_move(ai_move)
        
        print(f"Trạng thái bàn cờ sau lượt {_+1}:\n{np.array(game.get_board())}")
        print("-" * 30)
        
        if game.game_over:
            break
    
    print("Tất cả các test đã hoàn thành!")
    return True

if __name__ == "__main__":
    test_agent() 