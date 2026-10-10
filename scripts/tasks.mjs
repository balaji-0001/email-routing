// Local development tasks. Run them through the root package.json scripts,
// for example `pnpm dev` or `pnpm db:start`.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const envFile = path.join(root, '.env');
if (existsSync(envFile)) process.loadEnvFile(envFile); // variables already set in the shell win

const windows = process.platform === 'win32';
const backend = path.join(root, 'backend');
const python = path.join(backend, '.venv', windows ? 'Scripts/python.exe' : 'bin/python');

const databaseUrl = new URL((process.env.DATABASE_URL || 'mysql+pymysql://root@127.0.0.1:3308/email_management').replace(/^mysql\+\w+:/, 'mysql:'));
const database = databaseUrl.pathname.slice(1) || 'email_management';
const mysqlPort = Number(databaseUrl.port || 3306);
const mysqlHost = databaseUrl.hostname;
const mysqlData = path.join(root, 'local-mysql', 'data');
const mysqlLog = path.join(root, 'local-mysql', 'mysql.log');

function fail(message) {
  console.error(message);
  process.exit(1);
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, { stdio: 'inherit', cwd: root, ...options });
  if (result.error) fail(`Could not run ${command}: ${result.error.message}`);
  if (result.status !== 0) process.exit(result.status ?? 1);
}

function requireBackend() {
  if (!existsSync(python)) fail('The backend is not installed yet. Run `pnpm setup` first.');
}

/** A MySQL program from MYSQL_HOME, a server unpacked into local-mysql/server, or the PATH. */
function mysqlProgram(name) {
  const exe = windows ? `${name}.exe` : name;
  for (const home of [process.env.MYSQL_HOME, path.join(root, 'local-mysql', 'server')]) {
    if (home && existsSync(path.join(home, 'bin', exe))) return path.join(home, 'bin', exe);
  }
  return exe;
}

function listening(port, host = '127.0.0.1') {
  return new Promise((resolve) => {
    const socket = net.connect({ port, host });
    socket.once('connect', () => { socket.destroy(); resolve(true); });
    socket.once('error', () => resolve(false));
    socket.setTimeout(1000, () => { socket.destroy(); resolve(false); });
  });
}

const databaseIsLocal = ['127.0.0.1', 'localhost'].includes(mysqlHost);
const rootLogin = ['-h', '127.0.0.1', '-P', String(mysqlPort), '-u', 'root'];

async function dbStart() {
  if (!databaseIsLocal) return console.log(`DATABASE_URL points at ${mysqlHost}; not starting a local MySQL.`);
  if (await listening(mysqlPort)) return console.log(`MySQL is already running on port ${mysqlPort}.`);

  const mysqld = mysqlProgram('mysqld');
  if (!existsSync(mysqlData)) {
    console.log('Creating the local MySQL data folder (first run only)...');
    mkdirSync(path.dirname(mysqlData), { recursive: true });
    // Creates a root user without a password. The server only ever listens on 127.0.0.1.
    run(mysqld, ['--initialize-insecure', `--datadir=${mysqlData}`, '--console']);
  }

  // The server writes its own log, so it keeps no ties to this process or its terminal.
  const server = spawn(mysqld, [`--datadir=${mysqlData}`, `--port=${mysqlPort}`, '--bind-address=127.0.0.1', '--mysqlx=OFF', `--log-error=${mysqlLog}`], {
    detached: true,
    stdio: 'ignore',
    windowsHide: true,
  });
  server.on('error', (error) => fail(`Could not start MySQL (${error.message}). Set MYSQL_HOME in .env to your MySQL server folder.`));
  server.unref();

  for (let waited = 0; !(await listening(mysqlPort)); waited++) {
    if (waited >= 60) fail(`MySQL did not come up on port ${mysqlPort}. See ${mysqlLog}.`);
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  const create = [database, `${database}_test`].map((name) => `CREATE DATABASE IF NOT EXISTS \`${name}\` CHARACTER SET utf8mb4`).join('; ');
  run(mysqlProgram('mysql'), [...rootLogin, '-e', create]);
  console.log(`MySQL is running on port ${mysqlPort} (databases ${database} and ${database}_test).`);
}

async function dbStop() {
  if (!(await listening(mysqlPort))) return console.log(`MySQL is not running on port ${mysqlPort}.`);
  run(mysqlProgram('mysqladmin'), [...rootLogin, 'shutdown']);
  console.log('MySQL stopped.');
}

async function dbStatus() {
  console.log((await listening(mysqlPort)) ? `MySQL is running on port ${mysqlPort}.` : `MySQL is not running on port ${mysqlPort}.`);
}

function migrate() {
  requireBackend();
  run(python, ['-m', 'alembic', 'upgrade', 'head'], { cwd: backend });
}

function apiCommand() {
  return [python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', process.env.PORT || '5000', '--reload']];
}

async function setup() {
  if (!existsSync(python)) {
    console.log('Creating the Python environment in backend/.venv...');
    run(windows ? 'py' : 'python3', [...(windows ? ['-3'] : []), '-m', 'venv', path.join(backend, '.venv')]);
  }
  run(python, ['-m', 'pip', 'install', '--disable-pip-version-check', '-q', '-r', 'requirements-dev.txt'], { cwd: backend });
  await dbStart();
  migrate();
  console.log('Ready. Start everything with `pnpm dev`.');
}

/** Database, API and web app together; Ctrl+C stops the API and the web app. */
async function dev() {
  requireBackend();
  await dbStart();
  migrate();

  const children = [];
  const start = (label, command, args, options) => {
    const child = spawn(command, args, { cwd: root, ...options });
    const print = (chunk) => String(chunk).split(/\r?\n/).filter(Boolean).forEach((line) => console.log(`[${label}] ${line}`));
    child.stdout.on('data', print);
    child.stderr.on('data', print);
    child.on('exit', (code) => { console.log(`[${label}] stopped (${code})`); stop(); });
    children.push(child);
  };
  let stopping = false;
  const stop = () => {
    if (stopping) return;
    stopping = true;
    for (const child of children) {
      if (windows) spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' });
      else child.kill('SIGTERM');
    }
    process.exit(0);
  };
  process.on('SIGINT', stop);
  process.on('SIGTERM', stop);

  const [command, args] = apiCommand();
  start('api', command, args, { cwd: backend });
  // pnpm is a script on Windows, so it has to go through the shell: one command string, no separate arguments.
  start('web', 'pnpm --filter frontend run dev', [], { shell: true });
}

const [task, ...rest] = process.argv.slice(2);
const tasks = {
  setup,
  dev,
  api: () => { requireBackend(); const [command, args] = apiCommand(); run(command, args, { cwd: backend }); },
  migrate,
  test: () => { requireBackend(); run(python, ['-m', 'pytest', ...rest], { cwd: backend }); },
  'db:start': dbStart,
  'db:stop': dbStop,
  'db:status': dbStatus,
};

if (!tasks[task]) fail(`Unknown task "${task ?? ''}". Try one of: ${Object.keys(tasks).join(', ')}`);
await tasks[task]();
