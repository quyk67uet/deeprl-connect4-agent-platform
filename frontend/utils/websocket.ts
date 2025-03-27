export type WebSocketCallback = (event: any) => void;

export interface WebSocketCallbacks {
  onOpen: WebSocketCallback | null;
  onMessage: WebSocketCallback | null;
  onClose: WebSocketCallback | null;
  onError: WebSocketCallback | null;
}

export class WebSocketManager {
  private url: string;
  private gameId: string;
  private socket: WebSocket | null;
  private callbacks: WebSocketCallbacks;

  constructor(url: string, gameId: string) {
    this.url = url;
    this.gameId = gameId;
    this.socket = null;
    this.callbacks = {
      onOpen: null,
      onMessage: null,
      onClose: null,
      onError: null
    };
  }

  connect(): void {
    this.socket = new WebSocket(`${this.url}/ws/${this.gameId}`);
    
    this.socket.onopen = (event) => {
      console.log('WebSocket connection established');
      if (this.callbacks.onOpen) this.callbacks.onOpen(event);
    };
    
    this.socket.onmessage = (event) => {
      if (this.callbacks.onMessage) this.callbacks.onMessage(event);
    };
    
    this.socket.onclose = (event) => {
      console.log('WebSocket connection closed');
      if (this.callbacks.onClose) this.callbacks.onClose(event);
    };
    
    this.socket.onerror = (error) => {
      console.error('WebSocket error:', error);
      if (this.callbacks.onError) this.callbacks.onError(error);
    };
  }

  disconnect(): void {
    if (this.socket) {
      this.socket.close();
    }
  }

  send(message: object): void {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(message));
    } else {
      console.error('WebSocket not connected');
    }
  }

  setCallback(event: keyof WebSocketCallbacks, callback: WebSocketCallback): void {
    this.callbacks[event] = callback;
  }

  isConnected(): boolean {
    return this.socket !== null && this.socket.readyState === WebSocket.OPEN;
  }
}