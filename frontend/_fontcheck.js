'use strict';
const fs = require('fs');
for (const f of ['workers.html', 'index.html', 'weather.html', 'news.html', 'marketplace.html', 'schemes.html', 'techniques.html', 'crop-health.html', 'expert.html', 'livestock.html']) {
  const p = 'frontend/' + f;
  if (!fs.existsSync(p)) { console.log(f, 'MISSING'); continue; }
  const h = fs.readFileSync(p, 'utf8');
  const fonts = [...h.matchAll(/fonts\.googleapis\.com\/css2[^"' )]*/g)].map(m => m[0]);
  const ff = [...h.matchAll(/font-family:\s*([^;}]+)/g)].slice(0, 3).map(m => '  ' + m[1].trim());
  console.log('\n== ' + f + ' ==');
  console.log('  fonts link:', fonts.length ? fonts.join(' ') : 'none');
  ff.forEach(l => console.log(l));
}