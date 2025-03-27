import asyncio
import websockets
import json
import time

async def test_websocket_make_move():
    # Tạo URL WebSocket, thay đổi ID game nếu cần
    game_id = "test_game" 
    uri = f"ws://localhost:8000/ws/{game_id}"
    
    try:
        # Kết nối WebSocket
        print(f"Kết nối tới {uri}")
        async with websockets.connect(uri) as websocket:
            # Nhận trạng thái game ban đầu
            response = await websocket.recv()
            initial_state = json.loads(response)
            print(f"Trạng thái ban đầu: {initial_state}")
            
            # Bật chế độ Agent
            print(f"Bật chế độ Agent")
            await websocket.send(json.dumps({
                "type": "start_agent_game"
            }))
            
            # Chờ phản hồi từ server
            response = await websocket.recv()
            agent_state = json.loads(response)
            print(f"Trạng thái sau khi bật Agent: {agent_state}")
            
            # Đợi 1 giây
            await asyncio.sleep(1)
            
            # Thực hiện nước đi ở cột 3
            print(f"Thực hiện nước đi ở cột 3")
            await websocket.send(json.dumps({
                "type": "make_move",
                "column": 3
            }))
            
            # Đợi phản hồi từ server (người chơi)
            response = await websocket.recv()
            move_result = json.loads(response)
            print(f"Kết quả nước đi người chơi: {move_result}")
            
            # Đợi phản hồi từ server (AI)
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                ai_result = json.loads(response)
                print(f"Kết quả nước đi AI: {ai_result}")
            except asyncio.TimeoutError:
                print("Không nhận được phản hồi từ AI trong 2 giây")
            
    except Exception as e:
        print(f"Lỗi: {e}")

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(test_websocket_make_move()) 