// Taskbolt SaaS - API Client
// 
// Centralized API client with:
// - Automatic auth token injection
// - Tenant context handling
// - Error handling and retries
// - Type-safe responses

import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios';
import { getIdToken, getCurrentUser, signOutUser } from './firebase';

// API base URL - uses relative path when hosted on same domain
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

// ============================================================================
// Types
// ============================================================================

export interface Tenant {
  id: string;
  slug: string;
  name: string;
  plan: string;
  limits: {
    max_agents: number;
    max_users: number;
    max_storage_bytes: number;
  };
  stats: {
    users_count: number;
    agents_count: number;
  };
}

export interface User {
  user_id: string;
  email: string;
  role: string;
  tenant: Tenant;
}

export interface Agent {
  id: string;
  external_id: string;
  name: string;
  description: string;
  is_active: boolean;
  created_at: string;
  updated_at?: string;
  channels?: Record<string, unknown>;
  mcp?: Record<string, unknown>;
  tools?: Record<string, unknown>;
  security?: Record<string, unknown>;
}

export interface Chat {
  id: string;
  external_id: string;
  name: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ApiKey {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  last_used_at: string | null;
  created_at: string;
}

export interface Usage {
  tenant_id: string;
  total_records: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_cents: number;
  estimated_cost_dollars: number;
}

export interface ApiError {
  detail: string;
  code: string;
  retry_after?: number;
}

// ============================================================================
// API Client Class
// ============================================================================

class ApiClient {
  private client: AxiosInstance;
  private refreshAttempted = false;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.setupInterceptors();
  }

  private setupInterceptors() {
    // Request interceptor - add auth token
    this.client.interceptors.request.use(
      async (config: InternalAxiosRequestConfig) => {
        const token = await getIdToken();
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Response interceptor - handle errors
    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError<ApiError>) => {
        const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

        // Handle 401 - Unauthorized
        if (error.response?.status === 401 && !originalRequest._retry) {
          originalRequest._retry = true;

          // Try to refresh token
          if (!this.refreshAttempted) {
            this.refreshAttempted = true;
            try {
              const user = getCurrentUser();
              if (user) {
                const newToken = await user.getIdToken(true);
                originalRequest.headers.Authorization = `Bearer ${newToken}`;
                return this.client(originalRequest);
              }
            } catch (refreshError) {
              // Refresh failed, sign out user
              await signOutUser();
              window.location.href = '/login';
              return Promise.reject(refreshError);
            } finally {
              this.refreshAttempted = false;
            }
          }
        }

        // Handle 429 - Rate Limited
        if (error.response?.status === 429) {
          const retryAfter = error.response?.data?.retry_after || 60;
          console.warn(`Rate limited. Retry after ${retryAfter} seconds.`);
        }

        return Promise.reject(error);
      }
    );
  }

  // =========================================================================
  // Authentication
  // =========================================================================

  async getAuthStatus() {
    const { data } = await this.client.get('/auth/status');
    return data;
  }

  async getCurrentUser(): Promise<User> {
    const { data } = await this.client.get('/auth/me');
    return data;
  }

  // =========================================================================
  // Tenant
  // =========================================================================

  async getTenant(): Promise<Tenant> {
    const { data } = await this.client.get('/tenant');
    return data;
  }

  // =========================================================================
  // Agents
  // =========================================================================

  async listAgents(): Promise<{ agents: Agent[] }> {
    const { data } = await this.client.get('/agents');
    return data;
  }

  async getAgent(agentId: string): Promise<Agent> {
    const { data } = await this.client.get(`/agents/${agentId}`);
    return data;
  }

  async createAgent(agent: Partial<Agent>): Promise<Agent> {
    const { data } = await this.client.post('/agents', agent);
    return data;
  }

  async updateAgent(agentId: string, updates: Partial<Agent>): Promise<Agent> {
    const { data } = await this.client.patch(`/agents/${agentId}`, updates);
    return data;
  }

  async deleteAgent(agentId: string): Promise<void> {
    await this.client.delete(`/agents/${agentId}`);
  }

  // =========================================================================
  // Chats
  // =========================================================================

  async listChats(agentId: string): Promise<{ chats: Chat[] }> {
    const { data } = await this.client.get(`/agents/${agentId}/chats`);
    return data;
  }

  // =========================================================================
  // API Keys
  // =========================================================================

  async listApiKeys(): Promise<{ api_keys: ApiKey[] }> {
    const { data } = await this.client.get('/api-keys');
    return data;
  }

  async createApiKey(name: string, scopes: string[] = ['read', 'write']): Promise<{ key: string } & ApiKey> {
    const { data } = await this.client.post('/api-keys', { name, scopes });
    return data;
  }

  async revokeApiKey(keyId: string): Promise<void> {
    await this.client.delete(`/api-keys/${keyId}`);
  }

  // =========================================================================
  // Usage
  // =========================================================================

  async getUsage(): Promise<Usage> {
    const { data } = await this.client.get('/usage');
    return data;
  }

  // =========================================================================
  // Chat Streaming
  // =========================================================================

  async *streamChat(
    agentId: string,
    message: string,
    chatId?: string,
    onToken?: (token: string) => void
  ): AsyncGenerator<string> {
    const token = await getIdToken();
    
    const response = await fetch(`${API_BASE_URL}/agents/${agentId}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        message,
        chat_id: chatId,
      }),
    });

    if (!response.ok) {
      throw new Error(`Chat failed: ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') return;
          if (onToken) onToken(data);
          yield data;
        }
      }
    }
  }
}

// Export singleton instance
export const api = new ApiClient();
export default api;
