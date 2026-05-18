const fs = require('fs');
const path = require('path');

const gradlePath = path.join(
  __dirname,
  '..',
  'node_modules',
  '@react-native-voice',
  'voice',
  'android',
  'build.gradle',
);

if (!fs.existsSync(gradlePath)) {
  console.warn(`[postinstall] @react-native-voice/voice build.gradle not found: ${gradlePath}`);
  process.exit(0);
}

let source = fs.readFileSync(gradlePath, 'utf8');
let next = source
  .replace(/repositories \{\n    mavenLocal\(\)\n    jcenter\(\)/, [
    'repositories {',
    '    mavenLocal()',
    '    google()',
    '    mavenCentral()',
  ].join('\n'))
  .replace(/repositories \{\n            jcenter\(\)\n        \}/, [
    'repositories {',
    '            google()',
    '            mavenCentral()',
    '        }',
  ].join('\n'))
  .replace(/allprojects \{\n    repositories \{\n        jcenter\(\)\n    \}\n\}/, [
    'allprojects {',
    '    repositories {',
    '        google()',
    '        mavenCentral()',
    '    }',
    '}',
  ].join('\n'));

if (!next.includes('def safeExtGet(prop, fallback)')) {
  next = next.replace(
    'def DEFAULT_SUPPORT_LIB_VERSION = "28.0.0"\n',
    [
      'def DEFAULT_SUPPORT_LIB_VERSION = "28.0.0"',
      '',
      'def safeExtGet(prop, fallback) {',
      '    rootProject.ext.has(prop) ? rootProject.ext.get(prop) : fallback',
      '}',
      '',
    ].join('\n'),
  );
}

next = next
  .replace(
    /android \{\n    compileSdkVersion rootProject\.hasProperty\('compileSdkVersion'\) \? rootProject\.compileSdkVersion : DEFAULT_COMPILE_SDK_VERSION\n    buildToolsVersion rootProject\.hasProperty\('buildToolsVersion'\) \? rootProject\.buildToolsVersion : DEFAULT_BUILD_TOOLS_VERSION/,
    [
      'android {',
      '    namespace "com.wenkesj.voice"',
      "    compileSdk = safeExtGet('compileSdkVersion', DEFAULT_COMPILE_SDK_VERSION) as Integer",
      "    buildToolsVersion safeExtGet('buildToolsVersion', DEFAULT_BUILD_TOOLS_VERSION)",
    ].join('\n'),
  )
  .replace(
    /defaultConfig \{\n        minSdkVersion 15\n        targetSdkVersion rootProject\.hasProperty\('targetSdkVersion'\) \? rootProject\.targetSdkVersion : DEFAULT_TARGET_SDK_VERSION/,
    [
      'defaultConfig {',
      "        minSdkVersion safeExtGet('minSdkVersion', 15)",
      "        targetSdkVersion safeExtGet('targetSdkVersion', DEFAULT_TARGET_SDK_VERSION)",
    ].join('\n'),
  )
  .replace(
    /    implementation "com\.android\.support:appcompat-v7:\$\{supportVersion\}"/,
    '    implementation "androidx.annotation:annotation:1.9.1"',
  );

if (source !== next) {
  fs.writeFileSync(gradlePath, next);
  console.log('[postinstall] patched @react-native-voice/voice Android Gradle config');
} else {
  console.log('[postinstall] @react-native-voice/voice Android Gradle config already patched');
}
