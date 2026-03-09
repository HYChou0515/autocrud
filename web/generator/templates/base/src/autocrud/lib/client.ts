import axios from 'axios';

const baseURL = import.meta.env.VITE_API_URL || '/api';
console.log('🔧 Axios baseURL:', baseURL);

export const client = axios.create({
  baseURL,
});

/**
 * Resolve the API base URL.
 *
 * This is the same value used by the Axios client instance.
 * Non-Axios callers (e.g. `fetch` for streaming) should use this
 * to stay consistent with the proxy / production configuration.
 */
export function getBaseUrl(): string {
  return baseURL;
}

// Response interceptor for error handling
client.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('[API Error]', error.response?.status, error.response?.data);
    return Promise.reject(error);
  },
);
