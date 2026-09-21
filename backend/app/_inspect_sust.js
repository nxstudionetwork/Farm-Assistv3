const fs = require('fs');
const path = require('path');
const root = 'C:\\Users\\AICOE 5\\Downloads\\Farm_Assist.Application';

// 1. main.py wiring
console.log('=== main.py: how routers are registered + app lifecycle (include_router / create_all / seeds / auth dep) ===');
try {
  const m = fs.readFileSync(path.join(root, 'backend', 'app', 'main.py'), 'utf8').split(/\r?\n/);
  m.forEach((l, i) => {
    const t = l.trim();
    if (/include_router|create_all|seed|get_current_user|from app|import |FastAPI\(|on_event|startup|lifespan|Base\.metadata/.test(t)) {
      console.log(String(i + 1).padStart(4) + '| ' + t.replace(/\s+/g, ' '));
    }
  });
} catch (e) { console.log('ERR main.py: ' + e.message); }

// 2. soil router existence + pattern (reuse its auth+ownership approach)
console.log('\n=== routers/soil_irrigation.py? + models/soil_irrigation? ==="');
for (const rel of ['backend/app/routers/soil_irrigation.py', 'backend/app/models/soil_irrigation.py']) {
  const p = path.join(root, rel);
  const ex = fs.existsSync(p);
  console.log((ex ? 'EXISTS' : 'MISSING') + '  ' + rel);
}

// 3. which model file actually holds SoilRecord/SoilRecord tables (crop.py showed? earlier grep showed crop.py but maybe duplicates) — find the REAL one we reuse
console.log('\n=== actual models that carry sustainability-parseable tables (SoilRecord/IrrigationRecord/WaterUsage) ===');
function scan(dir) {
  if (!fs.existsSync(dir)) return;
  for (const f of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, f.name);
    if (f.isDirectory()) { if (f.name !== '__pycache__' && f.name !== 'migrations') scan(full); }
    else if (f.name.endsWith('.py')) {
      const txt = fs.readFileSync(full, 'utf8');
      if (/class (SoilRecord|IrrigationRecord|WaterUsage|EnergyUsage|Sustainability\w*Record|SustainablePractice)/.test(txt)) {
        console.log(full.replace(root + '\\', ''));
        txt.split(/\r?\n/).forEach((l, i) => {
          if (/class (SoilRecord|IrrigationRecord|WaterUsage|EnergyUsage|Sustainability\w*Record|SustainablePractice)\(Base\)/.test(l.trim())) {
            console.log('    ' + String(i + 1) + '| ' + l.trim());
          }
        });
      }
    }
  }
}
scan(path.join(root, 'backend', 'app', 'models'));

// 4. how tables get created — find create_all call sites + any alembic/upgrade harness that must keep in sync
console.log('\n=== create_all call sites across backend (the DB-init choke point) ===');
function scan2(dir) {
  if (!fs.existsSync(dir)) return;
  for (const f of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, f.name);
    if (f.isDirectory()) { if (f.name !== '__pycache__' && f.name !== 'node_modules' && f.name !== 'migrations' && f.name !== 'venv' && f.name !== '.venv' && f.name !== '__pycache__') scan2(full); }
    else if (f.name.endsWith('.py')) {
      const txt = fs.readFileSync(full, 'utf8');
      if (/metadata\.create_all|create_all\(/.test(txt)) {
        console.log(full.replace(root + '\\', ''));
        txt.split(/\r?\n/).forEach((l, i) => {
          if (/create_all/.test(l)) console.log('    ' + String(i + 1) + '| ' + l.trim());
        });
      }
    }
  }
}
scan2(path.join(root, 'backend'));

// 5. sustainability.html current API calls (should be ZERO — the stub)
const sh = path.join(root, 'frontend', 'sustainability.html');
if (fs.existsSync(sh)) {
  console.log('\n=== sustainability.html inline API references (expect: none = stub) ===');
  const txt = fs.readFileSync(sh, 'utf8');
  const hits = [];
  txt.split(/\r?\n/).forEach((l, i) => { if (/(SERVICE|SVC\.|fetch\(|/api\/|-api-request|getSustainability|loadSustainability|apiPost|apiGet)/.test(l)) hits.push(String(i + 1).padStart(4) + '| ' + l.trim()); });
  console.log(hits.length ? hits.join('\n') : '(no API calls — stub)');
} else { console.log('\nMISSING frontend/sustainability.html'); }

// 6. who links to sustainability.html (nav) + the marketplace auth helper we'll mirror (getCurrentFarmer)
console.log('\n=== nav links to sustainability.html ===');
function scan3(dir) {
  if (!fs.existsSync(dir)) return;
  for (const f of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, f.name);
    if (f.isDirectory()) { if (f.name !== 'node_modules') scan3(full); }
    else if (f.name.endsWith('.html') || f.name.endsWith('.js')) {
      const txt = fs.readFileSync(full, 'utf8');
      if (/sustainability\.html/.test(txt)) {
        txt.split(/\r?\n/).forEach((l, i) => { if (/sustainability\.html/.test(l)) console.log(full.replace(root + '\\', '') + ':' + (i + 1) + (l.trim())); });
      }
    }
  }
}
scan3(path.join(root, 'frontend'));
