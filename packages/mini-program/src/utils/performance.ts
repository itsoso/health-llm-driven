/**
 * 性能监控工具
 * 用于追踪小程序页面加载和 API 调用性能
 */

interface PerformanceMetric {
  name: string;
  startTime: number;
  endTime?: number;
  duration?: number;
  metadata?: Record<string, any>;
}

class PerformanceMonitor {
  private metrics: Map<string, PerformanceMetric> = new Map();
  private enabled: boolean = true;
  
  /**
   * 开始计时
   */
  start(name: string, metadata?: Record<string, any>) {
    if (!this.enabled) return;
    
    this.metrics.set(name, {
      name,
      startTime: Date.now(),
      metadata
    });
    
    console.log(`[性能] ${name} 开始`, metadata || '');
  }
  
  /**
   * 结束计时
   */
  end(name: string, metadata?: Record<string, any>) {
    if (!this.enabled) return;
    
    const metric = this.metrics.get(name);
    if (!metric) {
      console.warn(`[性能] 未找到计时器: ${name}`);
      return;
    }
    
    const endTime = Date.now();
    const duration = endTime - metric.startTime;
    
    metric.endTime = endTime;
    metric.duration = duration;
    if (metadata) {
      metric.metadata = { ...metric.metadata, ...metadata };
    }
    
    // 根据时长使用不同的日志级别
    if (duration > 3000) {
      console.error(`[性能-慢] ${name} 耗时 ${duration}ms ⚠️`, metric.metadata || '');
    } else if (duration > 1000) {
      console.warn(`[性能-警告] ${name} 耗时 ${duration}ms`, metric.metadata || '');
    } else {
      console.log(`[性能] ${name} 耗时 ${duration}ms`, metric.metadata || '');
    }
    
    return duration;
  }
  
  /**
   * 记录 API 调用
   */
  async trackAPI<T>(
    name: string,
    apiCall: () => Promise<T>,
    metadata?: Record<string, any>
  ): Promise<T> {
    const trackName = `API-${name}`;
    this.start(trackName, metadata);
    
    try {
      const result = await apiCall();
      this.end(trackName, { success: true });
      return result;
    } catch (error) {
      this.end(trackName, { success: false, error: String(error) });
      throw error;
    }
  }
  
  /**
   * 获取所有指标
   */
  getMetrics(): PerformanceMetric[] {
    return Array.from(this.metrics.values());
  }
  
  /**
   * 获取性能报告
   */
  getReport(): string {
    const metrics = this.getMetrics().filter(m => m.duration);
    
    if (metrics.length === 0) {
      return '暂无性能数据';
    }
    
    const totalDuration = metrics.reduce((sum, m) => sum + (m.duration || 0), 0);
    const avgDuration = totalDuration / metrics.length;
    
    const slowMetrics = metrics.filter(m => (m.duration || 0) > 1000);
    
    let report = `\n========== 性能报告 ==========\n`;
    report += `总计时项: ${metrics.length}\n`;
    report += `总耗时: ${totalDuration}ms\n`;
    report += `平均耗时: ${avgDuration.toFixed(2)}ms\n`;
    report += `慢操作 (>1s): ${slowMetrics.length}\n`;
    
    if (slowMetrics.length > 0) {
      report += `\n慢操作详情:\n`;
      slowMetrics
        .sort((a, b) => (b.duration || 0) - (a.duration || 0))
        .forEach(m => {
          report += `  - ${m.name}: ${m.duration}ms\n`;
        });
    }
    
    report += `==============================\n`;
    
    return report;
  }
  
  /**
   * 清空所有指标
   */
  clear() {
    this.metrics.clear();
  }
  
  /**
   * 启用/禁用监控
   */
  setEnabled(enabled: boolean) {
    this.enabled = enabled;
  }
}

// 导出单例
export const performanceMonitor = new PerformanceMonitor();

/**
 * 装饰器：自动追踪函数执行时间
 */
export function trackPerformance(name?: string) {
  return function (
    target: any,
    propertyKey: string,
    descriptor: PropertyDescriptor
  ) {
    const originalMethod = descriptor.value;
    const trackName = name || `${target.constructor.name}.${propertyKey}`;
    
    descriptor.value = async function (...args: any[]) {
      performanceMonitor.start(trackName);
      try {
        const result = await originalMethod.apply(this, args);
        performanceMonitor.end(trackName);
        return result;
      } catch (error) {
        performanceMonitor.end(trackName, { error: String(error) });
        throw error;
      }
    };
    
    return descriptor;
  };
}

/**
 * 页面性能监控辅助函数
 */
export const pagePerformance = {
  /**
   * 标记页面开始加载
   */
  pageStart(pageName: string) {
    performanceMonitor.start(`页面-${pageName}`);
    performanceMonitor.start(`${pageName}-数据加载`);
  },
  
  /**
   * 标记数据加载完成
   */
  dataLoaded(pageName: string) {
    performanceMonitor.end(`${pageName}-数据加载`);
  },
  
  /**
   * 标记页面渲染完成
   */
  pageReady(pageName: string) {
    performanceMonitor.end(`页面-${pageName}`);
    
    // 输出性能报告
    console.log(performanceMonitor.getReport());
  }
};
