#!/usr/bin/env node
const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const cliPath = path.join(__dirname, '..', 'tools', 'cc-sdd', 'dist', 'cli.js');

// Build if dist doesn't exist (happens with npx github: installs)
if (!fs.existsSync(cliPath)) {
  console.error('Building cc-sdd-graph...');
  execSync('npm install && npm run build', {
    cwd: path.join(__dirname, '..', 'tools', 'cc-sdd'),
    stdio: 'inherit',
  });
}

require(cliPath);
