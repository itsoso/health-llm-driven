/**
 * 本地缓存工具
 * 用于缓存 API 响应数据，减少不必要的网络请求
 */

import Taro from '@tarojs/taro';

interface CacheItem<T> {
  data: T;
  timestamp: number;
  expiresAt: number;
}

class LocalCache {
  private readonly DEFAULT_TTL = 5 * 60 * 1000; // 默认 5 分钟
  private readonly STORAGE_PREFIX = 'cache_';
  
  /**
   * 获取缓存
   * @param key 缓存键
   * @returns 缓存数据，如果不存在或已过期则返回 null
   */
  get<T>(key: string): T | null {
    try {
      const storageKey = this.STORAGE_PREFIX + key;
      const cached = Taro.getStorageSync(storageKey);
      
      if (!cached) {
        return null;
      }
      
      const cacheItem: CacheItem<T> = JSON.parse(cached);
      
      // 检查是否过期
      if (Date.now() > cacheItem.expiresAt) {
        console.log(`[缓存] ${key} 已过期，清除`);
        this.remove(key);
        return null;
      }
      
      console.log(`[缓存] ${key} 命中 ✅`);
      return cacheItem.data;
      
    } catch (error) {
      console.error(`[缓存] 获取 ${key} 失败:`, error);
      return null;
    }
  }
  
  /**
   * 设置缓存
   * @param key 缓存键
   * @param data 要缓存的数据
   * @param ttl 过期时间（毫秒），默认 5 分钟
   */
  set<T>(key: string, data: T, ttl: number = this.DEFAULT_TTL): void {
    try {
      const storageKey = this.STORAGE_PREFIX + key;
      const cacheItem: CacheItem<T> = {
        data,
        timestamp: Date.now(),
        expiresAt: Date.now() + ttl
      };
      
      Taro.setStorageSync(storageKey, JSON.stringify(cacheItem));
      console.log(`[缓存] ${key} 已保存，TTL: ${ttl}ms`);
      
    } catch (error) {
      console.error(`[缓存] 保存 ${key} 失败:`, error);
    }
  }
  
  /**
   * 移除缓存
   * @param key 缓存键
   */
  remove(key: string): void {
    try {
      const storageKey = this.STORAGE_PREFIX + key;
      Taro.removeStorageSync(storageKey);
      console.log(`[缓存] ${key} 已移除`);
    } catch (error) {
      console.error(`[缓存] 移除 ${key} 失败:`, error);
    }
  }
  
  /**
   * 清空所有缓存
   */
  clear(): void {
    try {
      const { keys } = Taro.getStorageInfoSync();
      const cacheKeys = keys.filter(k => k.startsWith(this.STORAGE_PREFIX));
      
      cacheKeys.forEach(key => {
        Taro.removeStorageSync(key);
      });
      
      console.log(`[缓存] 已清空 ${cacheKeys.length} 个缓存项`);
    } catch (error) {
      console.error('[缓存] 清空失败:', error);
    }
  }
  
  /**
   * 获取缓存统计信息
   */
  getStats(): { total: number; size: string } {
    try {
      const { keys, currentSize, limitSize } = Taro.getStorageInfoSync();
      const cacheKeys = keys.filter(k => k.startsWith(this.STORAGE_PREFIX));
      
      return {
        total: cacheKeys.length,
        size: `${currentSize}KB / ${limitSize}KB`
      };
    } catch (error) {
      console.error('[缓存] 获取统计失败:', error);
      return { total: 0, size: '0KB / 0KB' };
    }
  }
  
  /**
   * 包装 API 调用，自动处理缓存
   * @param key 缓存键
   * @param apiCall API 调用函数
   * @param ttl 缓存时间（毫秒）
   * @param forceRefresh 是否强制刷新
   */
  async withCache<T>(
    key: string,
    apiCall: () => Promise<T>,
    ttl: number = this.DEFAULT_TTL,
    forceRefresh: boolean = false
  ): Promise<T> {
    // 如果不强制刷新，先尝试从缓存获取
    if (!forceRefresh) {
      const cached = this.get<T>(key);
      if (cached !== null) {
        return cached;
      }
    }
    
    // 缓存未命中或强制刷新，调用 API
    console.log(`[缓存] ${key} 未命中，请求 API`);
    const data = await apiCall();
    
    // 保存到缓存
    this.set(key, data, ttl);
    
    return data;
  }
}

// 导出单例
export const localCache = new LocalCache();

/**
 * 缓存配置
 * 定义不同数据的缓存时间
 */
export const CacheConfig = {
  // Garmin 数据：5 分钟（运动数据变化较快）
  GARMIN_DATA: 5 * 60 * 1000,
  
  // 每日推荐：10 分钟（推荐相对稳定）
  DAILY_RECOMMENDATION: 10 * 60 * 1000,
  
  // 鼻炎记录：3 分钟（可能频繁更新）
  RHINITIS_RECORD: 3 * 60 * 1000,
  
  // 运动记录：5 分钟
  WORKOUT_RECORDS: 5 * 60 * 1000,
  
  // 饮食摘要：5 分钟
  DIET_SUMMARY: 5 * 60 * 1000,
  
  // 早间简报：30 分钟（生成成本高，可以缓存久一点）
  MORNING_BRIEFING: 30 * 60 * 1000,
  
  // AI 推荐：30 分钟（生成成本高）
  AI_RECOMMENDATION: 30 * 60 * 1000,
  
  // 当前提醒：2 分钟（需要及时更新）
  CURRENT_REMINDERS: 2 * 60 * 1000,
  
  // 每日日程：5 分钟
  DAILY_SCHEDULE: 5 * 60 * 1000,
  
  // 运动指导：1 小时（不常变化）
  WORKOUT_GUIDANCE: 60 * 60 * 1000,
};

/**
 * 生成带日期的缓存键
 * @param prefix 前缀
 * @param date 日期（可选，默认今天）
 */
export function getCacheKey(prefix: string, date?: Date): string {
  const d = date || new Date();
  const dateStr = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  return `${prefix}_${dateStr}`;
}
