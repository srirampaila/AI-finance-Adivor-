/**
 * Central API Client Abstraction Layer
 * 
 * Supports GET, POST, PUT, PATCH, DELETE operations.
 * Operates in Real Backend HTTP Mode (default) or Mock Mode based on VITE_API_MODE / VITE_USE_MOCK_API.
 * Automatically handles JWT Authorization headers, standardized error parsing, and 401 session expiry.
 */

import type { ApiResponse, ApiError } from '../types';
import { mockAuthService } from '../services/mock/auth.mock';
import { mockDashboardService } from '../services/mock/dashboard.mock';
import { mockAdvisorService } from '../services/mock/advisor.mock';
import { mockInvestmentsService } from '../services/mock/investments.mock';
import { mockTransactionsService } from '../services/mock/transactions.mock';
import { mockGoalsService } from '../services/mock/goals.mock';
import { mockAnalyticsService } from '../services/mock/analytics.mock';
import { mockReportsService } from '../services/mock/reports.mock';
import { mockNotificationsService } from '../services/mock/notifications.mock';
import { mockSettingsService } from '../services/mock/settings.mock';
import { mockFinancialProfileService } from '../services/mock/financial-profile.mock';
import { API_ENDPOINTS } from './api-contracts';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';
const USE_MOCK_API = (import.meta.env.VITE_API_MODE === 'mock') || (import.meta.env.VITE_USE_MOCK_API === 'true');

const AUTH_STORAGE_KEY = 'ai_finance_auth_session';

class ApiClient {
  private baseUrl: string;
  private useMock: boolean;

  constructor(baseUrl = BASE_URL, useMock = USE_MOCK_API) {
    this.baseUrl = baseUrl;
    this.useMock = useMock;
  }

  /**
   * Set API mode dynamically if needed
   */
  public setMockMode(enabled: boolean) {
    this.useMock = enabled;
  }

  public isMockMode(): boolean {
    return this.useMock;
  }

  /**
   * Safe URL builder preventing double /api/v1 prefixing
   */
  private buildUrl(endpoint: string): string {
    if (endpoint.startsWith('http://') || endpoint.startsWith('https://')) {
      return endpoint;
    }
    const cleanBase = this.baseUrl.replace(/\/+$/, '');
    const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;

    if (cleanBase.endsWith('/api/v1') && cleanEndpoint.startsWith('/api/v1')) {
      return `${cleanBase}${cleanEndpoint.substring(7)}`;
    }
    return `${cleanBase}${cleanEndpoint}`;
  }

  /**
   * Retrieve JWT access token from session storage
   */
  private getAuthHeader(): Record<string, string> {
    if (typeof window === 'undefined') return {};
    try {
      const sessionStr = sessionStorage.getItem(AUTH_STORAGE_KEY);
      if (sessionStr) {
        const parsed = JSON.parse(sessionStr);
        if (parsed?.token) {
          return { Authorization: `Bearer ${parsed.token}` };
        }
      }
    } catch {
      // Ignore parse errors
    }
    return {};
  }

  /**
   * Universal fetch execution with standardized ApiResponse and ApiError handling
   */
  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<ApiResponse<T>> {
    if (this.useMock) {
      return this.handleMockRequest<T>(endpoint, options);
    }

    const url = this.buildUrl(endpoint);
    const authHeaders = this.getAuthHeader();

    try {
      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders,
          ...options.headers,
        },
        ...options,
      });

      // Handle 401 Unauthorized globally
      if (response.status === 401) {
        if (typeof window !== 'undefined') {
          sessionStorage.removeItem(AUTH_STORAGE_KEY);
          window.dispatchEvent(new CustomEvent('auth:unauthorized'));
        }
      }

      let json: any = null;
      const text = await response.text();
      try {
        json = text ? JSON.parse(text) : null;
      } catch {
        json = null;
      }

      if (!response.ok) {
        const error: ApiError = {
          code: json?.error?.code || json?.code || `HTTP_${response.status}`,
          message: json?.error?.message || json?.message || (text && text.length < 300 ? text : `HTTP ${response.status}: ${response.statusText}`),
          details: json?.error?.details || json?.details,
        };
        throw error;
      }

      // If backend returns standard { success: true, data: T, ... }
      if (json && typeof json === 'object' && 'success' in json && 'data' in json) {
        return json as ApiResponse<T>;
      }

      // If backend returns raw data object
      return {
        success: true,
        data: (json ?? text) as T,
        timestamp: new Date().toISOString(),
      };
    } catch (err: any) {
      if (err.code && err.message) {
        throw err;
      }
      throw {
        code: 'NETWORK_ERROR',
        message: err.message || 'Network request failed. Please check your connection.',
      } as ApiError;
    }
  }

  /**
   * Route mock requests to corresponding mock service methods
   */
  private async handleMockRequest<T>(endpoint: string, options: RequestInit): Promise<ApiResponse<T>> {
    const method = (options.method || 'GET').toUpperCase();
    const body = options.body ? JSON.parse(options.body as string) : {};

    // Auth
    if ((endpoint === API_ENDPOINTS.AUTH.LOGIN || endpoint === '/auth/login') && method === 'POST') {
      return mockAuthService.login(body) as Promise<ApiResponse<T>>;
    }
    if ((endpoint === API_ENDPOINTS.AUTH.SIGNUP || endpoint === API_ENDPOINTS.AUTH.REGISTER || endpoint === '/auth/signup') && method === 'POST') {
      return mockAuthService.signup(body) as Promise<ApiResponse<T>>;
    }
    if ((endpoint === API_ENDPOINTS.AUTH.LOGOUT || endpoint === '/auth/logout') && method === 'POST') {
      return mockAuthService.logout() as Promise<ApiResponse<T>>;
    }
    if ((endpoint === API_ENDPOINTS.AUTH.ME || endpoint === '/auth/me') && method === 'GET') {
      return mockAuthService.getCurrentUser() as Promise<ApiResponse<T>>;
    }

    // Dashboard
    if (endpoint === API_ENDPOINTS.DASHBOARD.GET_DATA && method === 'GET') {
      return mockDashboardService.getDashboardData() as Promise<ApiResponse<T>>;
    }

    // Advisor
    if (endpoint === API_ENDPOINTS.ADVISOR.CHAT && method === 'POST') {
      return mockAdvisorService.sendMessage(body.message) as Promise<ApiResponse<T>>;
    }

    // Transactions
    if (endpoint === API_ENDPOINTS.TRANSACTIONS.LIST && method === 'GET') {
      return mockTransactionsService.getTransactions() as Promise<ApiResponse<T>>;
    }
    if (endpoint === API_ENDPOINTS.TRANSACTIONS.CREATE && method === 'POST') {
      return mockTransactionsService.createTransaction(body) as Promise<ApiResponse<T>>;
    }

    // Goals
    if (endpoint === API_ENDPOINTS.GOALS.LIST && method === 'GET') {
      return mockGoalsService.getGoals() as Promise<ApiResponse<T>>;
    }
    if (endpoint === API_ENDPOINTS.GOALS.CREATE && method === 'POST') {
      return mockGoalsService.createGoal(body) as Promise<ApiResponse<T>>;
    }

    // Analytics
    if (endpoint.startsWith(API_ENDPOINTS.ANALYTICS.SUMMARY) && method === 'GET') {
      return mockAnalyticsService.getAnalyticsSummary() as Promise<ApiResponse<T>>;
    }

    // Reports
    if (endpoint === API_ENDPOINTS.REPORTS.LIST && method === 'GET') {
      return mockReportsService.getReports() as Promise<ApiResponse<T>>;
    }
    if (endpoint === API_ENDPOINTS.REPORTS.GENERATE && method === 'POST') {
      return mockReportsService.generateReport(body.type, body.period) as Promise<ApiResponse<T>>;
    }

    // Notifications
    if (endpoint === API_ENDPOINTS.NOTIFICATIONS.LIST && method === 'GET') {
      return mockNotificationsService.getNotifications() as Promise<ApiResponse<T>>;
    }
    if (endpoint === API_ENDPOINTS.NOTIFICATIONS.MARK_ALL_READ && method === 'POST') {
      return mockNotificationsService.markAllAsRead() as Promise<ApiResponse<T>>;
    }
    if (endpoint === API_ENDPOINTS.NOTIFICATIONS.CLEAR_ALL && method === 'POST') {
      return mockNotificationsService.clearAll() as Promise<ApiResponse<T>>;
    }

    // Settings
    if (endpoint === API_ENDPOINTS.SETTINGS.GET && method === 'GET') {
      return mockSettingsService.getSettings() as Promise<ApiResponse<T>>;
    }
    if (endpoint === API_ENDPOINTS.SETTINGS.UPDATE_PROFILE && method === 'POST') {
      return mockSettingsService.updateProfile(body) as Promise<ApiResponse<T>>;
    }
    if (endpoint === API_ENDPOINTS.SETTINGS.UPDATE_PREFERENCES && method === 'POST') {
      return mockSettingsService.updatePreferences(body) as Promise<ApiResponse<T>>;
    }

    // Investments
    if (endpoint === API_ENDPOINTS.INVESTMENTS.SUMMARY && method === 'GET') {
      const data = await mockInvestmentsService.getPortfolioSummary();
      return { success: true, data: data as unknown as T, timestamp: new Date().toISOString() };
    }
    if (endpoint === API_ENDPOINTS.INVESTMENTS.POSITIONS && method === 'GET') {
      const data = await mockInvestmentsService.getPositions();
      return { success: true, data: data as unknown as T, timestamp: new Date().toISOString() };
    }
    if (endpoint === API_ENDPOINTS.INVESTMENTS.INDICES && method === 'GET') {
      const data = await mockInvestmentsService.getMarketIndices();
      return { success: true, data: data as unknown as T, timestamp: new Date().toISOString() };
    }
    if (endpoint === API_ENDPOINTS.INVESTMENTS.NEWS && method === 'GET') {
      const data = await mockInvestmentsService.getMarketNews();
      return { success: true, data: data as unknown as T, timestamp: new Date().toISOString() };
    }
    if (endpoint === API_ENDPOINTS.INVESTMENTS.SENTIMENT && method === 'GET') {
      const data = await mockInvestmentsService.getMarketSentiment();
      return { success: true, data: data as unknown as T, timestamp: new Date().toISOString() };
    }
    if (endpoint === API_ENDPOINTS.INVESTMENTS.RISK && method === 'GET') {
      const data = await mockInvestmentsService.getRiskMetrics();
      return { success: true, data: data as unknown as T, timestamp: new Date().toISOString() };
    }
    if (endpoint === API_ENDPOINTS.INVESTMENTS.INSIGHTS && method === 'GET') {
      const data = await mockInvestmentsService.getInvestmentInsights();
      return { success: true, data: data as unknown as T, timestamp: new Date().toISOString() };
    }

    // Financial Profile
    if ((endpoint === API_ENDPOINTS.FINANCIAL_PROFILE.GET || endpoint === '/financial-profile') && method === 'GET') {
      return mockFinancialProfileService.getProfile() as Promise<ApiResponse<T>>;
    }
    if ((endpoint === API_ENDPOINTS.FINANCIAL_PROFILE.STATUS || endpoint === '/financial-profile/status') && method === 'GET') {
      return mockFinancialProfileService.getStatus() as Promise<ApiResponse<T>>;
    }
    if ((endpoint === API_ENDPOINTS.FINANCIAL_PROFILE.SAVE || endpoint === '/financial-profile') && method === 'POST') {
      return mockFinancialProfileService.saveProfile(body) as Promise<ApiResponse<T>>;
    }
    if ((endpoint === API_ENDPOINTS.FINANCIAL_PROFILE.UPDATE || endpoint === '/financial-profile') && (method === 'PATCH' || method === 'POST')) {
      return mockFinancialProfileService.updateProfile(body) as Promise<ApiResponse<T>>;
    }

    throw {
      code: 'NOT_FOUND',
      message: `Mock endpoint ${method} ${endpoint} is not implemented.`,
    } as ApiError;
  }

  // Public HTTP Method Wrappers
  public async get<T>(endpoint: string, options?: RequestInit): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { ...options, method: 'GET' });
  }

  public async post<T>(endpoint: string, body?: unknown, options?: RequestInit): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'POST',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  }

  public async put<T>(endpoint: string, body?: unknown, options?: RequestInit): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'PUT',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  }

  public async patch<T>(endpoint: string, body?: unknown, options?: RequestInit): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'PATCH',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  }

  public async delete<T>(endpoint: string, options?: RequestInit): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { ...options, method: 'DELETE' });
  }

  // Feature specific shortcut references for mock compatibility
  public auth = mockAuthService;
  public dashboard = mockDashboardService;
  public investments = mockInvestmentsService;
  public transactions = mockTransactionsService;
  public goals = mockGoalsService;
  public analytics = mockAnalyticsService;
  public reports = mockReportsService;
  public notifications = mockNotificationsService;
  public settings = mockSettingsService;
  public financialProfile = mockFinancialProfileService;
}

export const apiClient = new ApiClient();
