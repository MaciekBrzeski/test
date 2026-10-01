// Builds the fixture PDFs once per test run.
const { execFileSync } = require('child_process');
const path = require('path');

module.exports = async () => {
  const root = path.resolve(__dirname, '..');
  execFileSync(process.env.PYTHON || 'python3', [path.join(__dirname, 'build_fixtures.py')],
               { cwd: root, stdio: 'inherit' });
};
