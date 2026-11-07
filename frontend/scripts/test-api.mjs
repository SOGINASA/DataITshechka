import {spawn} from 'node:child_process';
import {createServer} from 'node:net';
import {fileURLToPath} from 'node:url';
import {once} from 'node:events';

// Select a free loopback port; the fixture always creates a fresh temporary DB.
const reservation = createServer().listen(0, '127.0.0.1');
await once(reservation, 'listening');
process.env.QA_API_PORT = String(reservation.address().port);
await new Promise(resolve => reservation.close(resolve));
const child = spawn(process.env.PYTHON || 'python', [fileURLToPath(new URL('../tests/qa_backend.py', import.meta.url))], {
  env: process.env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
});
let output = '', spawnError;
child.on('error', error => { spawnError = error; });
child.stdout.on('data', data => { output += data; });
child.stderr.on('data', data => { output += data; });
const nativeFetch = globalThis.fetch;
try {
  let ready = false;
  for (let attempt = 0; attempt < 100; attempt++) {
    if (spawnError) throw spawnError;
    if (child.exitCode !== null) throw new Error(`Fixture failed: ${output}`);
    try { ready = (await nativeFetch(`http://127.0.0.1:${process.env.QA_API_PORT}/api/ready`)).ok; } catch {}
    if (ready) break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  if (!ready) throw new Error(`Fixture did not become ready: ${output}`);
  await import('../tests/api.integration.mjs');
} finally {
  globalThis.fetch = nativeFetch;
  child.kill();
}
