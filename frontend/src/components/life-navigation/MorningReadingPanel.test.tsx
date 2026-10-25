import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { getMorningReadings, getMorningReading } from '@/services/morningReadings';
import MorningReadingPanel from './MorningReadingPanel';
vi.mock('@/services/morningReadings', () => ({ getMorningReadings: vi.fn(), getMorningReading: vi.fn() }));
const item = { report_id: 'b3cbd442-0a47-454e-8fa7-c04050828c1a', title: '晨读 · 10月19日', generated_at: '2026-10-18T16:00:00Z', reading_date: '2026-10-19' };
beforeEach(() => {
  vi.resetAllMocks();
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
  vi.mocked(getMorningReadings).mockResolvedValue({ items: [item], next_offset: null });
  vi.mocked(getMorningReading).mockResolvedValue({ ...item, content_text: '有依据的思考 <script>bad()</script>' });
});
afterEach(cleanup);
it('folds timestamped source materials after coverage while preserving their text and coverage gaps', async () => {
  vi.mocked(getMorningReading).mockResolvedValue({ ...item, content_text: '主读｜今日判断\n\n正文与思考\n\ndedao · partial · 221 个订阅未扫描\n\n原文标题\n\n2026-10-23T00:00:00Z\n\n原始正文 <script>bad()</script>' });
  render(<MorningReadingPanel owner={7} day="2026-10-19" />);
  fireEvent.click(await screen.findByRole('button', { name: '开始阅读' }));
  const reader = screen.getByRole('dialog');
  expect(within(reader).getByText('dedao · partial · 221 个订阅未扫描')).toBeVisible();
  const source = within(reader).getByText('原始正文 <script>bad()</script>');
  expect(source).not.toBeVisible();
  const appendix = source.closest('details')!;
  appendix.open = true;
  expect(source).toBeVisible();
  expect(reader.querySelector('script')).toBeNull();
});

it('keeps unstructured text after coverage visible when no material timestamp identifies an appendix', async () => {
  vi.mocked(getMorningReading).mockResolvedValue({ ...item, content_text: 'dedao · partial · 覆盖缺口\n\n这还是需要直接阅读的分析\n\n另一段正文' });
  render(<MorningReadingPanel owner={7} day="2026-10-19" />);
  fireEvent.click(await screen.findByRole('button', { name: '开始阅读' }));
  const reader = screen.getByRole('dialog');
  expect(within(reader).getByText('这还是需要直接阅读的分析')).toBeVisible();
  expect(reader.querySelector('details')).toBeNull();
});

it('tracks the visible chapter and lets the mobile contents close after navigation', async () => {
  vi.mocked(getMorningReading).mockResolvedValue({ ...item, content_text: '主读｜第一章\n\n正文一\n\n深入问题｜第二章完整标题\n\n正文二' });
  render(<MorningReadingPanel owner={7} day="2026-10-19" />);
  fireEvent.click(await screen.findByRole('button', { name: '开始阅读' }));
  const reader = screen.getByRole('dialog');
  const body = within(reader).getByRole('article');
  const headings = within(reader).getAllByRole('heading', { level: 3 });
  Object.defineProperties(body, { scrollHeight: { value: 1200 }, clientHeight: { value: 400 }, scrollTop: { value: 400, writable: true } });
  vi.spyOn(body, 'getBoundingClientRect').mockReturnValue({ top: 0 } as DOMRect);
  vi.spyOn(headings[0], 'getBoundingClientRect').mockReturnValue({ top: -300 } as DOMRect);
  vi.spyOn(headings[1], 'getBoundingClientRect').mockReturnValue({ top: 24 } as DOMRect);
  fireEvent.scroll(body);
  expect(within(reader).getByRole('progressbar', { name: '正文位置' })).toHaveAttribute('aria-valuenow', '50');
  const desktop = within(reader).getByRole('navigation', { name: '本期目录' });
  expect(within(desktop).getByRole('button', { name: /第二章完整标题/ })).toHaveAttribute('aria-current', 'location');
  const details = reader.querySelector('details')!;
  details.open = true;
  const mobile = within(reader).getByRole('navigation', { name: '手机章节目录' });
  const scroll = vi.spyOn(headings[0], 'scrollIntoView');
  fireEvent.click(within(mobile).getByRole('button', { name: /第一章/ }));
  expect(details.open).toBe(false);
  expect(document.activeElement).toBe(headings[0]);
  expect(scroll).toHaveBeenCalledWith({ block: 'start' });
});

it('loads the selected date and renders source text without executing HTML', async () => {
  const view = render(<MorningReadingPanel owner={7} day="2026-10-19" />);
  expect(await screen.findByText('有依据的思考 <script>bad()</script>')).toBeTruthy();
  expect(view.container.querySelector('script')).toBeNull();
  expect(getMorningReading).toHaveBeenCalledWith(7, item.report_id, expect.any(AbortSignal));
  fireEvent.click(screen.getByRole('button', { name: /晨读 · 10月19日/ }));
  expect(screen.getByText('有依据的思考 <script>bad()</script>')).toBeTruthy();
});
it('does not present an older reading as today and allows opening history', async () => {
  render(<MorningReadingPanel owner={7} day="2026-10-21" />);
  expect(await screen.findByText('所选日期暂无晨读。')).toBeTruthy();
  expect(getMorningReading).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: /晨读 · 10月19日/ }));
  expect(await screen.findByText('有依据的思考 <script>bad()</script>')).toBeTruthy();
  expect(screen.getByText('历史晨读 · 2026-10-19')).toBeTruthy();
});
it('discards delayed prior-account content', async () => {
  let complete!: (value: { items: typeof item[]; next_offset: null }) => void;
  vi.mocked(getMorningReadings).mockReturnValueOnce(new Promise(resolve => { complete = resolve; })).mockResolvedValueOnce({ items: [], next_offset: null });
  const view = render(<MorningReadingPanel owner={7} day="2026-10-19" />);
  view.rerender(<MorningReadingPanel owner={8} day="2026-10-19" />);
  await screen.findByText('所选日期暂无晨读。');
  complete({ items: [item], next_offset: null });
  await waitFor(() => expect(getMorningReading).not.toHaveBeenCalled());
  expect(screen.queryByText(item.title)).toBeNull();
});
it('exposes errors and retries rather than claiming no updates', async () => {
  vi.mocked(getMorningReadings).mockRejectedValueOnce(new Error('private secret'));
  render(<MorningReadingPanel owner={7} day="2026-10-19" />);
  expect(await screen.findByRole('alert')).toHaveTextContent('晨读加载失败');
  expect(screen.queryByText('所选日期暂无晨读。')).toBeNull();
  expect(screen.queryByText('private secret')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '刷新晨读' }));
  expect(await screen.findByText('有依据的思考 <script>bad()</script>')).toBeTruthy();
});
it('shows history coverage and lets the user load an additional page', async () => {
  vi.mocked(getMorningReadings).mockResolvedValueOnce({ items: [], next_offset: 30 }).mockResolvedValueOnce({ items: [item], next_offset: null });
  render(<MorningReadingPanel owner={7} day="2026-10-19" />);
  fireEvent.click(await screen.findByRole('button', { name: '加载更早晨读' }));
  expect(await screen.findByText('有依据的思考 <script>bad()</script>')).toBeTruthy();
});

it('keeps a long reading out of the week layout until explicitly opened', async () => {
  const content = '开头摘要。'.repeat(50) + '\n\n正文结尾';
  vi.mocked(getMorningReading).mockResolvedValue({ ...item, content_text: content });
  const show = vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function () { this.open = true; });
  const view = render(<MorningReadingPanel owner={7} day="2026-10-19" />);
  const open = await screen.findByRole('button', { name: '开始阅读' });
  expect(screen.queryByText(/正文结尾/)).toBeNull();
  expect(view.container.querySelector('iframe')).toBeNull();
  fireEvent.click(open);
  const reader = screen.getByRole('dialog', { name: item.title });
  expect(within(reader).getByText('正文结尾')).toBeTruthy();
  fireEvent.click(within(reader).getByRole('button', { name: '关闭阅读' }));
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(show).toHaveBeenCalledTimes(1);
  show.mockRestore();
});

it('closes with Escape and removes private reading on account change', async () => {
  const view = render(<MorningReadingPanel owner={7} day="2026-10-19" />);
  const open = await screen.findByRole('button', { name: '开始阅读' });
  open.focus();
  fireEvent.click(open);
  expect(document.body.style.overflow).toBe('hidden');
  fireEvent(screen.getByRole('dialog'), new Event('cancel', { cancelable: true }));
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(document.body.style.overflow).toBe('');
  expect(document.activeElement).toBe(open);
  fireEvent.click(open);
  vi.mocked(getMorningReadings).mockResolvedValue({ items: [], next_offset: null });
  view.rerender(<MorningReadingPanel owner={8} day="2026-10-19" />);
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(document.body.style.overflow).toBe('');
  await screen.findByText('所选日期暂无晨读。');
});

it('gives known reading sections hierarchy while keeping source text literal', async () => {
  vi.mocked(getMorningReading).mockResolvedValue({ ...item, content_text: '速览\n第一条观点\n\n深入解读\n<script>bad()</script>\n\n普通段落保持原样' });
  render(<MorningReadingPanel owner={7} day="2026-10-19" />);
  fireEvent.click(await screen.findByRole('button', { name: '开始阅读' }));
  const reader = screen.getByRole('dialog');
  expect(within(reader).getByRole('heading', { name: '速览' })).toBeTruthy();
  expect(within(reader).getByText('第一条观点')).toBeTruthy();
  expect(within(reader).getByText('<script>bad()</script>')).toBeTruthy();
  expect(within(reader).getByText('普通段落保持原样')).toBeTruthy();
  expect(reader.querySelector('script')).toBeNull();
});

it('renders delivered main readings, evidence labels and a compact contents list', async () => {
  const content = `${item.title}\n\n资料日期：2026-10-12 — 2026-10-18\n\n含摘要与思考\n\n主读 · 昨日得到上架｜本地 AI 的回本账，先核对分母\n\n【来源与时间】完整来源说明。\n\n【作者主张与依据】作者的论证，不等于事实核验。\n\n【本次复算】50 亿 ÷ 50 ÷ 3600 ÷ 1095。\n\n深入问题｜如何验证结果？\n\n【本次推论】<img src=x onerror=alert(1)>\n\n未识别的原始段落也要保留。`;
  vi.mocked(getMorningReading).mockResolvedValue({ ...item, content_text: content });
  render(<MorningReadingPanel owner={7} day="2026-10-19" />);
  fireEvent.click(await screen.findByRole('button', { name: '开始阅读' }));
  const reader = screen.getByRole('dialog');
  expect(within(reader).getByRole('heading', { name: '本地 AI 的回本账，先核对分母' })).toBeTruthy();
  expect(within(reader).getByRole('heading', { name: '作者主张与依据' })).toBeTruthy();
  expect(within(reader).getByRole('heading', { name: '本次复算' })).toBeTruthy();
  expect(within(reader).getByRole('navigation', { name: '本期目录' })).toBeTruthy();
  expect(within(reader).getByText('完整来源说明。')).toBeTruthy();
  expect(within(reader).getByText('未识别的原始段落也要保留。')).toBeTruthy();
  expect(within(reader).getByText('<img src=x onerror=alert(1)>')).toBeTruthy();
  expect(reader.querySelector('img')).toBeNull();
  expect(within(reader).getAllByRole('heading', { name: item.title })).toHaveLength(1);
});
