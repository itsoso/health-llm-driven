/** Bind a queued query to its cache owner, rather than the session at dispatch time. */
export function queryOwnerHeaders(expectedSubject: number | undefined): Record<string, string> {
  if (expectedSubject === undefined || !Number.isSafeInteger(expectedSubject) || expectedSubject <= 0) {
    throw new Error('请先登录后重试，本次查询未发送。');
  }
  return { 'X-Reva-AI-Subject': String(expectedSubject) };
}
