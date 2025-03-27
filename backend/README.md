# Connect4 Game Backend

Backend cho ứng dụng Connect4 với Agent AI sử dụng Deep Reinforcement Learning.

## Cài đặt

1. Đảm bảo bạn đã cài đặt Python 3.10 hoặc cao hơn
2. Cài đặt các thư viện cần thiết:

```bash
pip install -r requirements.txt
```

## Cấu trúc mã nguồn

- `server.py`: FastAPI WebSocket server để giao tiếp với frontend
- `game_logic.py`: Triển khai logic trò chơi Connect4
- `agent_loader.py`: Tải và khởi tạo Agent AI sử dụng Stable Baselines3
- `models/connect4_ppo_agent.zip`: Model Agent đã được huấn luyện
- `test_agent.py`: Script để kiểm tra Agent

## Chạy server

```bash
uvicorn server:app --reload
```

Server mặc định sẽ chạy ở địa chỉ http://127.0.0.1:8000.

## Kiểm tra Agent

Để kiểm tra Agent hoạt động đúng cách:

```bash
python test_agent.py
```

## Vấn đề tương thích

- Nếu bạn gặp lỗi với NumPy 2.x, hãy cài đặt NumPy 1.x như trong requirements.txt
- Một số thư viện có thể yêu cầu phiên bản Python cụ thể. Dự án này được phát triển và kiểm tra trên Python 3.10.

## API Endpoints

- WebSocket: `/ws/{game_id}/{player_num}`
- REST API:
  - `POST /api/create-game`: Tạo game mới
  - `GET /api/game/{game_id}/state`: Lấy trạng thái hiện tại của game
  - `POST /api/game/{game_id}/move`: Thực hiện nước đi 