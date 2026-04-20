const path = require('path');
const fs = require('fs');

jest.mock('@expo/config-plugins', () => {
  const passthrough = (config, fn) => {
    const mod = {
      modRequest: { projectRoot: '/tmp/test-project' },
      modResults: {},
    };
    fn(mod);
    return config;
  };
  return {
    withXcodeProject: jest.fn((config, fn) => {
      const mod = {
        modRequest: { projectRoot: '/tmp/test-project' },
        modResults: {
          generateUuid: jest.fn().mockReturnValue('TEST-UUID'),
          addPbxGroup: jest.fn().mockReturnValue({ uuid: 'GROUP-UUID' }),
          addTarget: jest.fn().mockReturnValue({ uuid: 'TARGET-UUID' }),
          addBuildProperty: jest.fn(),
          addSourceFile: jest.fn(),
        },
      };
      fn(mod);
      return config;
    }),
    withEntitlementsPlist: jest.fn(passthrough),
    withInfoPlist: jest.fn(passthrough),
  };
});

jest.mock('fs', () => {
  const actual = jest.requireActual('fs');
  return {
    ...actual,
    existsSync: jest.fn().mockReturnValue(false),
    mkdirSync: jest.fn(),
    writeFileSync: jest.fn(),
  };
});

const { withXcodeProject, withEntitlementsPlist, withInfoPlist } = require('@expo/config-plugins');

describe('withIntentsExtension', () => {
  let plugin;

  beforeEach(() => {
    jest.clearAllMocks();
    plugin = require('../withIntentsExtension');
  });

  it('is a function', () => {
    expect(typeof plugin).toBe('function');
  });

  it('calls withEntitlementsPlist', () => {
    const config = { ios: { bundleIdentifier: 'life.executor.health' } };
    plugin(config);
    expect(withEntitlementsPlist).toHaveBeenCalled();
  });

  it('calls withInfoPlist', () => {
    const config = { ios: { bundleIdentifier: 'life.executor.health' } };
    plugin(config);
    expect(withInfoPlist).toHaveBeenCalled();
  });

  it('calls withXcodeProject', () => {
    const config = { ios: { bundleIdentifier: 'life.executor.health' } };
    plugin(config);
    expect(withXcodeProject).toHaveBeenCalled();
  });

  it('writes extension files when missing', () => {
    fs.existsSync.mockReturnValue(false);
    const config = { ios: { bundleIdentifier: 'life.executor.health' } };
    plugin(config);
    expect(fs.mkdirSync).toHaveBeenCalled();
    expect(fs.writeFileSync).toHaveBeenCalled();
  });

  it('sets Siri entitlement on main app', () => {
    const config = { ios: { bundleIdentifier: 'life.executor.health' } };
    plugin(config);

    const entitlementCall = withEntitlementsPlist.mock.calls[0];
    const mod = { modResults: {} };
    entitlementCall[1](mod);
    expect(mod.modResults['com.apple.developer.siri']).toBe(true);
    expect(mod.modResults['com.apple.security.application-groups']).toContain('group.life.executor.health');
  });
});
