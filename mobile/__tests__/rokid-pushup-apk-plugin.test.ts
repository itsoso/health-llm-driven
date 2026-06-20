const {
  _addBundledApkResource,
  _ensureResourcesGroup,
} = require('../plugins/withRokidPushupApk');

function createProjectMock(hasResourcesGroup = false) {
  const groups: Record<string, any> = hasResourcesGroup
    ? { Resources: { name: 'Resources', children: [], path: undefined } }
    : {};
  const addedGroups: any[] = [];
  const addedToGroups: any[] = [];
  const addedResourceFiles: any[] = [];

  return {
    addedGroups,
    addedToGroups,
    addedResourceFiles,
    project: {
      pbxGroupByName(name: string) {
        return groups[name] ?? null;
      },
      addPbxGroup(files: string[], name: string, groupPath?: string) {
        const group = {
          uuid: `${name}-uuid`,
          pbxGroup: {
            name,
            path: groupPath,
            children: files,
          },
        };
        groups[name] = group.pbxGroup;
        addedGroups.push({ files, name, groupPath });
        return group;
      },
      getFirstProject() {
        return { firstProject: { mainGroup: 'MAIN_GROUP' } };
      },
      addToPbxGroup(file: string, group: string) {
        addedToGroups.push({ file, group });
      },
      addResourceFile(resourcePath: string, options: any) {
        addedResourceFiles.push({ resourcePath, options });
      },
    },
  };
}

describe('withRokidPushupApk', () => {
  it('creates a Resources group before adding bundled APK resources', () => {
    const { project, addedGroups, addedToGroups } = createProjectMock();

    _ensureResourcesGroup(project);

    expect(project.pbxGroupByName('Resources')).toEqual({
      name: 'Resources',
      children: [],
    });
    expect(project.pbxGroupByName('Resources')).not.toHaveProperty('path');
    expect(addedGroups).toEqual([{ files: [], name: 'Resources', groupPath: undefined }]);
    expect(addedToGroups).toEqual([{ file: 'Resources-uuid', group: 'MAIN_GROUP' }]);
  });

  it('does not create a duplicate Resources group', () => {
    const { project, addedGroups, addedToGroups } = createProjectMock(true);

    _ensureResourcesGroup(project);

    expect(addedGroups).toEqual([]);
    expect(addedToGroups).toEqual([]);
  });

  it('adds the APK resource relative to SOURCE_ROOT', () => {
    const { project, addedResourceFiles } = createProjectMock();

    _addBundledApkResource(project, 'HEALTHPILOT_TARGET');

    expect(addedResourceFiles).toEqual([
      {
        resourcePath: 'HealthPilot/RokidApps/rokid-pushup-glasses.apk',
        options: {
          target: 'HEALTHPILOT_TARGET',
          sourceTree: 'SOURCE_ROOT',
        },
      },
    ]);
  });
});
