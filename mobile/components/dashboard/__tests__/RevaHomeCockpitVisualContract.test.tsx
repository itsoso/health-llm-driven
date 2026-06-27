import React from 'react';
import fs from 'fs';
import path from 'path';
import { render } from '@testing-library/react-native';

import { revaColors, revaFonts } from '../../../constants/revaTheme';
import ActivityRingBar from '../ActivityRingBar';
import VitalsGrid from '../VitalsGrid';
import MedicationCheckin from '../MedicationCheckin';
import BodyStatsRow from '../../home/BodyStatsRow';
import type { MedicationTodayItem } from '../../../services/medications';

const medItem: MedicationTodayItem = {
  medication_id: 1,
  name: '二甲双胍',
  dosage: '0.5g',
  category: null,
  total_count: 2,
  taken_count: 0,
  skipped_count: 0,
  last_taken_time: null,
  reminder_times: ['08:00'],
  logs: [],
};

describe('Reva Home cockpit visual contract', () => {
  it('does not use negative letter spacing in Home cockpit surfaces', () => {
    const mobileRoot = path.resolve(__dirname, '../../..');
    const roots = ['components/home', 'components/dashboard', 'app/(tabs)'];
    const offenders = roots.flatMap((root) =>
      listSourceFiles(path.join(mobileRoot, root)).flatMap((file) => {
        const rel = path.relative(mobileRoot, file);
        return fs
          .readFileSync(file, 'utf8')
          .split('\n')
          .flatMap((line, index) =>
            /letterSpacing:\s*-\d/.test(line) ? [`${rel}:${index + 1}:${line.trim()}`] : [],
          );
      }),
    );

    expect(offenders).toEqual([]);
  });

  it('keeps activity numbers on Reva mono with zero letter spacing', () => {
    const { getByText } = render(<ActivityRingBar steps={1234} activeMin={18} calories={260} />);

    expect(getByText('1,234')).toHaveStyle({
      color: revaColors.ink1,
      fontFamily: revaFonts.mono,
      letterSpacing: 0,
    });
  });

  it('keeps vital numbers on Reva mono with zero letter spacing', () => {
    const { getByText } = render(
      <VitalsGrid sleep={7.5} heartRate={61} hrv={48.2} bodyBatteryCurrent={72} />,
    );

    expect(getByText('7.5')).toHaveStyle({
      fontFamily: revaFonts.mono,
      letterSpacing: 0,
    });
  });

  it('keeps medication progress on Reva mono with zero letter spacing', () => {
    const { getByText } = render(<MedicationCheckin items={[medItem]} />);

    expect(getByText('0/2 已服')).toHaveStyle({
      fontFamily: revaFonts.mono,
      letterSpacing: 0,
    });
  });

  it('keeps body stat values on Reva mono with zero letter spacing', () => {
    const { getByText } = render(
      <BodyStatsRow values={{ bmi: 23.4, systolic: 120, diastolic: 80, spo2: 97, bodyFatPct: 18.5 }} />,
    );

    expect(getByText('23.4')).toHaveStyle({
      fontFamily: revaFonts.mono,
      letterSpacing: 0,
    });
  });
});

function listSourceFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return listSourceFiles(full);
    return /\.(tsx?|jsx?)$/.test(entry.name) ? [full] : [];
  });
}
