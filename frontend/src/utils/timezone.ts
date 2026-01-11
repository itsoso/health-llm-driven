/**
 * 时区工具函数 - 统一使用北京时间 (UTC+8)
 */

/**
 * 将UTC时间转换为北京时间并格式化
 * @param dateString ISO 8601格式的时间字符串（可能包含时区信息）
 * @param options Intl.DateTimeFormatOptions 格式化选项
 * @returns 格式化后的北京时间字符串
 */
export function formatBeijingTime(
  dateString: string | null | undefined,
  options: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'Asia/Shanghai'
  }
): string {
  if (!dateString) return '--';
  
  try {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return '--';
    
    return new Intl.DateTimeFormat('zh-CN', options).format(date);
  } catch (error) {
    console.error('时间格式化错误:', error);
    return '--';
  }
}

/**
 * 格式化日期时间（简洁版，用于显示）
 * @param dateString ISO 8601格式的时间字符串
 * @returns 格式：YYYY/MM/DD HH:mm:ss
 */
export function formatDateTime(dateString: string | null | undefined): string {
  if (!dateString) return '--';
  
  try {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return '--';
    
    // 使用Intl.DateTimeFormat转换为北京时间，然后手动格式化为 YYYY/MM/DD HH:mm:ss
    const formatter = new Intl.DateTimeFormat('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
      timeZone: 'Asia/Shanghai'
    });
    
    const parts = formatter.formatToParts(date);
    const year = parts.find(p => p.type === 'year')?.value || '';
    const month = parts.find(p => p.type === 'month')?.value.padStart(2, '0') || '';
    const day = parts.find(p => p.type === 'day')?.value.padStart(2, '0') || '';
    const hour = parts.find(p => p.type === 'hour')?.value.padStart(2, '0') || '';
    const minute = parts.find(p => p.type === 'minute')?.value.padStart(2, '0') || '';
    const second = parts.find(p => p.type === 'second')?.value.padStart(2, '0') || '';
    
    return `${year}/${month}/${day} ${hour}:${minute}:${second}`;
  } catch (error) {
    console.error('时间格式化错误:', error);
    return '--';
  }
}

/**
 * 格式化日期（仅日期）
 * @param dateString ISO 8601格式的时间字符串
 * @returns 格式：YYYY/MM/DD
 */
export function formatDate(dateString: string | null | undefined): string {
  return formatBeijingTime(dateString, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone: 'Asia/Shanghai'
  });
}

/**
 * 格式化时间（仅时间）
 * @param dateString ISO 8601格式的时间字符串
 * @returns 格式：HH:mm:ss
 */
export function formatTime(dateString: string | null | undefined): string {
  return formatBeijingTime(dateString, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'Asia/Shanghai'
  });
}

/**
 * 获取当前北京时间
 * @returns Date对象（北京时间）
 */
export function getBeijingNow(): Date {
  const now = new Date();
  // 转换为北京时间字符串，再转回Date对象
  const beijingTimeString = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  }).format(now);
  
  // 解析为本地时间（但实际是北京时间）
  const [datePart, timePart] = beijingTimeString.split(', ');
  const [month, day, year] = datePart.split('/');
  const [hour, minute, second] = timePart.split(':');
  
  return new Date(
    parseInt(year),
    parseInt(month) - 1,
    parseInt(day),
    parseInt(hour),
    parseInt(minute),
    parseInt(second)
  );
}
