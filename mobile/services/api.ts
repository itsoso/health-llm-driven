import axios from 'axios';
import * as SecureStore from 'expo-secure-store';

const TOKEN_KEY = 'auth_token';

const api = axios.create({
  baseURL: 'https://health.executor.life/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use(
  async (config) => {
    try {
      const token = await SecureStore.getItemAsync(TOKEN_KEY);
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    } catch {
      // SecureStore not available (e.g. web), ignore
    }
    return config;
  },
  (error) => Promise.reject(error),
);

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      try {
        await SecureStore.deleteItemAsync(TOKEN_KEY);
      } catch {
        // ignore
      }
    }
    return Promise.reject(error);
  },
);

export default api;
export { TOKEN_KEY };
