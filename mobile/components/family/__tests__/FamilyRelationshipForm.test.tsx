import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import FamilyRelationshipForm from '../FamilyRelationshipForm';
import { colors } from '../../../constants/theme';
jest.mock('../../../services/api', () => ({ __esModule: true, default: {} }));
it('requires explicit consent and supports daughter nickname on all platforms', async () => {
  const submit = jest.fn().mockResolvedValue(undefined);
  render(<FamilyRelationshipForm visible c={colors} mode="accept" onClose={jest.fn()} onSubmit={submit} />);
  fireEvent.changeText(screen.getByLabelText('邀请码'), ' abc123 ');
  fireEvent.changeText(screen.getByLabelText('家庭昵称'), '小禾');
  fireEvent.press(screen.getByText('女儿'));
  fireEvent.press(screen.getByText('同意并加入'));
  expect(submit).not.toHaveBeenCalled();
  fireEvent.press(screen.getByRole('checkbox'));
  fireEvent.press(screen.getByText('同意并加入'));
  await waitFor(() => expect(submit).toHaveBeenCalledWith('daughter', '小禾', 'ABC123'));
});
it('keeps errors visible without closing the form or pretending acceptance', async () => {
  const close = jest.fn();
  render(<FamilyRelationshipForm visible c={colors} mode="accept" onClose={close} onSubmit={jest.fn().mockRejectedValue(new Error('请求失败'))} />);
  fireEvent.changeText(screen.getByLabelText('邀请码'), 'ABC123');
  fireEvent.press(screen.getByRole('checkbox'));
  fireEvent.press(screen.getByText('同意并加入'));
  expect(await screen.findByText('请求失败')).toBeTruthy();
  expect(close).not.toHaveBeenCalled();
});
