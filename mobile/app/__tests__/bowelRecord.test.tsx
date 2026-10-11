import React from 'react';
import { Alert } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import * as ImagePicker from 'expo-image-picker';
import * as ImageManipulator from 'expo-image-manipulator';
import BowelRecordScreen from '../bowel-record';
import * as service from '../../services/excretion';

let mockOwner = 7;
let mockRevision = 1;
jest.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ user: { id: mockOwner }, token: 'synthetic-session', isLoading: false }) }));
jest.mock('../../services/aiConsentState', () => ({ aiConsentRevision: () => mockRevision, subscribeAIConsentInvalidation: () => () => {} }));
jest.mock('expo-modules-core', () => ({ ...jest.requireActual('expo-modules-core'), uuid: { v4: () => 'bdbe0a80-b169-4a45-86d3-f4c28419654d' } }));
jest.mock('expo-image-picker', () => ({
  requestCameraPermissionsAsync: jest.fn(), launchCameraAsync: jest.fn(), launchImageLibraryAsync: jest.fn(),
}));
jest.mock('expo-image-manipulator', () => ({ SaveFormat: { JPEG: 'jpeg' }, manipulateAsync: jest.fn().mockResolvedValue({ uri: 'file:///synthetic/sanitized.jpg' }) }));
jest.mock('../../services/excretion', () => ({
  listBowelRecords: jest.fn(), getBowelRecord: jest.fn(), createBowelRecord: jest.fn(), uploadBowelPhoto: jest.fn(),
  bowelPhotoUrl: (url: string) => `https://synthetic.invalid${url}`,
}));
const inputPhoto = { uri: 'file:///synthetic/photo.jpg', mimeType: 'image/jpeg' };
const saved = { id: 41, user_id: 7, type: 'bowel', record_date: '2026-10-11', record_time: '08:30:00', photo_url: null };
beforeEach(() => {
  jest.clearAllMocks(); mockOwner = 7; mockRevision = 1;
  (service.listBowelRecords as jest.Mock).mockResolvedValue([]);
  (service.createBowelRecord as jest.Mock).mockResolvedValue(saved);
  (service.uploadBowelPhoto as jest.Mock).mockResolvedValue('medical/7/synthetic.jpg');
  (ImagePicker.requestCameraPermissionsAsync as jest.Mock).mockResolvedValue({ granted: true });
  (ImagePicker.launchCameraAsync as jest.Mock).mockResolvedValue({ canceled: false, assets: [inputPhoto] });
  (ImagePicker.launchImageLibraryAsync as jest.Mock).mockResolvedValue({ canceled: false, assets: [inputPhoto] });
  jest.spyOn(Alert, 'alert').mockImplementation(() => {});
});
afterEach(() => jest.restoreAllMocks());

it('only writes after explicit save and keeps unknown observations undefined', async () => {
  const screen = render(<BowelRecordScreen />);
  await waitFor(() => expect(service.listBowelRecords).toHaveBeenCalled());
  expect(service.createBowelRecord).not.toHaveBeenCalled();
  fireEvent.press(screen.getByLabelText('保存排便记录'));
  await waitFor(() => expect(screen.getByText('排便记录已保存。')).toBeTruthy());
  expect(service.createBowelRecord).toHaveBeenCalledWith({ owner: 7, revision: 1 }, expect.objectContaining({
    type: 'bowel', stool_type: undefined, blood_present: undefined, pain_level: undefined,
    client_request_id: 'bdbe0a80-b169-4a45-86d3-f4c28419654d',
  }));
  expect(service.uploadBowelPhoto).not.toHaveBeenCalled();
});

it('adds a photo locally then uploads and associates it only on save', async () => {
  const screen = render(<BowelRecordScreen />);
  fireEvent.press(screen.getByLabelText('拍照'));
  await waitFor(() => expect(screen.getByLabelText('待保存的排便照片')).toBeTruthy());
  expect(service.uploadBowelPhoto).not.toHaveBeenCalled();
  expect(ImageManipulator.manipulateAsync).toHaveBeenCalledWith(inputPhoto.uri, [], { compress: 0.8, format: 'jpeg' });
  fireEvent.press(screen.getByLabelText('4型 · 光滑软条'));
  fireEvent.press(screen.getByLabelText('未见血'));
  fireEvent.press(screen.getByLabelText('保存排便记录'));
  await waitFor(() => expect(service.createBowelRecord).toHaveBeenCalled());
  expect(service.createBowelRecord).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ photo_key: 'medical/7/synthetic.jpg', stool_type: 4, blood_present: false }));
});

it('allows photo removal without uploading', async () => {
  const screen = render(<BowelRecordScreen />);
  fireEvent.press(screen.getByLabelText('从相册选择'));
  await waitFor(() => expect(screen.getByLabelText('移除照片')).toBeTruthy());
  fireEvent.press(screen.getByLabelText('移除照片'));
  fireEvent.press(screen.getByLabelText('保存排便记录'));
  await waitFor(() => expect(service.createBowelRecord).toHaveBeenCalled());
  expect(service.uploadBowelPhoto).not.toHaveBeenCalled();
});

it('denied camera permission and cancellation do not write', async () => {
  (ImagePicker.requestCameraPermissionsAsync as jest.Mock).mockResolvedValueOnce({ granted: false });
  const screen = render(<BowelRecordScreen />);
  fireEvent.press(screen.getByLabelText('拍照'));
  await waitFor(() => expect(Alert.alert).toHaveBeenCalledWith('相机未授权', expect.any(String)));
  expect(ImagePicker.launchCameraAsync).not.toHaveBeenCalled();
  (ImagePicker.launchImageLibraryAsync as jest.Mock).mockResolvedValueOnce({ canceled: true });
  fireEvent.press(screen.getByLabelText('从相册选择'));
  await act(async () => {});
  expect(service.createBowelRecord).not.toHaveBeenCalled();
  expect(service.uploadBowelPhoto).not.toHaveBeenCalled();
});

it('retains content and reuses the same uploaded key and request ID on retry', async () => {
  (service.createBowelRecord as jest.Mock).mockRejectedValueOnce(new Error('synthetic_failure'));
  const screen = render(<BowelRecordScreen />);
  fireEvent.changeText(screen.getByLabelText('排便备注'), '合成观察');
  fireEvent.press(screen.getByLabelText('从相册选择'));
  await waitFor(() => expect(screen.getByLabelText('移除照片')).toBeTruthy());
  fireEvent.press(screen.getByLabelText('保存排便记录'));
  await waitFor(() => expect(screen.getByText(/保存未确认/)).toBeTruthy());
  expect(screen.getByLabelText('排便备注').props.value).toBe('合成观察');
  fireEvent.press(screen.getByLabelText('保存排便记录'));
  await waitFor(() => expect(service.createBowelRecord).toHaveBeenCalledTimes(2));
  expect(service.uploadBowelPhoto).toHaveBeenCalledTimes(1);
  const calls = (service.createBowelRecord as jest.Mock).mock.calls;
  expect(calls[0][1]).toEqual(calls[1][1]);
});

it('blocks immediate duplicate presses', async () => {
  let finish!: (value: unknown) => void;
  (service.createBowelRecord as jest.Mock).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
  const screen = render(<BowelRecordScreen />);
  fireEvent.press(screen.getByLabelText('保存排便记录'));
  fireEvent.press(screen.getByLabelText('保存排便记录'));
  expect(service.createBowelRecord).toHaveBeenCalledTimes(1);
  await act(async () => finish(saved));
});

it('discards pending photo selection on account switch', async () => {
  let finish!: (value: unknown) => void;
  (ImagePicker.launchImageLibraryAsync as jest.Mock).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
  const screen = render(<BowelRecordScreen />);
  fireEvent.press(screen.getByLabelText('从相册选择'));
  mockOwner = 8; mockRevision = 2;
  screen.rerender(<BowelRecordScreen />);
  await act(async () => finish({ canceled: false, assets: [inputPhoto] }));
  expect(screen.queryByLabelText('待保存的排便照片')).toBeNull();
  expect(service.uploadBowelPhoto).not.toHaveBeenCalled();
});

it('does not write after an old account upload completes', async () => {
  let finish!: (value: unknown) => void;
  (service.uploadBowelPhoto as jest.Mock).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
  const screen = render(<BowelRecordScreen />);
  fireEvent.press(screen.getByLabelText('从相册选择'));
  await waitFor(() => expect(screen.getByLabelText('移除照片')).toBeTruthy());
  fireEvent.press(screen.getByLabelText('保存排便记录'));
  mockOwner = 8; mockRevision = 2; screen.rerender(<BowelRecordScreen />);
  await act(async () => finish('medical/7/synthetic.jpg'));
  expect(service.createBowelRecord).not.toHaveBeenCalled();
  expect(screen.queryByText('排便记录已保存。')).toBeNull();
});

it('refreshes the private photo link when explicitly viewing a historical photo', async () => {
  (service.listBowelRecords as jest.Mock).mockResolvedValueOnce([{ ...saved, photo_url: '/expired' }]);
  (service.getBowelRecord as jest.Mock).mockResolvedValueOnce({ ...saved, photo_url: '/fresh' });
  const screen = render(<BowelRecordScreen />);
  await waitFor(() => expect(screen.getByLabelText('查看照片')).toBeTruthy());
  expect(screen.queryByLabelText('排便记录照片')).toBeNull();
  fireEvent.press(screen.getByLabelText('查看照片'));
  await waitFor(() => expect(screen.getByLabelText('排便记录照片')).toBeTruthy());
  expect(service.getBowelRecord).toHaveBeenCalledWith({ owner: 7, revision: 1 }, 41);
});

it('rejects impossible dates before writing', async () => {
  const screen = render(<BowelRecordScreen />);
  fireEvent.changeText(screen.getByLabelText('排便日期'), '2026-02-30');
  fireEvent.press(screen.getByLabelText('保存排便记录'));
  expect(service.createBowelRecord).not.toHaveBeenCalled();
  expect(screen.getByText('请填写有效日期和时间。')).toBeTruthy();
});
it('keeps a freshly saved record when the older history request finishes later', async () => {
  let finish!: (value: unknown) => void;
  (service.listBowelRecords as jest.Mock).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
  const screen = render(<BowelRecordScreen />);
  fireEvent.press(screen.getByLabelText('保存排便记录'));
  await waitFor(() => expect(screen.getByText('排便记录已保存。')).toBeTruthy());
  await act(async () => finish([]));
  expect(screen.getByText('2026-10-11 08:30')).toBeTruthy();
  expect(screen.queryByText('当天还没有排便记录。')).toBeNull();
});
