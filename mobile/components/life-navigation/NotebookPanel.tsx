import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useTheme } from '../../hooks/useTheme';
import type { NotebookEntry } from '../../types/lifeNavigation';
import { newId } from '../../utils/lifeNavigationModel';

interface Props {
    notes: NotebookEntry[];
    disabled: boolean;
    onChange: (notes: NotebookEntry[]) => void;
    onDelete: (id: string) => void;
}

export default function NotebookPanel({ notes, disabled, onChange, onDelete }: Props) {
    const { c } = useTheme();
    const [selected, setSelected] = useState<string | null>(null);
    const [query, setQuery] = useState('');
    const current = notes.find(note => note.id === selected);
    const matching = notes.filter(note => `${note.title}\n${note.body}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
    const button = (label: string, action: () => void, blocked = false) => (
        <Pressable accessibilityRole="button" accessibilityLabel={label}
            accessibilityState={{ disabled: disabled || blocked }} disabled={disabled || blocked}
            onPress={action} style={[styles.button, { borderColor: c.separator, opacity: disabled || blocked ? 0.5 : 1 }]}>
            <Text style={{ color: c.brand }}>{label}</Text>
        </Pressable>
    );
    const update = (patch: Partial<Pick<NotebookEntry, 'title' | 'body'>>) => {
        if (!disabled && current) onChange(notes.map(note => note.id === current.id ? { ...note, ...patch } : note));
    };
    const add = () => {
        if (disabled || notes.length >= 100) return;
        const id = newId();
        onChange([{ id, title: '', body: '' }, ...notes]);
        setSelected(id);
        setQuery('');
    };
    const inputStyle = [styles.input, { color: c.labelPrimary, borderColor: c.separator, backgroundColor: c.bgCard }];
    return <View style={styles.panel}>
        <Text style={{ color: c.labelSecondary }}>仅自己可见 · 跨周保留。编辑后点击上方“保存”。</Text>
        {current ? <>
            <View style={styles.actions}>
                {button('返回笔记列表', () => setSelected(null))}
                {button('删除笔记', () => onDelete(current.id))}
            </View>
            <TextInput accessibilityLabel="笔记标题" placeholder="无标题笔记" placeholderTextColor={c.labelSecondary}
                value={current.title} onChangeText={title => update({ title })} maxLength={200} editable={!disabled}
                style={[inputStyle, styles.title]} />
            <TextInput accessibilityLabel="笔记正文" placeholder="从一个想法开始…" placeholderTextColor={c.labelSecondary}
                value={current.body} onChangeText={body => update({ body })} maxLength={20000} editable={!disabled}
                multiline textAlignVertical="top" scrollEnabled={false} style={[inputStyle, styles.body]} />
            <Text style={{ color: c.labelSecondary }}>{current.body.length} / 20000 字符</Text>
            <Text style={{ color: c.labelSecondary }}>不会自动加入健康记录或发送给 AI</Text>
        </> : <>
            <View style={styles.actions}>
                {button('新建笔记', add, notes.length >= 100)}
                <Text style={{ color: c.labelSecondary }}>{notes.length} / 100 条笔记</Text>
            </View>
            <TextInput accessibilityLabel="搜索笔记" placeholder="搜索标题或正文" placeholderTextColor={c.labelSecondary}
                value={query} onChangeText={setQuery} editable={!disabled} style={inputStyle} />
            {matching.map(note => <Pressable key={note.id} accessibilityRole="button"
                accessibilityLabel={`打开笔记 ${note.title.trim() || '无标题笔记'}`} disabled={disabled}
                onPress={() => setSelected(note.id)} style={[styles.note, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
                <Text numberOfLines={2} style={[styles.noteTitle, { color: c.labelPrimary }]}>{note.title.trim() || '无标题笔记'}</Text>
                <Text numberOfLines={2} style={{ color: c.labelSecondary }}>{note.body.trim().slice(0, 80) || '写下第一句话…'}</Text>
            </Pressable>)}
            {!matching.length && <Text style={{ color: c.labelSecondary }}>{query.trim() ? '没有匹配的笔记' : '还没有笔记'}</Text>}
        </>}
    </View>;
}

const styles = StyleSheet.create({
    panel: { gap: 12 },
    actions: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 12 },
    button: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 12, borderWidth: 1, borderRadius: 8 },
    input: { minHeight: 44, padding: 12, borderWidth: 1, borderRadius: 10, fontSize: 16, lineHeight: 24 },
    title: { fontWeight: '600' },
    body: { minHeight: 240 },
    note: { minHeight: 64, padding: 12, gap: 6, borderWidth: 1, borderRadius: 10 },
    noteTitle: { fontSize: 16, fontWeight: '600' },
});
