import { useEffect, useState, useRef } from 'react';
import { MetricsSnapshot } from '../types/metrics';
import { SSE_STREAM_URL } from '../services/api';

export function useSSE() {
  const [data, setData] = useState<MetricsSnapshot | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    console.log('Connecting to SSE stream:', SSE_STREAM_URL);
    const eventSource = new EventSource(SSE_STREAM_URL);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      console.log('SSE connection opened');
      setIsConnected(true);
      setError(null);
    };

    eventSource.addEventListener('metrics', (event) => {
      try {
        const metrics: MetricsSnapshot = JSON.parse(event.data);
        setData(metrics);
      } catch (e) {
        console.error('Failed to parse metrics:', e);
        setError(e as Error);
      }
    });

    eventSource.addEventListener('error', (event) => {
      console.error('SSE error event:', event);
      setError(new Error('SSE connection error'));
    });

    eventSource.onerror = (err) => {
      console.error('SSE connection error:', err);
      setIsConnected(false);
      setError(new Error('Failed to connect to metrics stream'));
    };

    return () => {
      console.log('Closing SSE connection');
      eventSource.close();
    };
  }, []);

  return { data, error, isConnected };
}
