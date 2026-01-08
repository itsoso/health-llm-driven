/**
 * 用户相关类型定义
 */

export interface User {
  id: number;
  email?: string;
  username?: string;
  name: string;
  avatar_url?: string;
  gender?: string;
  birth_date?: string;
  phone?: string;
  is_active: boolean;
  is_admin: boolean;
  wechat_openid?: string;
  created_at: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface WechatLoginRequest {
  code: string;
  nickname?: string;
  avatar_url?: string;
}

export interface WechatLoginResponse {
  access_token: string;
  token_type: string;
  user_id: number;
  is_new_user: boolean;
  nickname?: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  name: string;
  username?: string;
}

