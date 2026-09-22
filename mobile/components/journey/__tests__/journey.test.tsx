import React from 'react';
import { Alert } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
const mockAuth = { user: { id: 1 }, token: 'token-a' };
jest.mock('../../../hooks/useAuth', () => ({ useAuth: () => mockAuth }));
jest.mock('expo-router', () => ({ Stack: { Screen: () => null }, router: { navigate: jest.fn() }, useFocusEffect: jest.fn() }));
jest.mock('react-native-safe-area-context', () => ({ SafeAreaView: require('react-native').View }));
jest.mock('../JourneyConstellation', () => ({ __esModule: true, default: () => null }));
jest.mock('../../../services/api', () => ({ __esModule: true, default: {}, BASE_URL: 'https://health.executor.life/api' }));
jest.mock('expo-location', () => ({ requestForegroundPermissionsAsync: jest.fn(), Accuracy: { Balanced: 3 } }));
jest.mock('../../../services/journey', () => ({ ...jest.requireActual('../../../services/journey'), journeyAPI: { month: jest.fn(), sources: jest.fn(), save: jest.fn(), remove: jest.fn(), preview: jest.fn() } }));
jest.mock('react-native-view-shot', () => ({ captureRef: jest.fn().mockResolvedValue('file:///capture.png'), releaseCapture: jest.fn() }));
jest.mock('../../../utils/share', () => ({ materializeImageForLocalUse: jest.fn(), shareLongImage: jest.fn(), shareImage: jest.fn() }));
jest.mock('expo-media-library', () => ({ requestPermissionsAsync: jest.fn().mockResolvedValue({ granted: true }), saveToLibraryAsync: jest.fn() }));
import JourneyScreen from '../../../app/journey';
import JourneyEditor from '../JourneyEditor';
import JourneyExportPanel from '../JourneyExportPanel';
import { journeyAPI, journeySessionRevision } from '../../../services/journey';
import { setAIConsentIdentity } from '../../../services/aiConsentState';
import { captureRef, releaseCapture } from 'react-native-view-shot';
import { materializeImageForLocalUse, shareImage } from '../../../utils/share';
const place = { id: 1, source_id: 11, kind: 'diet' as const, version: 1, city: '成都', local_date: '2026-09-22', timezone: 'Asia/Shanghai', location_source: 'manual' as const, title: '私密饮食文字', images: [{ key: 'photo1', url: 'https://health.executor.life/api/v1/upload/files/diet/1/a.jpg' }], image_status: 'ready' as const };
const source = { ...place, suggested_date: '2026-09-22', date_basis: 'record' as const, place: null };
const page = (items: any[], total = items.length) => ({ items, total, offset: 0, limit: 30 });
const publicPreview = { month: '2026-09', items: [{ city: '成都', local_date: '2026-09-22', kind: 'diet', images: [] }] };
beforeEach(() => {
  jest.clearAllMocks(); mockAuth.user = { id: 1 }; mockAuth.token = 'token-a';
  (journeyAPI.month as jest.Mock).mockResolvedValue(page([place]));
  (journeyAPI.sources as jest.Mock).mockResolvedValue(page([source]));
  (journeyAPI.preview as jest.Mock).mockResolvedValue(publicPreview);
});

describe('monthly journey page', () => {
  it('defaults every record and photo to unselected, and provides all source tabs', async () => {
    const view = render(<JourneyScreen />);
    await waitFor(() => expect(view.getByText('私密饮食文字')).toBeTruthy());
    expect(view.getByText('预览我的长图 · 已选 0 / 30')).toBeTruthy();
    fireEvent.press(view.getByLabelText('选择片段 2026-09-22 成都'));
    expect(view.getByText('□ 照片 1')).toBeTruthy();
    fireEvent.press(view.getByText('＋ 为记录添加地点'));
    await waitFor(() => expect(view.getByText('聊天照片')).toBeTruthy());
    fireEvent.press(view.getByText('聊天照片'));
    await waitFor(() => expect(journeyAPI.sources).toHaveBeenLastCalledWith('chat_photo', expect.any(String), expect.any(String), 0, expect.any(Number)));
  });
  it('does not treat one loaded page as full month', async () => {
    (journeyAPI.month as jest.Mock).mockResolvedValueOnce(page([place], 35)).mockResolvedValueOnce(page([{ ...place, id: 2, city: '北京' }], 35));
    const view = render(<JourneyScreen />);
    await waitFor(() => expect(view.getByText('加载更多片段（剩余 34）')).toBeTruthy());
    fireEvent.press(view.getByText('加载更多片段（剩余 34）'));
    await waitFor(() => expect(journeyAPI.month).toHaveBeenLastCalledWith(expect.any(String), 1, expect.any(Number)));
  });
  it('ignores old month response arriving after a month switch', async () => {
    let resolveOld!: (value: any) => void;
    (journeyAPI.month as jest.Mock).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; })).mockResolvedValueOnce(page([{ ...place, city: '新月份' }]));
    const view = render(<JourneyScreen />);
    fireEvent.press(view.getByLabelText('上个月'));
    await waitFor(() => expect(view.getByText('新月份')).toBeTruthy());
    await act(async () => resolveOld(page([place])));
    expect(view.queryByText('成都')).toBeNull();
  });
  it('account switch drops private records and old async responses', async () => {
    let resolveOld!: (value: any) => void;
    (journeyAPI.month as jest.Mock).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; })).mockResolvedValueOnce(page([]));
    const view = render(<JourneyScreen />);
    mockAuth.user = { id: 2 }; mockAuth.token = 'token-b';
    view.rerender(<JourneyScreen />);
    await act(async () => resolveOld(page([place])));
    expect(view.queryByText('私密饮食文字')).toBeNull();
  });
});

describe('journey edit safety', () => {
  it('preserves city draft on failed save and never silently overwrites a 409', async () => {
    (journeyAPI.save as jest.Mock).mockRejectedValue({ response: { status: 409 } });
    const onSaved = jest.fn();
    const view = render(<JourneyEditor source={source} timezone="Asia/Shanghai" revision={journeySessionRevision()} onSaved={onSaved} onClose={jest.fn()} onReload={jest.fn()} />);
    fireEvent.changeText(view.getByLabelText('城市'), '北京');
    fireEvent.press(view.getByText('确认日期与城市，保存'));
    await waitFor(() => expect(view.getByText('重新读取最新记录')).toBeTruthy());
    expect(view.getByLabelText('城市').props.value).toBe('北京');
    fireEvent.press(view.getByText('确认日期与城市，保存'));
    expect(journeyAPI.save).toHaveBeenCalledTimes(1);
    expect(onSaved).not.toHaveBeenCalled();
  });
  it('labels message date as not capture time and disables historical device location', () => {
    const view = render(<JourneyEditor source={{ ...source, suggested_date: '2020-01-01', date_basis: 'message' }} timezone="Asia/Shanghai" revision={journeySessionRevision()} onSaved={jest.fn()} onClose={jest.fn()} onReload={jest.fn()} />);
    expect(view.getByText('建议日期来自消息发送时间，不是照片拍摄时间。请核对真实发生日期。')).toBeTruthy();
    expect(view.getByText('历史记录请手动填写城市')).toBeTruthy();
  });
});

describe('version bound share preview', () => {
  it('captures fixed width with natural height and never renders private source fields', async () => {
    (journeyAPI.preview as jest.Mock).mockResolvedValue({ ...publicPreview, items: [{ ...publicPreview.items[0], title: '不可分享的私密原文', calories: 500 }] });
    const view = render(<JourneyExportPanel selection={[{ place_id: 1, version: 1, image_keys: [] }]} token="token-a" revision={journeySessionRevision()} onClose={jest.fn()} />);
    await waitFor(() => expect(view.getByText('成都')).toBeTruthy());
    expect(view.queryByText('不可分享的私密原文')).toBeNull();
    const layout = view.UNSAFE_getAllByType(require('react-native').View).find(node => node.props.onLayout);
    fireEvent(layout!, 'layout', { nativeEvent: { layout: { height: 500 } } });
    fireEvent.press(view.getByText('系统分享'));
    await waitFor(() => expect(shareImage).toHaveBeenCalled());
    expect(journeyAPI.preview).toHaveBeenCalledTimes(2);
    expect((captureRef as jest.Mock).mock.calls[0][1]).toEqual({ format: 'png', quality: 1, result: 'tmpfile', width: 720 });
    expect(releaseCapture).toHaveBeenCalledWith('file:///capture.png');
  });
  it('never captures before all selected images load and blocks image errors', async () => {
    const cleanup = jest.fn().mockResolvedValue(undefined);
    (journeyAPI.preview as jest.Mock).mockResolvedValue({ ...publicPreview, items: [{ ...publicPreview.items[0], images: place.images }] });
    (materializeImageForLocalUse as jest.Mock).mockResolvedValue({ uri: 'file:///private.jpg', cleanup });
    const view = render(<JourneyExportPanel selection={[{ place_id: 1, version: 1, image_keys: ['photo1'] }]} token="token-a" revision={journeySessionRevision()} onClose={jest.fn()} />);
    await waitFor(() => expect(view.getByText('成都')).toBeTruthy());
    const layout = view.UNSAFE_getAllByType(require('react-native').View).find(node => node.props.onLayout);
    fireEvent(layout!, 'layout', { nativeEvent: { layout: { height: 700 } } });
    fireEvent.press(view.getByText('系统分享'));
    expect(captureRef).not.toHaveBeenCalled();
    fireEvent(view.UNSAFE_getByType(require('react-native').Image), 'error');
    fireEvent.press(view.getByText('系统分享'));
    expect(captureRef).not.toHaveBeenCalled();
    expect(view.getByText('照片未能加载，不能导出。请重新预览，或关闭并取消选择该照片。')).toBeTruthy();
    view.unmount();
    await waitFor(() => expect(cleanup).toHaveBeenCalled());
  });
  it('rejects oversized photo selections before downloading any files', async () => {
    (journeyAPI.preview as jest.Mock).mockResolvedValue({ ...publicPreview, items: [{ ...publicPreview.items[0], images: Array.from({ length: 31 }, (_, index) => ({ key: String(index), url: place.images[0].url })) }] });
    const view = render(<JourneyExportPanel selection={[{ place_id: 1, version: 1, image_keys: [] }]} token="token-a" revision={journeySessionRevision()} onClose={jest.fn()} />);
    await waitFor(() => expect(view.getByText('长图过长，请减少片段或照片后重试')).toBeTruthy());
    expect(materializeImageForLocalUse).not.toHaveBeenCalled();
  });
  it('rechecks versions immediately before capture and rejects stale without sharing', async () => {
    (journeyAPI.preview as jest.Mock).mockResolvedValueOnce(publicPreview).mockRejectedValueOnce({ response: { status: 409 } });
    const view = render(<JourneyExportPanel selection={[{ place_id: 1, version: 1, image_keys: [] }]} token="token-a" revision={journeySessionRevision()} onClose={jest.fn()} />);
    await waitFor(() => expect(view.getByText('成都')).toBeTruthy());
    const layout = view.UNSAFE_getAllByType(require('react-native').View).find(node => node.props.onLayout);
    fireEvent(layout!, 'layout', { nativeEvent: { layout: { height: 500 } } });
    fireEvent.press(view.getByText('系统分享'));
    await waitFor(() => expect(view.getByText('片段或照片已变化，旧预览已失效，请重新选择。')).toBeTruthy());
    expect(captureRef).not.toHaveBeenCalled(); expect(shareImage).not.toHaveBeenCalled();
  });
  it('late photo materialization after close cleans up and never renders', async () => {
    let resolveImage!: (value: any) => void;
    const cleanup = jest.fn().mockResolvedValue(undefined);
    (journeyAPI.preview as jest.Mock).mockResolvedValue({ ...publicPreview, items: [{ ...publicPreview.items[0], images: place.images }] });
    (materializeImageForLocalUse as jest.Mock).mockImplementation(() => new Promise(resolve => { resolveImage = resolve; }));
    const view = render(<JourneyExportPanel selection={[{ place_id: 1, version: 1, image_keys: ['photo1'] }]} token="token-a" revision={journeySessionRevision()} onClose={jest.fn()} />);
    await waitFor(() => expect(materializeImageForLocalUse).toHaveBeenCalledTimes(1));
    view.unmount();
    await act(async () => resolveImage({ uri: 'file:///private.jpg', cleanup }));
    expect(cleanup).toHaveBeenCalledTimes(1); expect(captureRef).not.toHaveBeenCalled();
  });
  it('blocks late session change before preparing an image', async () => {
    let resolvePreview!: (value: any) => void;
    (journeyAPI.preview as jest.Mock).mockImplementation(() => new Promise(resolve => { resolvePreview = resolve; }));
    const view = render(<JourneyExportPanel selection={[{ place_id: 1, version: 1, image_keys: [] }]} token="token-a" revision={journeySessionRevision()} onClose={jest.fn()} />);
    await waitFor(() => expect(journeyAPI.preview).toHaveBeenCalled());
    setAIConsentIdentity('switched-account');
    await act(async () => resolvePreview(publicPreview));
    expect(view.queryByText('成都')).toBeNull();
    expect(materializeImageForLocalUse).not.toHaveBeenCalled();
  });
});
