// Runs the backend's offline pytest suite with the backend virtual environment (`npm run test:backend`).
import { spawnSync } from 'node:child_process';
import { join } from 'node:path';
import { projectRoot } from './environment.mjs';

const backendDir = join(projectRoot, 'backend');
const python = process.platform === 'win32'
  ? join(backendDir, '.venv', 'Scripts', 'python.exe')
  : join(backendDir, '.venv', 'bin', 'python');
const result = spawnSync(python, ['-m', 'pytest', '-q', 'tests'], { cwd: backendDir, stdio: 'inherit' });
process.exit(result.status ?? 1);
