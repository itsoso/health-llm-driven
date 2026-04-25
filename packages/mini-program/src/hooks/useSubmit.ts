/**
 * 防重复提交 Hook
 * 用于处理表单提交，防止用户重复点击
 */

import { useState, useCallback } from 'react';
import Taro from '@tarojs/taro';

interface UseSubmitOptions {
  onSuccess?: (data?: any) => void;
  onError?: (error: any) => void;
  successMessage?: string;
  errorMessage?: string;
}

/**
 * 防重复提交 Hook
 *
 * @example
 * const { isSubmitting, handleSubmit } = useSubmit({
 *   onSuccess: () => {
 *     console.log('提交成功');
 *     loadData();
 *   },
 *   successMessage: '保存成功',
 * });
 *
 * const onSave = handleSubmit(async () => {
 *   await api.save(data);
 * });
 */
export function useSubmit(options: UseSubmitOptions = {}) {
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = useCallback(
    <T = any>(submitFn: () => Promise<T>) => {
      return async () => {
        // 防止重复提交
        if (isSubmitting) {
          console.log('[防重复提交] 正在提交中，忽略本次点击');
          return;
        }

        setIsSubmitting(true);
        try {
          const result = await submitFn();

          // 显示成功提示
          if (options.successMessage) {
            Taro.showToast({
              title: options.successMessage,
              icon: 'success',
            });
          }

          // 调用成功回调
          if (options.onSuccess) {
            options.onSuccess(result);
          }

          return result;
        } catch (error: any) {
          console.error('[提交失败]', error);

          // 显示错误提示
          const errorMsg = options.errorMessage || error?.message || '操作失败';
          Taro.showToast({
            title: errorMsg,
            icon: 'none',
            duration: 2000,
          });

          // 调用错误回调
          if (options.onError) {
            options.onError(error);
          }

          throw error;
        } finally {
          setIsSubmitting(false);
        }
      };
    },
    [isSubmitting, options]
  );

  return {
    isSubmitting,
    handleSubmit,
  };
}

/**
 * 简化版：只返回 loading 状态和包装函数
 *
 * @example
 * const [isSaving, withLoading] = useLoading();
 *
 * const handleSave = async () => {
 *   await withLoading(async () => {
 *     await api.save(data);
 *   });
 * };
 */
export function useLoading(initialState = false): [
  boolean,
  <T>(fn: () => Promise<T>) => Promise<T>
] {
  const [loading, setLoading] = useState(initialState);

  const withLoading = useCallback(
    async <T,>(fn: () => Promise<T>): Promise<T> => {
      if (loading) {
        throw new Error('操作进行中，请勿重复提交');
      }

      setLoading(true);
      try {
        return await fn();
      } finally {
        setLoading(false);
      }
    },
    [loading]
  );

  return [loading, withLoading];
}
