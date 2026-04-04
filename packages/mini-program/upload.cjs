const path = require('path');
const ci = require(path.join(__dirname, 'node_modules', 'miniprogram-ci'));
const project = new ci.Project({
  appid: 'wx169f93db056a7dd5',
  type: 'miniProgram',
  projectPath: path.join(__dirname, 'dist'),
  privateKeyPath: '/Users/liqiuhua/Downloads/private.wx169f93db056a7dd5.key',
  ignores: ['node_modules/**/*'],
});
ci.upload({
  project,
  version: '1.0.1',
  desc: '统一 OpenClaw 智能助理 + 消息反馈 + 动态快捷问题',
  robot: 1,
}).then(() => { console.log('✅ 上传成功!'); process.exit(0); })
  .catch(e => { console.error('❌ 上传失败:', e.message); process.exit(1); });
