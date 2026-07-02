import { describe, expect, it } from 'vitest';
import { pickPastedMedicalImportFile, type PastedItemLike } from '../pastedMedicalImportFile';

function fileItem(type: string, name = 'f'): PastedItemLike {
  const file = new File(['x'], name, { type });
  return { kind: 'file', type, getAsFile: () => file };
}

function stringItem(type = 'text/plain'): PastedItemLike {
  return { kind: 'string', type, getAsFile: () => null };
}

describe('pickPastedMedicalImportFile', () => {
  it('截屏/拷贝的图片(image file item)→ 取图', () => {
    const png = fileItem('image/png', 'shot.png');
    expect(pickPastedMedicalImportFile([png])?.name).toBe('shot.png');
  });

  it('浏览器"拷贝图像":string(html/url) + image 混合 → 取图(不被伴生文本挡住)', () => {
    const items = [stringItem('text/html'), stringItem('text/plain'), fileItem('image/jpeg', 'mri.jpg')];
    expect(pickPastedMedicalImportFile(items)?.name).toBe('mri.jpg');
  });

  it('Finder 拷 PDF 文件 → 取原文件', () => {
    const pdf = fileItem('application/pdf', '诊断报告.pdf');
    expect(pickPastedMedicalImportFile([pdf])?.name).toBe('诊断报告.pdf');
  });

  it('划选文字(只有 string item)→ null,走默认文本粘贴', () => {
    expect(pickPastedMedicalImportFile([stringItem('text/plain')])).toBeNull();
  });

  it('不可导入的文件类型(csv/docx)→ null', () => {
    expect(pickPastedMedicalImportFile([fileItem('text/csv', 'a.csv')])).toBeNull();
    expect(
      pickPastedMedicalImportFile([
        fileItem('application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'b.docx'),
      ]),
    ).toBeNull();
  });

  it('多文件:与 input.files[0] 对齐,取第一个可导入项', () => {
    const items = [fileItem('text/csv', 'skip.csv'), fileItem('image/webp', 'first.webp'), fileItem('image/png', 'second.png')];
    expect(pickPastedMedicalImportFile(items)?.name).toBe('first.webp');
  });

  it('heic 等 image/* 子类型 → 取图', () => {
    expect(pickPastedMedicalImportFile([fileItem('image/heic', 'photo.heic')])?.name).toBe('photo.heic');
  });

  it('getAsFile 返回 null 的坏 item → 跳过继续找', () => {
    const broken: PastedItemLike = { kind: 'file', type: 'image/png', getAsFile: () => null };
    const good = fileItem('image/png', 'ok.png');
    expect(pickPastedMedicalImportFile([broken, good])?.name).toBe('ok.png');
  });

  it('空/缺失 items → null', () => {
    expect(pickPastedMedicalImportFile([])).toBeNull();
    expect(pickPastedMedicalImportFile(null)).toBeNull();
    expect(pickPastedMedicalImportFile(undefined)).toBeNull();
  });
});
