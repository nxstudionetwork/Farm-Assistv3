const fs = require('fs');
const os = require('os');
const path = require('path');
const cp = require('child_process');

const T = path.join(os.tmpdir(), 'opencode');
fs.mkdirSync(T, { recursive: true });
const LOGF = path.join(T, 'final_git_truth.txt');
const out = [];

function base() {
  const dl = path.join(os.homedir(), 'Downloads');
  for (const n of fs.readdirSync(dl)) {
    const p = path.join(dl, n);
    try {
      if (!fs.statSync(p).isDirectory()) continue;
      if (/assist/i.test(n) && fs.existsSync(path.join(p, '.git'))) return p;
    } catch (e) {}
  }
  return null;
}
const B = base();
out.push('BASE=' + (B || 'NONE'));
if (!B) { fs.writeFileSync(LOGF, out.join('\n')); console.log('done'); process.exit(0); }

function g(args) {
  try { return cp.execFileSync('git', args, { cwd: B, encoding: 'utf8' }).trim(); }
  catch (e) { return 'GITERR'; }
}

out.push('BRANCH=' + g(['rev-parse', '--abbrev-ref', 'HEAD']));
out.push('LOG=' + g(['log', '--oneline', '-6']));
out.push('STATUS=' + g(['status', '--short']));

const files = {
  model: path.join(B, 'backend', 'app', 'models', 'livestock.py'),
  router: path.join(B, 'backend', 'app', 'routers', 'livestock.py'),
  svc: path.join(B, 'frontend', 'js', 'services.js'),
  html: path.join(B, 'frontend', 'livestock.html'),
};
const markers = {
  model: ['class LivestockPhoto', 'photos = relationship', 'photo_url = Column', 'is_primary = Column', 'sort_order = Column'],
  router: ['list_photos', '_get_photo_or_404', '_photo_dict', 'class LivestockPhotoCreate', 'class LivestockPhotoUpdate'],
  svc: ['listPhotos:', 'addPhoto:', 'updatePhoto:', 'deletePhoto:'],
  html: ['Photo Vault', 'photos-grid', 'photo-vault-subform', 'add-photo-btn', 'photo-caption-input', 'vault-upload-btn'],
};
for (const k of Object.keys(files)) {
  const p = files[k];
  out.push('KV=' + k + ' exists=' + fs.existsSync(p));
  if (!fs.existsSync(p)) continue;
  const s = fs.readFileSync(p, 'utf8');
  out.push('KV=' + k + ' lines=' + s.split('\n').length);
  let hits = [];
  for (const m of markers[k]) {
    const c = s.split(m).length - 1;
    if (c > 0) hits.push(m + ':' + c);
  }
  out.push('KV=' + k + ' hits=[' + hits.join(' | ') + ']');
}

fs.writeFileSync(LOGF, out.join('\n'), 'utf8');
console.log('done');
