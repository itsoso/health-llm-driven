'use client';
import { ArrowUpRight, ArrowRight, BookOpen, ChevronDown, RefreshCw, X } from 'lucide-react';
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { getMorningReading, getMorningReadings, type MorningReadingItem, type MorningReadingDetail } from '@/services/morningReadings';
import css from './workspace.module.css';

export default function MorningReadingPanel({ owner, day }: { owner: number; day: string }) {
  return <ReadingSession key={`${owner}:${day}`} owner={owner} day={day} />;
}

function ReadingSession({ owner, day }: { owner: number; day: string }) {
  const [reading, setReading] = useState(false);
  const [items, setItems] = useState<MorningReadingItem[]>([]);
  const [offset, setOffset] = useState(0);
  const [next, setNext] = useState<number | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const selectedRef = useRef<string | null>(null);
  const [report, setReport] = useState<MorningReadingDetail | null>(null);
  const [detailError, setDetailError] = useState(false);
  const [detailRefresh, setDetailRefresh] = useState(0);
  const choose = (id: string) => {
    if (selectedRef.current === id) return;
    setReading(false);
    selectedRef.current = id; setReport(null); setSelected(id);
  };

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setListError(false);
    getMorningReadings(owner, offset, controller.signal).then(result => {
      if (controller.signal.aborted) return;
      setItems(old => [...new Map([...(offset ? old : []), ...result.items].map(item => [item.report_id, item])).values()]);
      setNext(result.next_offset);
      const match = result.items.find(item => item.reading_date === day);
      if (match && !selectedRef.current) choose(match.report_id);
    }).catch(() => { if (!controller.signal.aborted) setListError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [owner, day, offset, refresh]);

  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    setReport(null); setDetailError(false);
    getMorningReading(owner, selected, controller.signal).then(value => {
      if (!controller.signal.aborted) setReport(value);
    }).catch(() => { if (!controller.signal.aborted) setDetailError(true); });
    return () => controller.abort();
  }, [owner, selected, detailRefresh]);

  return <section className={`${css.card} ${css.morningCard}`} aria-label="晨读" id="life-morning-reading">
    <div className={css.morningMasthead}><h2><BookOpen size={16} aria-hidden="true" /> 晨读 <span>给思考留一点时间</span></h2>
      <button type="button" className={css.button} aria-label="刷新晨读" disabled={loading} onClick={() => {
        setOffset(0); setRefresh(v => v + 1); setDetailRefresh(v => v + 1);
      }}><RefreshCw size={14} aria-hidden="true" /> 刷新</button></div>
    {loading ? <p role="status" className={css.muted}>正在读取晨读…</p> : null}
    {listError ? <p role="alert">晨读加载失败，请刷新重试。</p> : null}
    {!loading && !listError && !items.some(item => item.reading_date === day) ? <p className={css.muted}>{next !== null ? '已加载记录中未找到所选日期的晨读。' : '所选日期暂无晨读。'}</p> : null}
    {selected && !report && !detailError ? <p role="status" className={css.muted}>正在读取正文…</p> : null}
    {detailError ? <div role="alert">正文读取失败。<button type="button" className={css.button} onClick={() => setDetailRefresh(v => v + 1)}>重试正文</button></div> : null}
    {report ? <article className={css.morningFeature}>
      <div className={css.morningDate} aria-hidden="true"><span>{report.reading_date.slice(0, 7).replace('-', ' / ')}</span><strong>{report.reading_date.slice(8)}</strong><span>晨间阅读</span></div>
      <div className={css.morningCopy}><p className={css.readingEyebrow}>MORNING JOURNAL · {report.reading_date}</p><h3>{report.title}</h3>
      {report.reading_date !== day ? <p className={css.muted}>历史晨读 · {report.reading_date}</p> : null}
      <p className={css.morningPreview}>{report.content_text.slice(0, 180)}{report.content_text.length > 180 ? '…' : ''}</p>
      <div className={css.readingActions}><button type="button" className={css.readingStart} onClick={() => setReading(true)}>开始阅读 <ArrowRight size={16} aria-hidden="true" /></button>
      {reading ? <MorningReader report={report} onClose={() => setReading(false)} /> : null}
      <a href={`https://base.executor.life/external-reports/${encodeURIComponent(report.report_id)}`} target="_blank" rel="noopener noreferrer" className={css.readingSource}>查看原版 <ArrowUpRight size={14} aria-hidden="true" /></a></div></div>
    </article> : null}
    {items.length ? <details className={css.morningHistory}><summary>晨读历史 · {items.length} 份</summary>
      <div className={css.stack}>{items.map(item => <button type="button" className={css.button} key={item.report_id} aria-pressed={selected === item.report_id}
        onClick={() => choose(item.report_id)}>{item.reading_date} · {item.title}</button>)}</div></details> : null}
    {next !== null ? <button type="button" className={css.button} disabled={loading} onClick={() => setOffset(next)}>加载更早晨读</button> : null}
  </section>;
}

type ReadingBlock = { kind: 'heading' | 'label' | 'meta' | 'paragraph'; title: string; body: string; kicker?: string };

function readingBlocks(text: string, title: string): ReadingBlock[] {
  return text.split(/\n\s*\n/).filter(part => part.trim()).flatMap<ReadingBlock>(part => {
    const value = part.trim();
    if (value === title) return [];
    const [first, ...rest] = value.split('\n');
    if (/^(资料日期[：:]|含摘要与思考$|摘要简版$|材料简版$)/.test(first)) {
      return [{ kind: 'meta', title: '', body: value }];
    }
    if (/^(主读|速览|深入解读|深入问题|综合思考|昨日更新|昨日上架|昨日讨论|昨日播客上架|昨日讨论与七日背景)(?:$|[\s｜|·：:])/.test(first) && first.length <= 120) {
      const separator = first.search(/[｜|]/);
      return [{ kind: 'heading', title: separator >= 0 ? first.slice(separator + 1).trim() : first,
        kicker: separator >= 0 ? first.slice(0, separator).trim() : undefined, body: rest.join('\n') }];
    }
    const label = value.match(/^【([^【】\n]{1,40})】\s*([\s\S]*)$/);
    if (label) return [{ kind: 'label', title: label[1], body: label[2] }];
    return [{ kind: 'paragraph', title: '', body: value }];
  });
}

function MorningReader({ report, onClose }: { report: MorningReadingDetail; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const body = useRef<HTMLElement>(null);
  const mobileContents = useRef<HTMLDetailsElement>(null);
  const titleId = useId();
  const [position, setPosition] = useState(0);
  const [activeSection, setActiveSection] = useState<string | null>(null);
  const { blocks, appendix } = useMemo(() => {
    const allBlocks = readingBlocks(report.content_text, report.title);
    const appendixStart = allBlocks.findIndex((block, index) => index > 0 && block.kind === 'paragraph'
      && /^(?:dedao|xiaoyuzhou|wechat) · (?:partial|available|unavailable|failed) · /.test(allBlocks[index - 1].body)
      && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(allBlocks[index + 1]?.body ?? ''));
    return { blocks: appendixStart < 0 ? allBlocks : allBlocks.slice(0, appendixStart),
      appendix: appendixStart < 0 ? [] : allBlocks.slice(appendixStart) };
  }, [report.content_text, report.title]);
  const appendixParagraphs = useMemo(() => appendix.map((block, index) => <p key={index}>{[block.kicker, block.title, block.body].filter(Boolean).join('\n')}</p>), [appendix]);
  const contents = blocks.flatMap((block, index) => block.kind === 'heading' ? [{ ...block, index }] : []);
  const updatePosition = useCallback(() => {
    const element = body.current;
    if (!element) return;
    const range = element.scrollHeight - element.clientHeight;
    setPosition(range > 0 ? Math.round(Math.max(0, Math.min(1, element.scrollTop / range)) * 100) : 0);
    const headings = Array.from(element.querySelectorAll<HTMLHeadingElement>('h3[id]'));
    const threshold = element.getBoundingClientRect().top + 60;
    const visible = headings.filter(heading => heading.getBoundingClientRect().top <= threshold);
    const current = range > 0 && element.scrollTop >= range - 2 ? headings.at(-1) : visible.at(-1) ?? headings[0];
    setActiveSection(current?.id ?? null);
  }, []);
  const jumpTo = (index: number) => {
    if (mobileContents.current) mobileContents.current.open = false;
    const heading = document.getElementById(`${titleId}-section-${index}`);
    heading?.scrollIntoView({ block: 'start' });
    heading?.focus({ preventScroll: true });
    updatePosition();
  };
  useEffect(() => {
    const element = dialog.current!;
    const trigger = document.activeElement;
    const overflow = document.body.style.overflow;
    element.showModal();
    document.body.style.overflow = 'hidden';
    updatePosition();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(updatePosition);
    if (body.current) observer?.observe(body.current);
    return () => {
      observer?.disconnect();
      element.close();
      document.body.style.overflow = overflow;
      if (trigger instanceof HTMLElement && trigger.isConnected) trigger.focus();
    };
  }, [updatePosition]);
  const activeIndex = Math.max(0, contents.findIndex(block => `${titleId}-section-${block.index}` === activeSection));
  const contentsButtons = contents.map((block, index) => <button type="button" key={block.index}
    aria-current={`${titleId}-section-${block.index}` === activeSection ? 'location' : undefined}
    onClick={() => jumpTo(block.index)}>
    <span>{String(index + 1).padStart(2, '0')}</span><span>{block.title}</span>
  </button>);
  return <dialog ref={dialog} className={css.morningReader} aria-labelledby={titleId}
    onCancel={event => { event.preventDefault(); onClose(); }}>
    <header className={css.readerHeader}>
      <span className={css.readerBrand}><BookOpen size={17} aria-hidden="true" /> 晨读 <span>{report.reading_date.replaceAll('-', '.')}</span></span>
      <div className={css.readerTools}><a href={`https://base.executor.life/external-reports/${encodeURIComponent(report.report_id)}`} target="_blank" rel="noopener noreferrer">原版 <ArrowUpRight size={13} aria-hidden="true" /></a>
      <button type="button" className={css.readerClose} aria-label="关闭阅读" onClick={onClose}><X size={19} aria-hidden="true" /></button></div>
    </header>
    <div className={css.readerProgress} role="progressbar" aria-label="正文位置" aria-valuemin={0} aria-valuemax={100} aria-valuenow={position}>
      <span style={{ width: `${position}%` }} />
    </div>
    <div className={`${css.readerLayout} ${contents.length ? '' : css.readerWithoutContents}`}>
      {contents.length ? <aside className={css.readerSidebar}>
        <p className={css.readerContentsLabel}>本期目录 <span>{String(contents.length).padStart(2, '0')}</span></p>
        <nav className={css.readerDesktopContents} aria-label="本期目录">{contentsButtons}</nav>
        <details ref={mobileContents} className={css.readerMobileContents}>
          <summary><span>本期目录</span><span>{String(activeIndex + 1).padStart(2, '0')} / {String(contents.length).padStart(2, '0')} <ChevronDown size={14} aria-hidden="true" /></span></summary>
          <nav aria-label="手机章节目录">{contentsButtons}</nav>
        </details>
        <p className={css.readerSideNote}>观点与依据，分开阅读。</p>
      </aside> : null}
      <article ref={body} className={css.readerBody} onScroll={updatePosition}>
        <div className={css.readerTitle}><p className={css.readingEyebrow}>MORNING JOURNAL</p><h2 id={titleId}>{report.title}</h2></div>
        {blocks.map((block, index) => {
          if (block.kind === 'heading') return <section className={css.readerSection} key={index}>
            {block.kicker ? <p className={css.readerKicker}>{block.kicker}</p> : null}
            <h3 id={`${titleId}-section-${index}`} tabIndex={-1}>{block.title}</h3>{block.body ? <p>{block.body}</p> : null}
          </section>;
          if (block.kind === 'label') return <section key={index} className={`${css.readerBlock} ${/复算|验证方式|验证方法/.test(block.title) ? css.readerEvidence : ''} ${/来源与时间/.test(block.title) ? css.readerSourceNote : ''}`}>
            <h4>{block.title}</h4><p>{block.body}</p>
          </section>;
          return <p className={block.kind === 'meta' ? css.readerMeta : undefined} key={index}>{block.body}</p>;
        })}
        {appendix.length ? <details className={css.readerAppendix} onToggle={updatePosition}>
          <summary>查看原始材料 <span>按需展开</span></summary>
          <div>{appendixParagraphs}</div>
        </details> : null}
        <a href={`https://base.executor.life/external-reports/${encodeURIComponent(report.report_id)}`} target="_blank" rel="noopener noreferrer">在 Proofroom 查看原版 ↗</a>
      </article>
    </div>
  </dialog>;
}
