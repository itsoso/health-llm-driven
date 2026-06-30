/**
 * RevaGreetingHeader —— 首页问候头(Reva 重设计第 1 块)。
 *
 * 一行「早安，{名}」+ 右侧中文日期(如「6 月 16 日 · 周二」)。
 * 纯表现型:名字由调用方传入(拿不到 → 「早安」无名)。
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { revaColors as C, revaFonts, revaSpacing } from '../../constants/revaTheme';

function partOfDay(h: number): string {
  if (h < 6) return '凌晨好';
  if (h < 11) return '早安';
  if (h < 14) return '午安';
  if (h < 18) return '下午好';
  return '晚上好';
}

function chineseDate(now: Date): string {
  const week = ['日', '一', '二', '三', '四', '五', '六'][now.getDay()];
  return `${now.getMonth() + 1} 月 ${now.getDate()} 日 · 周${week}`;
}

export default function RevaGreetingHeader({
  name,
}: {
  name?: string | null;
}) {
  const now = new Date();
  const greet = partOfDay(now.getHours());
  const title = name ? `${greet}，${name}` : greet;
  return (
    <View style={styles.shell}>
      <View style={styles.row}>
        <Text style={styles.greeting} numberOfLines={1}>
          {title}
        </Text>
        <Text style={styles.date}>{chineseDate(now)}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  shell: {
    gap: revaSpacing.s2,
    paddingHorizontal: 2,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    gap: revaSpacing.s3,
  },
  greeting: {
    fontFamily: revaFonts.sans,
    fontWeight: '800',
    fontSize: 24,
    letterSpacing: 0,
    color: C.ink1,
    flex: 1,
    minWidth: 0,
  },
  date: {
    fontFamily: revaFonts.mono,
    fontSize: 12.5,
    letterSpacing: 0,
    color: C.ink3,
  },
});
