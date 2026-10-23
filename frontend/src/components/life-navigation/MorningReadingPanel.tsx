'use client';
import { ArrowUpRight, ArrowRight, BookOpen, RefreshCw, X } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
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

function MorningReader({ report, onClose }: { report: MorningReadingDetail; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const element = dialog.current!;
    const trigger = document.activeElement;
    const overflow = document.body.style.overflow;
    element.showModal();
    document.body.style.overflow = 'hidden';
    return () => {
      element.close();
      document.body.style.overflow = overflow;
      if (trigger instanceof HTMLElement && trigger.isConnected) trigger.focus();
    };
  }, []);
  return <dialog ref={dialog} className={css.morningReader} aria-labelledby={titleId}
    onCancel={event => { event.preventDefault(); onClose(); }}>
    <header className={css.readerHeader}>
      <span className={css.readerBrand}><BookOpen size={17} aria-hidden="true" /> 晨读 <span> / 专注阅读</span></span>
      <button type="button" className={css.readerClose} aria-label="关闭阅读" onClick={onClose}><X size={19} aria-hidden="true" /></button>
    </header>
    <article className={css.readerBody}>
      <div className={css.readerTitle}><p className={css.readingEyebrow}>MORNING JOURNAL · {report.reading_date}</p><h2 id={titleId}>{report.title}</h2><div className={css.readerRule} /></div>
      {report.content_text.split(/\n\s*\n/).filter(part => part.trim()).map((part, index) => {
        const [first, ...rest] = part.trim().split('\n');
        const heading = /^(速览|深入解读|综合思考|昨日更新|昨日上架|昨日讨论)(?:$|[\s｜|·：:])/.test(first) && first.length <= 80;
        return heading ? <section className={css.readerSection} key={index}><h3>{first}</h3>{rest.length ? <p>{rest.join('\n')}</p> : null}</section> : <p key={index}>{part}</p>;
      })}
      <a href={`https://base.executor.life/external-reports/${encodeURIComponent(report.report_id)}`} target="_blank" rel="noopener noreferrer">在 Proofroom 查看原版 ↗</a>
    </article>
  </dialog>;
}
