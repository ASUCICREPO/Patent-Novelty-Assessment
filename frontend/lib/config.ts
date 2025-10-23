/**
 * API Configuration
 * Centralized configuration for API endpoints
 */

// Get API Gateway URL from environment variable
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || '';

// Validate that API URL is configured
if (!API_BASE_URL) {
  console.warn('NEXT_PUBLIC_API_BASE_URL is not configured. Using relative paths as fallback.');
}

/**
 * Get the full API URL for a given endpoint
 * @param endpoint - The API endpoint (e.g., '/s3', '/dynamodb')
 * @returns The full URL to the API endpoint
 */
export function getApiUrl(endpoint: string): string {
  // Remove leading slash if present
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint.slice(1) : endpoint;
  
  if (API_BASE_URL) {
    return `${API_BASE_URL}${cleanEndpoint}`;
  }
  
  // Fallback to relative path (for development or when API_BASE_URL is not set)
  return `/api/${cleanEndpoint}`;
}

/**
 * API Endpoints
 */
export const API_ENDPOINTS = {
  S3: '/s3',
  DYNAMODB: '/dynamodb',
  AGENT_INVOKE: '/agent-invoke',
} as const;

/**
 * Get API URL for S3 operations
 */
export function getS3ApiUrl(): string {
  return getApiUrl(API_ENDPOINTS.S3);
}

/**
 * Get API URL for DynamoDB operations
 */
export function getDynamoDBApiUrl(): string {
  return getApiUrl(API_ENDPOINTS.DYNAMODB);
}

/**
 * Get API URL for Agent Invoke operations
 */
export function getAgentInvokeApiUrl(): string {
  return getApiUrl(API_ENDPOINTS.AGENT_INVOKE);
}
