import { useEffect, useRef, useState, useCallback } from 'react';

interface UseWebSocketOptions {
  url: string;
  enabled?: boolean;
  reconnectAttempts?: number;
  reconnectInterval?: number;
}

interface UseWebSocketReturn<T> {
  data: T | null;
  isConnected: boolean;
  isConnecting: boolean;
  error: string | null;
  close: () => void;
}

/**
 * Reusable WebSocket hook with:
 * - JWT auth token injection via query param
 * - Exponential backoff reconnection
 * - Auto-cleanup on unmount
 */
export function useWebSocket<T = unknown>({
  url,
  enabled = true,
  reconnectAttempts = 5,
  reconnectInterval = 2000,
}: UseWebSocketOptions): UseWebSocketReturn<T> {
  const [data, setData] = useState<T | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const mountedRef = useRef(true);

  const close = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close(1000, 'User closed');
      wsRef.current = null;
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    if (!enabled || !url) return;

    const connect = () => {
      if (!mountedRef.current) return;

      setIsConnecting(true);
      setError(null);

      const token = localStorage.getItem('access_token');
      const separator = url.includes('?') ? '&' : '?';
      const fullUrl = `${url}${separator}access_token=${token}`;

      const ws = new WebSocket(fullUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setIsConnected(true);
        setIsConnecting(false);
        retriesRef.current = 0;
      };

      ws.onmessage = (event) => {
        if (!mountedRef.current) return;
        try {
          const payload = JSON.parse(event.data);
          setData(payload);
        } catch {
          console.error('[WS] Failed to parse message');
        }
      };

      ws.onerror = () => {
        if (!mountedRef.current) return;
        setError('WebSocket connection error');
        setIsConnecting(false);
      };

      ws.onclose = (event) => {
        if (!mountedRef.current) return;
        setIsConnected(false);
        setIsConnecting(false);

        // Don't reconnect on clean close or if max retries exceeded
        if (event.code === 1000 || retriesRef.current >= reconnectAttempts) {
          return;
        }

        // Exponential backoff
        const delay = reconnectInterval * Math.pow(2, retriesRef.current);
        retriesRef.current += 1;

        setTimeout(() => {
          if (mountedRef.current) connect();
        }, delay);
      };
    };

    connect();

    return () => {
      mountedRef.current = false;
      close();
    };
  }, [url, enabled, reconnectAttempts, reconnectInterval, close]);

  return { data, isConnected, isConnecting, error, close };
}
