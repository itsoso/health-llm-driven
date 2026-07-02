/**
 * ⌘V/Ctrl+V 粘贴内容 → 体检导入文件(纯函数,vitest 覆盖)。
 *
 * 镜像 mac 端 PastedContentClassifier 的语义,按 Web 剪贴板形态适配:
 *  - 浏览器"拷贝图像"(医院报告页等):image file item(常伴 text/html)→ 取图导入
 *  - 截屏直接粘贴:image file item → 取图导入
 *  - Finder/资源管理器 ⌘C 文件:file item(pdf/图片)→ 取原文件导入
 *  - 划选网页/文档文字:只有 string item,无 file item → 返回 null,走默认文本粘贴
 *
 * 与隐藏 file input 的 accept 同源(application/pdf + image/*);
 * 与 input.files[0] 行为对齐:多文件只取第一个可导入项。
 */
const ACCEPTED_EXACT_TYPES = new Set(['application/pdf']);

function isAcceptedType(mime: string): boolean {
  return mime.startsWith('image/') || ACCEPTED_EXACT_TYPES.has(mime);
}

/** DataTransferItem 的最小结构(便于测试注入假对象,不依赖 DOM 环境)。 */
export interface PastedItemLike {
  kind: string;
  type: string;
  getAsFile(): File | null;
}

export function pickPastedMedicalImportFile(
  items: ArrayLike<PastedItemLike> | null | undefined,
): File | null {
  if (!items) return null;
  for (const item of Array.from(items)) {
    if (item.kind !== 'file') continue;
    if (!isAcceptedType(item.type)) continue;
    const file = item.getAsFile();
    if (file) return file;
  }
  return null;
}
