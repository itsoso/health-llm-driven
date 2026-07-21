import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const root = process.cwd();

describe('Web credential storage', () => {
  it('keeps JWTs out of browser persistent storage and URL parameters', () => {
    const authSource = fs.readFileSync(path.join(root, 'src/contexts/AuthContext.tsx'), 'utf8');
    const clientSource = fs.readFileSync(path.join(root, 'src/services/api/client.ts'), 'utf8');
    const settingsSource = fs.readFileSync(path.join(root, 'src/app/settings/page.tsx'), 'utf8');

    expect(authSource).not.toContain("localStorage.setItem('auth_token'");
    expect(authSource).not.toContain("localStorage.getItem('auth_token'");
    expect(clientSource).not.toContain("localStorage.getItem('auth_token'");
    expect(settingsSource).not.toContain('quick-record?token=${token}');
  });
});
