// Renderiza a abertura quadro a quadro (determinístico) e entrega ao ffmpeg.
// Uso: node render.js [largura] [altura] [fps] [saida.mp4]
//      node render.js --stills 1920 1080 2 5 10 ...   (gera PNGs de conferência)
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');

const args = process.argv.slice(2);
const stills = args[0] === '--stills';
if (stills) args.shift();
const [W = 1920, H = 1080] = args.slice(0, 2).map(Number);
// servidor estático local (módulos ES não carregam via file://)
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.m4a': 'audio/mp4' };
const server = http.createServer((req, res) => {
  const file = path.join(__dirname, decodeURIComponent(new URL(req.url, 'http://x').pathname));
  if (!file.startsWith(__dirname) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream' });
  fs.createReadStream(file).pipe(res);
}).listen(0);
const url = () => `http://127.0.0.1:${server.address().port}/index.html?render=1&w=${W}&h=${H}`;

async function openPage(browser) {
  const page = await browser.newPage({ viewport: { width: W, height: H } });
  page.on('pageerror', e => console.error('erro na página:', e.message));
  await page.goto(url());
  await page.waitForFunction(() => window.ready);
  await page.evaluate(() => window.ready);
  return page;
}
const frame = (page, t) => page.evaluate(t => window.render(t), t)
  .then(() => page.locator('#c').screenshot({ type: 'png' }));

(async () => {
  const browser = await chromium.launch({ args: ['--force-color-profile=srgb', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  if (stills) {
    const page = await openPage(browser);
    fs.mkdirSync(path.join(__dirname, 'stills'), { recursive: true });
    for (const t of args.slice(2).map(Number)) {
      fs.writeFileSync(path.join(__dirname, 'stills', `t${String(t).padStart(5, '0')}.png`), await frame(page, t));
    }
    await browser.close(); return server.close();
  }

  const fps = Number(args[2] || 30), out = args[3] || 'abertura.mp4';
  const dur = 24, total = Math.round(dur * fps);
  const audio = path.join(__dirname, 'trilha.m4a');
  const ff = spawn('ffmpeg', [
    '-y', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'png', '-i', '-',
    ...(fs.existsSync(audio) ? ['-i', audio, '-c:a', 'copy', '-shortest'] : []),
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-tune', 'grain',
    '-pix_fmt', 'yuv420p', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
    '-movflags', '+faststart', path.join(__dirname, out),
  ], { stdio: ['pipe', 'inherit', 'inherit'] });

  // várias abas renderizam em paralelo; os quadros entram em ordem no ffmpeg
  const N = 4, pages = await Promise.all(Array.from({ length: N }, () => openPage(browser)));
  const started = Date.now();
  // se uma aba cair (o WebGL por software cansa depois de centenas de quadros), abre outra e refaz o quadro
  const safeFrame = async (k, t) => {
    for (let tries = 0; ; tries++) {
      try { return await frame(pages[k], t); } catch (e) {
        if (tries >= 3) throw e;
        console.error(`\naba ${k} caiu em t=${t.toFixed(2)}s (${e.message.split('\n')[0]}); reabrindo`);
        await pages[k].close().catch(() => {});
        pages[k] = await openPage(browser);
      }
    }
  };
  for (let i = 0; i < total; i += N) {
    if (i && i % 120 < N) await Promise.all(pages.map(async (p, k) => { await p.close(); pages[k] = await openPage(browser); }));
    const batch = await Promise.all(pages.map((p, k) => i + k < total ? safeFrame(k, (i + k) / fps) : null));
    for (const png of batch) if (png && !ff.stdin.write(png)) await new Promise(r => ff.stdin.once('drain', r));
    if (i % (fps * 2) < N) process.stderr.write(`\rquadro ${i}/${total}  ${((Date.now() - started) / 1000).toFixed(0)}s`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  await browser.close(); server.close();
  console.log(`\npronto: ${out}`);
})().catch(e => { console.error('\nfalhou:', e); process.exit(1); });
