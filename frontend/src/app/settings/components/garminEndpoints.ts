const API_BASE = '/api';

export const GARMIN_ENDPOINTS = {
  credentials: `${API_BASE}/auth/garmin/credentials`,
  connect: `${API_BASE}/auth/garmin/connect`,
} as const;
