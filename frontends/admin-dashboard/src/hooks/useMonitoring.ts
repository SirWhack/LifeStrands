import { useState, useEffect, useCallback, useRef } from 'react';

export interface SystemMetrics {
  timestamp: string;
  system: {
    cpu_usage_percent: number;
    memory_usage_percent: number;
    disk_usage_percent: number;
    disk_free_gb: number;
    load_average: number[];
    uptime_seconds: number;
  };
  gpu: {
    available: boolean;
    count: number;
    gpus: {
      id: number;
      name: string;
      memory_used_mb: number;
      memory_total_mb: number;
      memory_usage_percent: number;
      utilization_percent: number;
      temperature_c: number;
      power_usage_w: number;
    }[];
  };
  services: {
    [serviceName: string]: {
      status: string;
      response_time_ms: number;
      error_rate: number;
      active_connections: number;
      memory_usage_mb: number;
      cpu_usage_percent: number;
    };
  };
  database: {
    status: string;
    active_connections: number;
    query_time_ms: number;
    queries_per_second: number;
  };
  redis: {
    status: string;
    memory_usage_mb: number;
    connected_clients: number;
    commands_per_second: number;
  };
}

export interface Alert {
  alert_id: string;
  alert_type: string;
  message: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  source: string;
  status: 'active' | 'acknowledged' | 'resolved' | 'muted';
  metadata: any;
  created_at: string;
  updated_at: string;
  acknowledged_at?: string;
  resolved_at?: string;
  acknowledged_by?: string;
  count: number;
}

export interface HealthStatus {
  timestamp: string;
  overall_status: 'healthy' | 'degraded' | 'critical' | 'error';
  services: {
    [serviceName: string]: {
      status: string;
      response_time_ms: number;
      critical: boolean;
      error?: string;
    };
  };
  dependencies: {
    database: {
      status: string;
      response_time_ms: number;
      error?: string;
    };
    redis: {
      status: string;
      response_time_ms: number;
      error?: string;
    };
  };
  summary: {
    total_services: number;
    healthy_services: number;
    unhealthy_services: number;
    critical_failures: number;
  };
}

interface UseMonitoringOptions {
  apiBaseUrl?: string;
  authToken?: string;
  refreshInterval?: number;
  enableRealTime?: boolean;
}

interface UseMonitoringReturn {
  metrics: SystemMetrics | null;
  alerts: Alert[];
  healthStatus: HealthStatus | null;
  loading: boolean;
  error: string | null;
  connected: boolean;
  fetchMetrics: () => Promise<void>;
  fetchAlerts: () => Promise<void>;
  fetchHealthStatus: () => Promise<void>;
  acknowledgeAlert: (alertId: string) => Promise<boolean>;
  resolveAlert: (alertId: string) => Promise<boolean>;
  muteAlert: (alertId: string) => Promise<boolean>;
  subscribeToUpdates: (subscriptions: string[]) => void;
  unsubscribeFromUpdates: () => void;
}

export const useMonitoring = (options: UseMonitoringOptions = {}): UseMonitoringReturn => {
  const {
    apiBaseUrl = 'http://localhost:8000/api',
    authToken,
    refreshInterval = 30000, // 30 seconds
    enableRealTime = true
  } = options;

  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [healthStatus, setHealthStatus] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const refreshIntervalRef = useRef<NodeJS.Timeout>();

  const apiHeaders = {
    'Content-Type': 'application/json',
    ...(authToken && { 'Authorization': `Bearer ${authToken}` })
  };

  const handleApiError = (error: any): string => {
    if (error.response) {
      return error.response.data?.message || `API Error: ${error.response.status}`;
    }
    return error.message || 'An unexpected error occurred';
  };

  const fetchMetrics = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${apiBaseUrl}/metrics`, {
        headers: apiHeaders
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch metrics: ${response.status}`);
      }

      const data = await response.json();
      setMetrics(data);
    } catch (err: any) {
      const errorMessage = handleApiError(err);
      setError(errorMessage);
      console.error('Error fetching metrics:', err);
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, authToken]);

  const fetchAlerts = useCallback(async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/alerts`, {
        headers: apiHeaders
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch alerts: ${response.status}`);
      }

      const data = await response.json();
      setAlerts(data.alerts || []);
    } catch (err: any) {
      console.error('Error fetching alerts:', err);
    }
  }, [apiBaseUrl, authToken]);

  const fetchHealthStatus = useCallback(async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/health`, {
        headers: apiHeaders
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch health status: ${response.status}`);
      }

      const data = await response.json();
      setHealthStatus(data);
    } catch (err: any) {
      console.error('Error fetching health status:', err);
    }
  }, [apiBaseUrl, authToken]);

  const acknowledgeAlert = useCallback(async (alertId: string): Promise<boolean> => {
    try {
      const response = await fetch(`${apiBaseUrl}/alerts/${alertId}/acknowledge`, {
        method: 'POST',
        headers: apiHeaders
      });

      if (!response.ok) {
        throw new Error(`Failed to acknowledge alert: ${response.status}`);
      }

      // Update local alert state
      setAlerts(prev => prev.map(alert => 
        alert.alert_id === alertId 
          ? { ...alert, status: 'acknowledged', acknowledged_at: new Date().toISOString() }
          : alert
      ));

      return true;
    } catch (err: any) {
      console.error('Error acknowledging alert:', err);
      return false;
    }
  }, [apiBaseUrl, authToken]);

  const resolveAlert = useCallback(async (alertId: string): Promise<boolean> => {
    try {
      const response = await fetch(`${apiBaseUrl}/alerts/${alertId}/resolve`, {
        method: 'POST',
        headers: apiHeaders
      });

      if (!response.ok) {
        throw new Error(`Failed to resolve alert: ${response.status}`);
      }

      // Remove resolved alert from local state
      setAlerts(prev => prev.filter(alert => alert.alert_id !== alertId));

      return true;
    } catch (err: any) {
      console.error('Error resolving alert:', err);
      return false;
    }
  }, [apiBaseUrl, authToken]);

  const muteAlert = useCallback(async (alertId: string): Promise<boolean> => {
    try {
      const response = await fetch(`${apiBaseUrl}/alerts/${alertId}/mute`, {
        method: 'POST',
        headers: apiHeaders
      });

      if (!response.ok) {
        throw new Error(`Failed to mute alert: ${response.status}`);
      }

      // Update local alert state
      setAlerts(prev => prev.map(alert => 
        alert.alert_id === alertId 
          ? { ...alert, status: 'muted' }
          : alert
      ));

      return true;
    } catch (err: any) {
      console.error('Error muting alert:', err);
      return false;
    }
  }, [apiBaseUrl, authToken]);

  const subscribeToUpdates = useCallback((subscriptions: string[]) => {
    if (!enableRealTime) return;

    try {
      // Close existing connection
      if (wsRef.current) {
        wsRef.current.close();
      }

      const wsUrl = 'ws://localhost:8006/ws';
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('Monitoring WebSocket connected');
        setConnected(true);

        // Subscribe to channels
        subscriptions.forEach(subscription => {
          ws.send(JSON.stringify({
            type: 'subscribe',
            subscription
          }));
        });
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);

          switch (message.type) {
            case 'metrics_update':
              setMetrics(message.data);
              break;

            case 'alert':
              setAlerts(prev => {
                // Check if alert already exists (by ID)
                const existingIndex = prev.findIndex(alert => alert.alert_id === message.data.alert_id);
                
                if (existingIndex >= 0) {
                  // Update existing alert
                  const updated = [...prev];
                  updated[existingIndex] = { ...updated[existingIndex], ...message.data };
                  return updated;
                } else {
                  // Add new alert
                  return [message.data, ...prev];
                }
              });
              break;

            case 'heartbeat':
              // Keep connection alive
              break;

            case 'connection_established':
              console.log('Monitoring connection established:', message.connection_id);
              break;

            default:
              console.log('Unknown monitoring message type:', message.type);
          }
        } catch (error) {
          console.error('Error parsing monitoring message:', error);
        }
      };

      ws.onclose = (event) => {
        console.log('Monitoring WebSocket closed:', event.code, event.reason);
        setConnected(false);

        // Auto-reconnect if not intentionally closed
        if (event.code !== 1000) {
          setTimeout(() => {
            subscribeToUpdates(subscriptions);
          }, 5000);
        }
      };

      ws.onerror = (error) => {
        console.error('Monitoring WebSocket error:', error);
        setConnected(false);
      };

      wsRef.current = ws;
    } catch (error) {
      console.error('Error establishing monitoring WebSocket:', error);
    }
  }, [enableRealTime]);

  const unsubscribeFromUpdates = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close(1000, 'Unsubscribing');
      wsRef.current = null;
    }
    setConnected(false);
  }, []);

  // Set up periodic data fetching
  useEffect(() => {
    const fetchData = async () => {
      await Promise.all([
        fetchMetrics(),
        fetchAlerts(),
        fetchHealthStatus()
      ]);
    };

    // Initial fetch
    fetchData();

    // Set up interval for non-real-time updates or as fallback
    if (!enableRealTime || !connected) {
      refreshIntervalRef.current = setInterval(fetchData, refreshInterval);
    }

    return () => {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current);
      }
    };
  }, [fetchMetrics, fetchAlerts, fetchHealthStatus, refreshInterval, enableRealTime, connected]);

  // Subscribe to real-time updates on mount
  useEffect(() => {
    if (enableRealTime) {
      subscribeToUpdates([
        'system_metrics',
        'service_health', 
        'alerts',
        'model_status',
        'database_metrics',
        'gpu_metrics'
      ]);
    }

    return () => {
      unsubscribeFromUpdates();
    };
  }, [enableRealTime, subscribeToUpdates, unsubscribeFromUpdates]);

  return {
    metrics,
    alerts,
    healthStatus,
    loading,
    error,
    connected,
    fetchMetrics,
    fetchAlerts,
    fetchHealthStatus,
    acknowledgeAlert,
    resolveAlert,
    muteAlert,
    subscribeToUpdates,
    unsubscribeFromUpdates
  };
};

// Utility hook for historical data
export const useHistoricalMetrics = (timeframe: string = '1h') => {
  const [historicalData, setHistoricalData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchHistoricalData = useCallback(async (authToken?: string) => {
    setLoading(true);

    try {
      const response = await fetch(`http://localhost:8000/api/metrics/historical?timeframe=${timeframe}`, {
        headers: {
          'Content-Type': 'application/json',
          ...(authToken && { 'Authorization': `Bearer ${authToken}` })
        }
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch historical data: ${response.status}`);
      }

      const data = await response.json();
      setHistoricalData(data.data || []);
    } catch (error) {
      console.error('Error fetching historical metrics:', error);
    } finally {
      setLoading(false);
    }
  }, [timeframe]);

  useEffect(() => {
    fetchHistoricalData();
  }, [fetchHistoricalData]);

  return {
    historicalData,
    loading,
    refetch: fetchHistoricalData
  };
};