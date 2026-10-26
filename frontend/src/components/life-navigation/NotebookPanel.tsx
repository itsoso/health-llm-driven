'use client';
import { useRef, useState } from 'react';
import { FileText, Plus, Search, Trash2 } from 'lucide-react';
import type { NotebookEntry } from '@/services/lifeNavigation';
import { newId } from './model';
import css from './notebook.module.css';

export default function NotebookPanel({ notes, onChange }: { notes: NotebookEntry[]; onChange: (notes: NotebookEntry[]) => void }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const titleRef = useRef<HTMLInputElement>(null);
  const matching = notes.filter(note => `${note.title}\n${note.body}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  const current = matching.find(note => note.id === selected) ?? matching[0];
  const update = (patch: Partial<Pick<NotebookEntry, 'title' | 'body'>>) => {
    if (current) onChange(notes.map(note => note.id === current.id ? { ...note, ...patch } : note));
  };
  const add = () => {
    if (notes.length >= 100) return;
    const id = newId(); onChange([{ id, title: '', body: '' }, ...notes]); setSelected(id); setQuery('');
    requestAnimationFrame(() => titleRef.current?.focus());
  };
  return <section aria-label="私人记事本" className={css.notebook}>
    <div className={css.intro}><div><h2>随手记，慢慢整理</h2><p>灵感、备忘和阅读摘记，都放在这里。编辑后点击上方“保存工作区”。</p></div><span>仅自己可见 · 跨周保留</span></div>
    <div className={css.layout}>
      <aside className={css.list} aria-label="笔记列表">
        <button type="button" className={css.add} disabled={notes.length >= 100} onClick={add}><Plus size={18} aria-hidden="true"/>新建笔记</button>
        <label className={css.search}><Search size={17} aria-hidden="true"/><input aria-label="搜索笔记" placeholder="搜索标题或正文" value={query} onChange={e => setQuery(e.target.value)}/></label>
        <p className={css.count}>{notes.length} / 100 条笔记</p>
        {matching.map(note => <button key={note.id} type="button" aria-pressed={current?.id === note.id} className={`${css.item} ${current?.id === note.id ? css.selected : ''}`} onClick={() => setSelected(note.id)}><strong>{note.title.trim() || '无标题笔记'}</strong><span>{note.body.trim().slice(0, 80) || '写下第一句话…'}</span></button>)}
        {!matching.length && query.trim() ? <p className={css.empty}>没有匹配的笔记</p> : null}
      </aside>
      {current ? <div className={css.editor}>
        <div className={css.editorTop}><span><FileText size={16} aria-hidden="true"/>纯文本笔记</span><button type="button" className={css.remove} aria-label="删除笔记" onClick={() => { if (window.confirm('删除这条笔记？保存前可通过“撤销”恢复。')) onChange(notes.filter(note => note.id !== current.id)); }}><Trash2 size={17} aria-hidden="true"/>删除</button></div>
        <input ref={titleRef} className={css.title} aria-label="笔记标题" placeholder="无标题笔记" maxLength={200} value={current.title} onChange={e => update({ title: e.target.value })}/>
        <textarea className={css.body} aria-label="笔记正文" placeholder="从一个想法开始…" maxLength={20000} value={current.body} onChange={e => update({ body: e.target.value })}/>
        <div className={css.editorFooter}><span>不会自动加入健康记录或发送给 AI</span><span>{current.body.length} / 20000 字符</span></div>
      </div> : <div className={css.welcome}><FileText size={36} aria-hidden="true"/><h3>{notes.length ? '换个关键词试试' : '给想法一个落脚处'}</h3><p>{notes.length ? '搜索笔记标题或正文。' : '新建第一条笔记，记录此刻想记住的事。'}</p></div>}
    </div>
  </section>;
}
