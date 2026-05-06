import { Link, Stack } from 'expo-router';
import { View, Text, StyleSheet } from 'react-native';
import { useMemo } from 'react';
import { useTheme, type ColorPalette } from '../hooks/useTheme';

export default function NotFoundScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  return (
    <>
      <Stack.Screen options={{ title: '页面不存在' }} />
      <View style={styles.container}>
        <Text style={styles.title}>页面不存在</Text>
        <Link href="/" style={styles.link}>
          <Text style={styles.linkText}>返回首页</Text>
        </Link>
      </View>
    </>
  );
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 20,
    backgroundColor: c.bgPrimary,
  },
  title: {
    fontSize: 20,
    fontWeight: 'bold',
    color: c.labelPrimary,
  },
  link: {
    marginTop: 15,
    paddingVertical: 15,
  },
  linkText: {
    fontSize: 14,
    color: c.brand,
  },
});
