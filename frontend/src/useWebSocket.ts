import { useState, useEffect, useRef } from 'react';
import { AnalyticsData } from './types';

export function useWebSocket(url: string) {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    // Clear data immediately when URL changes to prevent showing stale data
    setData(null);
    setIsConnected(false);

    const connect = () => {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('WebSocket connected');
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        // Only process messages if this is still the active WebSocket
        if (ws === wsRef.current) {
          try {
            const message = JSON.parse(event.data);
            setData(message);
          } catch (error) {
            console.error('Failed to parse message:', error);
          }
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };

      ws.onclose = () => {
        console.log('WebSocket disconnected');
        // Only update state if this is still the active WebSocket
        if (ws === wsRef.current) {
          setIsConnected(false);
          setData(null);  // Clear data when disconnecting
          // Attempt to reconnect after 3 seconds
          reconnectTimeoutRef.current = setTimeout(connect, 3000);
        }
      };
    };

    connect();

    // Cleanup on unmount or URL change
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [url]);

  return { data, isConnected };
}
