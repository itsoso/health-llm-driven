import React from 'react';
import SettingsScreen from '../settings';

// A tab can have history without being a stack child. Its exit always returns home.
export default function MeScreen() {
  return <SettingsScreen home />;
}
