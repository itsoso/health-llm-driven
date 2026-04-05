export function relativeTime(dateStr: string): string {
  if (!dateStr) return '';
  // 后端返回北京时间但不带时区后缀，补上+08:00确保正确解析
  let normalized = dateStr.replace(' ', 'T');
  if (!/[Z+\-]\d{2}/.test(normalized) && !normalized.endsWith('Z')) {
    normalized += '+08:00';
  }
  const now = Date.now();
  const date = new Date(normalized).getTime();
  if (isNaN(date)) return dateStr;
  const diff = now - date;
  if (diff < 0) return '刚刚';
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes}分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}小时前`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}天前`;
  return new Date(normalized).toLocaleDateString('zh-CN');
}
