// Starts the FastAPI backend from backend/.venv on http://127.0.0.1:8000 (used by `npm run backend`).
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { projectRoot } from './environment.mjs';

const backendDir = join(projectRoot, 'backend');
const python = process.platform === 'win32'
  ? join(backendDir, '.venv', 'Scripts', 'python.exe')
  : join(backendDir, '.venv', 'bin', 'python');

if (!existsSync(python)) {
  console.error('backend/.venv not found. Create it first (see README: "Backend setup").');
  process.exit(1);
}
if (!existsSync(join(backendDir, '.env'))) {
  console.warn('Warning: backend/.env is missing. Copy backend/.env.example to backend/.env and add your OpenRouter key.');
}

// --reload watches only backend/app (code and prompt files), not backend/data, so uploads do not restart it.
// Changes to backend/.env still need a manual restart.
const child = spawn(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000',
  '--reload', '--reload-dir', 'app', '--reload-include', '*.md'], {
  cwd: backendDir, stdio: 'inherit',
});
child.on('exit', (code) => process.exit(code ?? 0));
for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => child.kill(signal));
