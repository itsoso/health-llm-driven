import React, { useState } from 'react';
import { Pressable, Text, TextInput, View } from 'react-native';
import { addDays, localDate } from '../../utils/lifeNavigationModel';
import { useLifeControls } from './Controls';

type Props = { date: string; onDate: (date: string) => void; weekly?: boolean; disabled?: boolean; status?: string; trailing?: React.ReactNode; today?: string };
export default function DateNavigation({ date, onDate, weekly = false, disabled = false, status, trailing, today = localDate() }: Props) {
    const { c, button } = useLifeControls(disabled);
    const [editing, setEditing] = useState(false);
    const [input, setInput] = useState(date);
    const [error, setError] = useState('');
    function open() { setInput(date); setError(''); setEditing(true); }
    function select() {
        if (!/^[1-9]\d{3}-\d{2}-\d{2}$/.test(input) || !Number.isFinite(Date.parse(input)) || new Date(input).toISOString().slice(0, 10) !== input) {
            setError('请填写有效日期 YYYY-MM-DD。');
            return;
        }
        onDate(input);
        setEditing(false);
        setError('');
    }
    return <View style={{ gap: 4 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            {!weekly && <Pressable accessibilityRole="button" accessibilityLabel="前一天" disabled={disabled} onPress={()=>onDate(addDays(date,-1))} style={{minWidth:44,minHeight:44,justifyContent:'center',alignItems:'center',opacity:disabled ? .5 : 1}}><Text style={{fontSize:20,color:c.brand}}>‹</Text></Pressable>}
            <Pressable accessibilityRole="button" accessibilityLabel={editing?'取消选择日期':'选择日期'} accessibilityValue={{text:date}} accessibilityHint={status} accessibilityState={{expanded:editing,disabled}} disabled={disabled} onPress={editing?()=>setEditing(false):open}
                style={{flex:1,minHeight:44,flexDirection:'row',justifyContent:'center',alignItems:'center',gap:8,borderWidth:1,borderColor:c.separator,borderRadius:8,opacity:disabled ? .5 : 1}}>
                <View style={{alignItems:'center'}}><Text style={{fontSize:13,lineHeight:18,color:c.labelPrimary,fontVariant:['tabular-nums']}}>{date}</Text>{status&&<Text style={{fontSize:11,lineHeight:14,color:c.labelSecondary}}>{status}</Text>}</View><Text style={{fontSize:12,color:c.brand}}>{editing?'▴':'▾'}</Text>
            </Pressable>
            {!weekly && <Pressable accessibilityRole="button" accessibilityLabel="后一天" disabled={disabled} onPress={()=>onDate(addDays(date,1))} style={{minWidth:44,minHeight:44,justifyContent:'center',alignItems:'center',opacity:disabled ? .5 : 1}}><Text style={{fontSize:20,color:c.brand}}>›</Text></Pressable>}
            {!weekly && date !== today && <Pressable accessibilityRole="button" accessibilityLabel="回到今天" disabled={disabled} onPress={()=>{onDate(today);setEditing(false);setError('');}} style={{minWidth:44,minHeight:44,justifyContent:'center',alignItems:'center',opacity:disabled?0.5:1}}><Text style={{fontSize:12,lineHeight:16,color:c.brand}}>今天</Text></Pressable>}
            {trailing}
        </View>
        {editing && <View style={{ gap: 4 }}>
            <Text style={{ fontSize: 12, lineHeight: 16, color: c.labelSecondary }}>输入日期，例如 2026-10-14</Text>
            <TextInput accessibilityLabel="查看日期 YYYY-MM-DD" value={input} onChangeText={value => { setInput(value); setError(''); }}
                editable={!disabled} maxLength={10} autoCorrect={false} autoCapitalize="none" returnKeyType="done"
                onSubmitEditing={() => { if (!disabled) select(); }}
                style={{ fontSize: 13, lineHeight: 18, color: c.labelPrimary, padding: 8, minHeight: 44, borderWidth: 1, borderColor: c.separator, borderRadius: 10 }} />
            {error ? <Text accessibilityRole="alert" style={{ fontSize: 13, lineHeight: 18, color: c.labelPrimary }}>{error}</Text> : null}
            {button('查看该日期', select)}
        </View>}
    </View>;
}
