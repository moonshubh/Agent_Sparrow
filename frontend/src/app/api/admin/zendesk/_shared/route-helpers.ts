/**
 * Shared utilities for Zendesk admin API routes
 * 
 * Provides common error handling, response building, and upstream API call patterns
 * to reduce duplication across route handlers.
 */

import { requireAdminApiConfig } from './admin-api-config';
import { verifyZendeskAdminAccess } from '@/services/security/zendesk-admin-auth';

/**
 * Standard JSON response headers for API routes
 */
export const JSON_HEADERS = { 'Content-Type': 'application/json' } as const;

/**
 * Authentication error reasons
 */
export type AuthErrorReason = 'not_authenticated' | 'forbidden' | 'unsupported';

/**
 * Builds a standardized authentication error response
 */
export function buildAuthError(reason: AuthErrorReason): Response {
  const status = reason === 'forbidden' ? 403 : reason === 'unsupported' ? 500 : 401;
  return new Response(JSON.stringify({ error: reason }), { 
    status, 
    headers: JSON_HEADERS 
  });
}

/**
 * Builds a standardized server configuration error response
 */
export function buildConfigError(): Response {
  return new Response(
    JSON.stringify({ error: 'server_config_missing' }), 
    { status: 500, headers: JSON_HEADERS }
  );
}

/**
 * Builds a standardized upstream unreachable error response
 */
export function buildUpstreamError(): Response {
  return new Response(
    JSON.stringify({ error: 'upstream_unreachable' }), 
    { status: 502, headers: JSON_HEADERS }
  );
}

/**
 * Validates admin access and returns auth result
 * Returns null if authorized, otherwise returns error response
 */
export async function validateAdminAccess(): Promise<Response | null> {
  const auth = await verifyZendeskAdminAccess();
  if (!auth.ok) {
    return buildAuthError(auth.reason ?? 'not_authenticated');
  }
  return null;
}

/**
 * Gets admin API configuration, handling errors
 * Returns config if successful, otherwise returns error response
 */
export function getAdminConfig(): { apiBase: string; token: string } | Response {
  try {
    return requireAdminApiConfig();
  } catch (err) {
    console.error('getAdminConfig failed to load admin API config', err);
    return buildConfigError();
  }
}

/**
 * Options for making upstream API calls
 */
export interface UpstreamCallOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: string;
  headers?: Record<string, string>;
  searchParams?: Record<string, string>;
}

/**
 * Makes an upstream API call to the backend with standardized error handling
 * 
 * @param path - API path (e.g., '/api/v1/integrations/zendesk/admin/health')
 * @param config - Admin API configuration
 * @param options - Request options
 * @returns Response from upstream or error response
 */
export async function callUpstream(
  path: string,
  config: { apiBase: string; token: string },
  options: UpstreamCallOptions = {}
): Promise<Response> {
  const { method = 'GET', body, headers = {}, searchParams } = options;
  
  // Build URL - ensure path starts with / and combine with apiBase
  const baseUrl = config.apiBase.endsWith('/') 
    ? config.apiBase.slice(0, -1) 
    : config.apiBase;
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  const url = new URL(cleanPath, baseUrl);
  
  if (searchParams) {
    Object.entries(searchParams).forEach(([key, value]) => {
      url.searchParams.set(key, value);
    });
  }

  try {
    const fetchOptions: RequestInit = {
      method,
      headers: {
        'X-Internal-Token': config.token,
        ...headers,
      },
      cache: 'no-store',
    };
    
    // Only include body if provided
    if (body !== undefined) {
      fetchOptions.body = body;
    }
    
    const response = await fetch(url.toString(), fetchOptions);

    // Preserve response headers (e.g., X-Total-Count for pagination)
    const responseHeaders = new Headers();
    const contentType = response.headers.get('content-type');
    if (contentType) {
      responseHeaders.set('Content-Type', contentType);
    }
    
    // Copy custom headers (e.g., pagination headers)
    const totalCount = response.headers.get('X-Total-Count');
    if (totalCount) {
      responseHeaders.set('X-Total-Count', totalCount);
    }

    const text = await response.text();
    return new Response(text, { 
      status: response.status, 
      headers: responseHeaders 
    });
  } catch {
    return buildUpstreamError();
  }
}

/**
 * Exported for testing
 */
export const __testing__ = {
  buildAuthError,
  buildConfigError,
  buildUpstreamError,
  validateAdminAccess,
  getAdminConfig,
  callUpstream,
};
