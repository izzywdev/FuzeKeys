#!/usr/bin/env node

const { spawn } = require('child_process');

console.log('🧪 Running SitesDatabase tests...');
console.log('Working directory:', process.cwd());

const testProcess = spawn('npm', ['test', '--', 'SitesDatabase'], {
  stdio: 'inherit',
  cwd: __dirname
});

testProcess.on('close', (code) => {
  console.log(`\n📊 Test process exited with code ${code}`);
  if (code === 0) {
    console.log('✅ Tests passed successfully!');
  } else {
    console.log('❌ Tests failed or encountered errors');
  }
  process.exit(code);
});

testProcess.on('error', (error) => {
  console.error('❌ Failed to start test process:', error);
  process.exit(1);
});
