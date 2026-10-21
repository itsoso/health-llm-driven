'use client';
import { useEffect, useRef, useState } from 'react';
import { getMorningReading, getMorningReadings, type MorningReadingItem, type MorningReadingDetail } from '@/services/morningReadings';
import css from './workspace.module.css';

export default function MorningReadingPanel({ owner, day }: { owner: number; day: string }) {
  return <ReadingSession key={`${owner}:${day}`} owner={owner} day={day} />;
}

function ReadingSession({ owner, day }: { owner: number; day: string }) {
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

  return <section className={css.card} aria-label="晨读" id="life-morning-reading">
    <div className={css.sectionHeading}><h2>晨读 <span className={css.muted}>{day}</span></h2>
      <button type="button" className={css.button} aria-label="刷新晨读" disabled={loading} onClick={() => {
        setOffset(0); setRefresh(v => v + 1); setDetailRefresh(v => v + 1);
      }}>刷新</button></div>
    {loading ? <p role="status" className={css.muted}>正在读取晨读…</p> : null}
    {listError ? <p role="alert">晨读加载失败，请刷新重试。</p> : null}
    {!loading && !listError && !items.some(item => item.reading_date === day) ? <p className={css.muted}>{next !== null ? '已加载记录中未找到所选日期的晨读。' : '所选日期暂无晨读。'}</p> : null}
    {next !== null ? <p className={css.muted}>已读取部分历史，可继续加载更早的晨读。</p> : null}
    {selected && !report && !detailError ? <p role="status" className={css.muted}>正在读取正文…</p> : null}
    {detailError ? <div role="alert">正文读取失败。<button type="button" className={css.button} onClick={() => setDetailRefresh(v => v + 1)}>重试正文</button></div> : null}
    {report ? <article>
      <h3>{report.title}</h3>
      {report.reading_date !== day ? <p className={css.muted}>历史晨读 · {report.reading_date}</p> : null}
      <details open><summary>阅读全文</summary><div className={css.morningText}>{report.content_text}</div></details>
      <a href={`https://base.executor.life/external-reports/${encodeURIComponent(report.report_id)}`} target="_blank" rel="noopener noreferrer" className={css.muted}>在 Proofroom 查看原版 ↗</a>
    </article> : null}
    {items.length ? <details className={css.morningHistory}><summary>晨读历史 · {items.length} 份</summary>
      <div className={css.stack}>{items.map(item => <button type="button" className={css.button} key={item.report_id} aria-pressed={selected === item.report_id}
        onClick={() => choose(item.report_id)}>{item.reading_date} · {item.title}</button>)}</div></details> : null}
    {next !== null ? <button type="button" className={css.button} disabled={loading} onClick={() => setOffset(next)}>加载更早晨读</button> : null}
  </section>;
}
