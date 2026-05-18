const CLOUD_TTS_MAX_CHARS = 480;
const SENTENCE_END = /[。！？!?]/;
const SOFT_BREAK = /[，,；;、：:]/;

function isDecimalPoint(text: string, index: number): boolean {
  return (
    text[index] === '.'
    && /\d/.test(text[index - 1] || '')
    && /\d/.test(text[index + 1] || '')
  );
}

function isSentenceEnd(text: string, index: number): boolean {
  const ch = text[index];
  if (SENTENCE_END.test(ch)) return true;
  return ch === '.' && !isDecimalPoint(text, index);
}

function pushHardWrapped(out: string[], raw: string, maxChars: number) {
  let text = raw.trim();
  while (text.length > maxChars) {
    let cut = -1;
    for (let i = maxChars; i >= Math.floor(maxChars * 0.55); i -= 1) {
      if (SOFT_BREAK.test(text[i] || '')) {
        cut = i + 1;
        break;
      }
    }
    if (cut <= 0) cut = maxChars;
    const piece = text.slice(0, cut).trim();
    if (piece) out.push(piece);
    text = text.slice(cut).trim();
  }
  if (text) out.push(text);
}

export function splitTextForCloudTts(text: string, maxChars = CLOUD_TTS_MAX_CHARS): string[] {
  const normalized = text.replace(/\s+/g, ' ').trim();
  if (!normalized) return [];

  const sentences: string[] = [];
  let start = 0;
  for (let i = 0; i < normalized.length; i += 1) {
    if (!isSentenceEnd(normalized, i)) continue;
    const sentence = normalized.slice(start, i + 1).trim();
    if (sentence) sentences.push(sentence);
    start = i + 1;
  }
  const tail = normalized.slice(start).trim();
  if (tail) sentences.push(tail);

  const chunks: string[] = [];
  let current = '';
  for (const sentence of sentences) {
    if (sentence.length > maxChars) {
      if (current) {
        chunks.push(current);
        current = '';
      }
      pushHardWrapped(chunks, sentence, maxChars);
      continue;
    }
    const next = current ? `${current} ${sentence}` : sentence;
    if (next.length <= maxChars) {
      current = next;
    } else {
      if (current) chunks.push(current);
      current = sentence;
    }
  }
  if (current) chunks.push(current);
  return chunks.filter(Boolean);
}
