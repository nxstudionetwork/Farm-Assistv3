const fs = require('fs');
const path = require('path');
const os = require('os');
const { execFileSync } = require('child_process');

const LOG = path.join(os.tmpdir(), 'opencode', 'repo_audit_v3.txt');
fs.mkdirSync(path.dirname(LOG), { recursive: true });
const out = [];

const dl = path.join(os.homedir(), 'Downloads');
let BASE = null;
let BASE_NAME = null;
for (const n of fs.readdirSync(dl)) {
  const p = path.join(dl, n);
  if (!fs.statSync(p).isDirectory()) continue;
  if (!/Farm.*[Aa]ssist/i.test(n)) continue;
  if (/ - Copy/i.test(n) || /copy/i.test(n) || /v\d/i.test(n)) continueelman;
  if (fs.existsSync(path.join(p, '.git'))) { BASE = p; BASE_NAME = n; break; }
}
if (!BASE) { out.push('BASE_NOT_FOUND downloads=' + dl); finalize(); return; }
out.push('BASE=' + BASE);
out.push('BASE_NAME=' + BASE_NAME);

function g(args) {
  try { return execFileSync('git', args, { cwd: BASE, encoding: 'utf8' }).trim(); }
  catch (e) { return 'GIT_ERR ' + (e.stderr || '').toString().slice(0, 160); }
}

out.push('=== GIT_BRANCH ===');
out.push(g(['rev-parse', '--abbrev-ref', 'HEAD']));
out.push('=== GIT_STATUS_SHORT ===');
out.push(g(['status', '--short']));
out.push('=== GIT_LOG_LAST4 ===');
out.push(g(['log', '--oneline', '-4']));

// scan my livestock files for vault markers
const targets = [
  ['ROUTER', path.join(BASE, 'backend', 'app', 'routers', 'livestock.py')],
  ['MODEL', path.join(BASE, 'backend', 'app', 'models', 'livestock.py')],
  ['SERVICES_JS', path.join(BASE, 'frontend', 'js', 'services.js')],
  ['LIVESTOCK_HTML', path.join(BASE, 'frontend', 'livestock.html')],
];
const needles = ['async def list_photos', 'async def add_photo', 'async def delete_photo', 'class LivestockPhotoCreate', 'def _get_photo_or_404', 'photos-grid', 'Photo Vault', 'vault-upload-btn', 'listPhotos:', 'addPhoto:', 'deletePhoto:'];
for (const [tag, f] of targets) {
  out.push('=== ' + tag + ' exists=' + fs.existsSync(f) + ' ===');
  if (fs.existsSync(f)) {
    const s = fs.readFileSync(f, 'utf8');
    out.push('total_lines=' + s.split('\n').length);
    for (const n of needles) {
      out.push(n + ' => ' + (s.split(n).length - 1));
    }
  }
}

finalize();
function finalize() {
  fs.writeFileSync(LOG, out.join('\n'), 'utf8');
  console.log('WROTE');
}
