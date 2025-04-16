/**
 * WebSocket utility functions
 */

/**
 * Creates a WebSocket connection with appropriate protocol based on the current page protocol
 * @param baseUrl - The base URL for the WebSocket connection (without protocol)
 * @param path - The path to connect to
 * @param onMessage - Message handler function
 * @param onError - Error handler function
 * @param onClose - Close handler function
 * @param onOpen - Open handler function
 * @returns The WebSocket instance
 */
export const createWebSocketConnection = (
  baseUrl: string,
  path: string,
  onMessage?: (event: MessageEvent) => void,
  onError?: (event: Event) => void,
  onClose?: (event: CloseEvent) => void,
  onOpen?: (event: Event) => void
): WebSocket => {
  // Determine if we're on a secure connection
  const isSecureConnection = typeof window !== 'undefined' && window.location.protocol === 'https:';
  
  // Choose the appropriate WebSocket protocol
  const protocol = isSecureConnection ? 'wss://' : 'ws://';
  
  // Full WebSocket URL
  const wsUrl = `${protocol}${baseUrl}${path}`;
  
  // Log connection attempt with environment details
  console.log(`[WebSocket] Connecting to: ${wsUrl}`);
  console.log(`[WebSocket] Environment: isSecure=${isSecureConnection}, protocol=${window?.location?.protocol}`);
  
  try {
    const socket = new WebSocket(wsUrl);
    
    // Set up event handlers if provided
    if (onMessage) socket.onmessage = onMessage;
    if (onError) socket.onerror = onError;
    if (onClose) socket.onclose = onClose;
    if (onOpen) socket.onopen = onOpen;
    
    // Add default error handler if none provided
    if (!onError) {
      socket.onerror = (event) => {
        console.error(`[WebSocket] Connection error:`, event);
      };
    }
    
    return socket;
  } catch (error) {
    console.error(`[WebSocket] Failed to create connection:`, error);
    // Re-throw to allow caller to handle
    throw error;
  }
};

/**
 * Safely send a message through WebSocket with error handling
 * @param socket - The WebSocket instance
 * @param data - The data to send
 * @returns true if sent successfully, false otherwise
 */
export const safeSend = (socket: WebSocket, data: any): boolean => {
  try {
    if (socket.readyState === WebSocket.OPEN) {
      const message = typeof data === 'string' ? data : JSON.stringify(data);
      socket.send(message);
      return true;
    } else {
      console.warn(`[WebSocket] Cannot send message, socket not open (state: ${socket.readyState})`);
      return false;
    }
  } catch (error) {
    console.error(`[WebSocket] Error sending message:`, error);
    return false;
  }
};

/**
 * Get a readable state description for WebSocket readyState
 * @param readyState - The WebSocket readyState value
 * @returns A human-readable description of the connection state
 */
export const getConnectionStateDescription = (readyState: number): string => {
  switch (readyState) {
    case WebSocket.CONNECTING:
      return 'Connecting';
    case WebSocket.OPEN:
      return 'Open';
    case WebSocket.CLOSING:
      return 'Closing';
    case WebSocket.CLOSED:
      return 'Closed';
    default:
      return 'Unknown';
  }
}; 