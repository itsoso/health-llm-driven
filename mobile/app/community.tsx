import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  deleteCommunityPost,
  getCommunityPostForDietRecord,
  listCommunityPosts,
  publishDietRecordToCommunity,
  removeCommunityReaction,
  reportCommunityPost,
  setCommunityReaction,
  type CommunityPost,
  type CommunityReaction,
} from '../services/community';
import {
  revaColors,
  revaFonts,
  revaRadii,
  revaSemantic,
  revaShadows,
  revaSpacing,
  revaType,
} from '../constants/revaTheme';

const REACTIONS: {
  key: CommunityReaction;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
}[] = [
  { key: 'support', label: '支持', icon: 'heart-outline' },
  { key: 'same_path', label: '同行', icon: 'walk-outline' },
  { key: 'learned', label: '有启发', icon: 'bulb-outline' },
];

const MEAL_LABELS: Record<string, string> = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  snack: '加餐',
};

function replacePost(items: CommunityPost[], next: CommunityPost): CommunityPost[] {
  return items.map((item) => (item.id === next.id ? next : item));
}

function optimisticReaction(
  post: CommunityPost,
  reaction: CommunityReaction,
): CommunityPost {
  const reactionCounts = { ...post.reaction_counts };
  const previous = post.my_reaction;

  if (previous) {
    reactionCounts[previous] = Math.max(0, (reactionCounts[previous] || 0) - 1);
  }
  if (previous === reaction) {
    return { ...post, my_reaction: null, reaction_counts: reactionCounts };
  }

  reactionCounts[reaction] = (reactionCounts[reaction] || 0) + 1;
  return { ...post, my_reaction: reaction, reaction_counts: reactionCounts };
}

function displayDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed);
}

function NutritionSummary({ post }: { post: CommunityPost }) {
  const metrics = [
    post.snapshot.calories == null ? null : `${post.snapshot.calories} kcal`,
    post.snapshot.protein == null ? null : `蛋白质 ${post.snapshot.protein}g`,
    post.snapshot.fiber == null ? null : `膳食纤维 ${post.snapshot.fiber}g`,
  ].filter(Boolean);

  if (metrics.length === 0) return null;

  return (
    <Text style={styles.nutrition} numberOfLines={2}>
      {metrics.join(' · ')}
    </Text>
  );
}

function PeerPost({
  post,
  busyReaction,
  onReaction,
  onDelete,
  onReport,
}: {
  post: CommunityPost;
  busyReaction: string | null;
  onReaction: (post: CommunityPost, reaction: CommunityReaction) => void;
  onDelete: (post: CommunityPost) => void;
  onReport: (post: CommunityPost) => void;
}) {
  return (
    <View style={styles.post}>
      <View style={styles.postHeader}>
        <View style={styles.avatar}>
          <Ionicons name="leaf-outline" size={17} color={revaColors.green600} />
        </View>
        <View style={styles.authorCopy}>
          <Text style={styles.author}>{post.anonymous_name}</Text>
          <Text style={styles.meta}>
            {MEAL_LABELS[post.snapshot.meal_type] || '饮食记录'} · {displayDate(post.created_at)}
          </Text>
        </View>
        <TouchableOpacity
          onPress={() => (post.is_owner ? onDelete(post) : onReport(post))}
          accessibilityLabel={post.is_owner ? '删除这条分享' : '举报这条分享'}
          hitSlop={10}
          style={styles.iconButton}
        >
          <Ionicons
            name={post.is_owner ? 'trash-outline' : 'ellipsis-horizontal'}
            size={18}
            color={revaColors.ink3}
          />
        </TouchableOpacity>
      </View>

      <Text style={styles.food}>{post.snapshot.food_items}</Text>
      <NutritionSummary post={post} />
      {post.caption ? <Text style={styles.caption}>{post.caption}</Text> : null}

      <View style={styles.reactions}>
        {REACTIONS.map(({ key, label, icon }) => {
          const selected = post.my_reaction === key;
          const count = post.reaction_counts[key] || 0;
          const isBusy = busyReaction === `${post.id}:${key}`;
          return (
            <TouchableOpacity
              key={key}
              onPress={() => onReaction(post, key)}
              disabled={isBusy}
              accessibilityRole="button"
              accessibilityState={{ selected, disabled: isBusy }}
              accessibilityLabel={`${label} ${count}`}
              style={[
                styles.reaction,
                selected && styles.reactionSelected,
                isBusy && styles.reactionPending,
              ]}
            >
              <Ionicons
                name={selected && key === 'support' ? 'heart' : icon}
                size={17}
                color={selected ? revaColors.green600 : revaColors.ink2}
              />
              <Text style={[styles.reactionText, selected && styles.reactionTextSelected]}>
                {label}{count > 0 ? ` ${count}` : ''}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

export default function CommunityScreen() {
  const router = useRouter();
  const { composeRecordId } = useLocalSearchParams<{ composeRecordId?: string }>();
  const recordId = Number(composeRecordId);
  const canCompose = Number.isInteger(recordId) && recordId > 0;
  const idempotencyKey = useRef(
    canCompose ? `community-diet-${recordId}-${Date.now()}` : '',
  );

  const [posts, setPosts] = useState<CommunityPost[]>([]);
  const [caption, setCaption] = useState('');
  const [showComposer, setShowComposer] = useState(false);
  const [existingShare, setExistingShare] = useState<CommunityPost | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);
  const [publishError, setPublishError] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [busyReaction, setBusyReaction] = useState<string | null>(null);

  const loadPosts = useCallback(async (refresh = false) => {
    if (refresh) setIsRefreshing(true);
    else setIsLoading(true);
    setLoadError(false);
    try {
      const [feed, existing] = await Promise.all([
        listCommunityPosts(),
        canCompose
          ? getCommunityPostForDietRecord(recordId)
          : Promise.resolve(null),
      ]);
      setExistingShare(existing);
      setShowComposer(canCompose && !existing);
      setPosts(
        existing?.status === 'active' && !feed.some((item) => item.id === existing.id)
          ? [existing, ...feed]
          : feed,
      );
    } catch {
      setLoadError(true);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [canCompose, recordId]);

  useEffect(() => {
    void loadPosts();
  }, [loadPosts]);

  const publish = useCallback(async () => {
    if (!canCompose || isPublishing) return;
    setIsPublishing(true);
    setPublishError(false);
    try {
      const created = await publishDietRecordToCommunity(
        recordId,
        caption,
        idempotencyKey.current,
      );
      setPosts((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      setExistingShare(created);
      setShowComposer(false);
      setCaption('');
    } catch {
      setPublishError(true);
    } finally {
      setIsPublishing(false);
    }
  }, [canCompose, caption, isPublishing, recordId]);

  const toggleReaction = useCallback(async (
    post: CommunityPost,
    reaction: CommunityReaction,
  ) => {
    const key = `${post.id}:${reaction}`;
    if (busyReaction) return;
    const optimistic = optimisticReaction(post, reaction);
    setPosts((current) => replacePost(current, optimistic));
    setBusyReaction(key);
    try {
      const updated = post.my_reaction === reaction
        ? await removeCommunityReaction(post.id)
        : await setCommunityReaction(post.id, reaction);
      setPosts((current) => replacePost(current, updated));
    } catch {
      setPosts((current) => replacePost(current, post));
      Alert.alert('暂时无法反馈', '网络恢复后再试，饮食记录不受影响。');
    } finally {
      setBusyReaction(null);
    }
  }, [busyReaction]);

  const removePost = useCallback((post: CommunityPost) => {
    Alert.alert('删除分享？', '只会删除同行圈中的匿名分享，私人饮食记录会保留。', [
      { text: '取消', style: 'cancel' },
      {
        text: '删除分享',
        style: 'destructive',
        onPress: async () => {
          try {
            await deleteCommunityPost(post.id);
            setPosts((current) => current.filter((item) => item.id !== post.id));
            if (existingShare?.id === post.id) {
              setExistingShare(null);
              setShowComposer(canCompose);
              idempotencyKey.current = canCompose
                ? `community-diet-${recordId}-${Date.now()}`
                : '';
            }
          } catch {
            Alert.alert('删除失败', '请稍后重试。');
          }
        },
      },
    ]);
  }, [canCompose, existingShare, recordId]);

  const reportPost = useCallback((post: CommunityPost) => {
    Alert.alert('举报这条内容？', '举报仅用于处理不适当内容，不会影响你的健康数据。', [
      { text: '取消', style: 'cancel' },
      {
        text: '举报',
        style: 'destructive',
        onPress: async () => {
          try {
            await reportCommunityPost(post.id, 'inappropriate');
            setPosts((current) => current.filter((item) => item.id !== post.id));
          } catch {
            Alert.alert('提交失败', '请稍后重试。');
          }
        },
      },
    ]);
  }, []);

  const header = useMemo(() => (
    <>
      <View style={styles.intro}>
        <Text style={styles.introTitle}>一起把健康习惯做下去</Text>
        <Text style={styles.introBody}>
          看见真实行动，给彼此一点支持。不比较体重，不做排行榜。
        </Text>
      </View>

      {existingShare && !showComposer ? (
        <View style={styles.publishedNotice}>
          <Ionicons
            name={existingShare.status === 'under_review' ? 'time-outline' : 'checkmark-circle'}
            size={19}
            color={revaColors.green600}
          />
          <Text style={styles.publishedNoticeText}>
            {existingShare.status === 'under_review'
              ? '这条匿名分享正在审核，暂时不能重复发布。'
              : '已经匿名发布，可在下方查看同行反馈。'}
          </Text>
        </View>
      ) : null}

      {showComposer ? (
        <View style={styles.composer}>
          <View style={styles.composerTitleRow}>
            <View style={styles.composerIcon}>
              <Ionicons name="shield-checkmark-outline" size={20} color={revaColors.green600} />
            </View>
            <View style={styles.composerCopy}>
              <Text style={styles.composerTitle}>发布这次饮食记录？</Text>
              <Text style={styles.composerPrivacy}>
                仅分享餐次、食物与营养摘要。照片、体重和健康档案不会公开。
              </Text>
            </View>
          </View>
          <TextInput
            value={caption}
            onChangeText={setCaption}
            maxLength={280}
            multiline
            placeholder="可选：写一句给同行者的话"
            placeholderTextColor={revaColors.ink3}
            style={styles.captionInput}
            accessibilityLabel="分享附言"
          />
          <Text style={styles.captionSafety}>
            请勿填写姓名、病史、用药或联系方式。
          </Text>
          {publishError ? (
            <View style={styles.publishError}>
              <Ionicons name="alert-circle-outline" size={17} color={revaSemantic.risk.fg} />
              <Text style={styles.publishErrorText}>发布失败，饮食记录未受影响。</Text>
            </View>
          ) : null}
          <View style={styles.composerActions}>
            <TouchableOpacity
              onPress={() => setShowComposer(false)}
              disabled={isPublishing}
              style={styles.secondaryButton}
            >
              <Text style={styles.secondaryButtonText}>暂不发布</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => void publish()}
              disabled={isPublishing}
              accessibilityLabel="确认发布到同行圈"
              style={[styles.primaryButton, isPublishing && styles.buttonDisabled]}
            >
              {isPublishing ? (
                <ActivityIndicator size="small" color={revaColors.greenOn} />
              ) : (
                <>
                  <Ionicons
                    name={publishError ? 'refresh-outline' : 'paper-plane-outline'}
                    size={17}
                    color={revaColors.greenOn}
                  />
                  <Text style={styles.primaryButtonText}>
                    {publishError ? '重试发布' : '匿名发布'}
                  </Text>
                </>
              )}
            </TouchableOpacity>
          </View>
        </View>
      ) : null}

      <View style={styles.feedHeading}>
        <Text style={styles.feedTitle}>同行动态</Text>
        <Text style={styles.feedNote}>只看行动，不比输赢</Text>
      </View>
    </>
  ), [caption, existingShare, isPublishing, publish, publishError, showComposer]);

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <TouchableOpacity
          onPress={() => router.back()}
          hitSlop={10}
          accessibilityLabel="返回"
          style={styles.headerButton}
        >
          <Ionicons name="chevron-back" size={24} color={revaColors.ink1} />
        </TouchableOpacity>
        <View style={styles.headerCopy}>
          <Text style={styles.headerTitle}>同行圈</Text>
          <Text style={styles.headerSubtitle}>匿名互助 · 不公开健康档案</Text>
        </View>
        <View style={styles.headerButton} />
      </View>

      <FlatList
        data={posts}
        keyExtractor={(item) => String(item.id)}
        renderItem={({ item }) => (
          <PeerPost
            post={item}
            busyReaction={busyReaction}
            onReaction={(post, reaction) => void toggleReaction(post, reaction)}
            onDelete={removePost}
            onReport={reportPost}
          />
        )}
        ListHeaderComponent={header}
        ListEmptyComponent={isLoading ? (
          <View style={styles.state}>
            <ActivityIndicator color={revaColors.green500} />
            <Text style={styles.stateText}>正在加载同行动态</Text>
          </View>
        ) : loadError ? (
          <View style={styles.state}>
            <Ionicons name="cloud-offline-outline" size={24} color={revaColors.ink3} />
            <Text style={styles.stateTitle}>动态暂时没有加载出来</Text>
            <TouchableOpacity onPress={() => void loadPosts()} style={styles.retryButton}>
              <Text style={styles.retryButtonText}>重新加载</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <View style={styles.state}>
            <Ionicons name="people-outline" size={24} color={revaColors.green500} />
            <Text style={styles.stateTitle}>还没有同行动态</Text>
            <Text style={styles.stateText}>第一条匿名行动，也可以从你开始。</Text>
          </View>
        )}
        contentContainerStyle={styles.content}
        ItemSeparatorComponent={() => <View style={styles.separator} />}
        refreshControl={(
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={() => void loadPosts(true)}
            tintColor={revaColors.green500}
          />
        )}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: revaColors.paper,
  },
  header: {
    minHeight: 58,
    paddingHorizontal: revaSpacing.s4,
    flexDirection: 'row',
    alignItems: 'center',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: revaColors.line,
    backgroundColor: revaColors.paper,
  },
  headerButton: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerCopy: {
    flex: 1,
    alignItems: 'center',
  },
  headerTitle: {
    ...revaType.title,
    fontFamily: revaFonts.cjk,
  },
  headerSubtitle: {
    ...revaType.caption,
    fontFamily: revaFonts.cjk,
    marginTop: 1,
  },
  content: {
    paddingHorizontal: revaSpacing.s4,
    paddingBottom: revaSpacing.s8,
  },
  intro: {
    paddingTop: revaSpacing.s5,
    paddingBottom: revaSpacing.s4,
  },
  introTitle: {
    ...revaType.h2,
    fontFamily: revaFonts.cjk,
  },
  introBody: {
    ...revaType.body2,
    fontFamily: revaFonts.cjk,
    marginTop: revaSpacing.s2,
  },
  composer: {
    backgroundColor: revaColors.surface,
    borderWidth: 1,
    borderColor: revaColors.green100,
    borderRadius: revaRadii.lg,
    padding: revaSpacing.s4,
    ...revaShadows.sm,
  },
  composerTitleRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  composerIcon: {
    width: 38,
    height: 38,
    borderRadius: revaRadii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: revaColors.green50,
  },
  composerCopy: {
    flex: 1,
    marginLeft: revaSpacing.s3,
  },
  composerTitle: {
    ...revaType.title,
    fontFamily: revaFonts.cjk,
  },
  composerPrivacy: {
    ...revaType.caption,
    fontFamily: revaFonts.cjk,
    marginTop: 3,
  },
  captionInput: {
    minHeight: 68,
    maxHeight: 120,
    marginTop: revaSpacing.s4,
    paddingHorizontal: revaSpacing.s3,
    paddingVertical: revaSpacing.s3,
    borderWidth: 1,
    borderColor: revaColors.line,
    borderRadius: revaRadii.sm,
    backgroundColor: revaColors.surface2,
    color: revaColors.ink1,
    fontFamily: revaFonts.cjk,
    fontSize: 14,
    lineHeight: 21,
    textAlignVertical: 'top',
  },
  captionSafety: {
    ...revaType.caption,
    fontFamily: revaFonts.cjk,
    color: revaColors.ink3,
    marginTop: revaSpacing.s2,
  },
  publishError: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: revaSpacing.s3,
  },
  publishErrorText: {
    ...revaType.caption,
    fontFamily: revaFonts.cjk,
    color: revaSemantic.risk.fg,
    marginLeft: revaSpacing.s2,
  },
  publishedNotice: {
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: revaSpacing.s4,
    borderWidth: 1,
    borderColor: revaColors.green100,
    borderRadius: revaRadii.md,
    backgroundColor: revaColors.green50,
  },
  publishedNoticeText: {
    ...revaType.body2,
    flex: 1,
    marginLeft: revaSpacing.s2,
    fontFamily: revaFonts.cjk,
    color: revaColors.green600,
  },
  composerActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: revaSpacing.s2,
    marginTop: revaSpacing.s4,
  },
  secondaryButton: {
    minHeight: 44,
    paddingHorizontal: revaSpacing.s4,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: revaColors.lineStrong,
    borderRadius: revaRadii.sm,
  },
  secondaryButtonText: {
    ...revaType.body2,
    fontFamily: revaFonts.cjk,
    fontWeight: '600',
  },
  primaryButton: {
    minHeight: 44,
    minWidth: 116,
    paddingHorizontal: revaSpacing.s4,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    borderRadius: revaRadii.sm,
    backgroundColor: revaColors.green500,
  },
  primaryButtonText: {
    ...revaType.body2,
    fontFamily: revaFonts.cjk,
    color: revaColors.greenOn,
    fontWeight: '700',
  },
  buttonDisabled: {
    opacity: 0.65,
  },
  feedHeading: {
    marginTop: revaSpacing.s6,
    marginBottom: revaSpacing.s3,
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
  },
  feedTitle: {
    ...revaType.h3,
    fontFamily: revaFonts.cjk,
  },
  feedNote: {
    ...revaType.caption,
    fontFamily: revaFonts.cjk,
  },
  post: {
    backgroundColor: revaColors.surface,
    borderWidth: 1,
    borderColor: revaColors.line,
    borderRadius: revaRadii.md,
    padding: revaSpacing.s4,
    ...revaShadows.sm,
  },
  postHeader: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  avatar: {
    width: 38,
    height: 38,
    borderRadius: revaRadii.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: revaColors.green50,
  },
  authorCopy: {
    flex: 1,
    minWidth: 0,
    marginLeft: revaSpacing.s3,
  },
  author: {
    ...revaType.body2,
    fontFamily: revaFonts.cjk,
    color: revaColors.ink1,
    fontWeight: '700',
  },
  meta: {
    ...revaType.caption,
    fontFamily: revaFonts.cjk,
    marginTop: 1,
  },
  iconButton: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  food: {
    ...revaType.title,
    fontFamily: revaFonts.cjk,
    marginTop: revaSpacing.s4,
  },
  nutrition: {
    ...revaType.dataLabel,
    fontFamily: revaFonts.mono,
    color: revaColors.ink2,
    marginTop: revaSpacing.s2,
    lineHeight: 18,
  },
  caption: {
    ...revaType.body2,
    fontFamily: revaFonts.cjk,
    color: revaColors.ink1,
    marginTop: revaSpacing.s3,
    paddingTop: revaSpacing.s3,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: revaColors.line,
  },
  reactions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: revaSpacing.s2,
    marginTop: revaSpacing.s4,
  },
  reaction: {
    minHeight: 40,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
    paddingHorizontal: revaSpacing.s3,
    borderWidth: 1,
    borderColor: revaColors.line,
    borderRadius: revaRadii.pill,
    backgroundColor: revaColors.surface2,
  },
  reactionSelected: {
    backgroundColor: revaColors.green50,
    borderColor: revaColors.green100,
  },
  reactionPending: {
    opacity: 0.72,
  },
  reactionText: {
    ...revaType.caption,
    fontFamily: revaFonts.cjk,
    color: revaColors.ink2,
  },
  reactionTextSelected: {
    color: revaColors.green600,
  },
  separator: {
    height: revaSpacing.s3,
  },
  state: {
    minHeight: 180,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: revaSpacing.s6,
  },
  stateTitle: {
    ...revaType.title,
    fontFamily: revaFonts.cjk,
    marginTop: revaSpacing.s3,
    textAlign: 'center',
  },
  stateText: {
    ...revaType.body2,
    fontFamily: revaFonts.cjk,
    marginTop: revaSpacing.s2,
    textAlign: 'center',
  },
  retryButton: {
    minHeight: 40,
    marginTop: revaSpacing.s4,
    paddingHorizontal: revaSpacing.s4,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: revaRadii.sm,
    backgroundColor: revaColors.green50,
  },
  retryButtonText: {
    ...revaType.body2,
    fontFamily: revaFonts.cjk,
    color: revaColors.green600,
    fontWeight: '700',
  },
});
