/*
  Script: check-commandbar-layout.js
  Purpose: Start Next.js dev server, open /chat with Puppeteer, and verify CommandBar layout.
  Checks:
  - Left and right control clusters share the same offsetParent (outer rounded container)
  - Their bottom baselines match across multiple viewport widths
  - With and without an interim text overlay
  - The input’s content area does not overlap with the left controls (vertical separation test)
*/

const { spawn } = require('child_process');
const http = require('http');
const puppeteer = require('puppeteer');

const FRONTEND_DIR = __dirname.replace(/\/scripts$/, '');
const PORT = 3030;
const URL = `http://localhost:${PORT}/chat`;

function waitForServerReady(url, timeoutMs = 120000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const req = http.get(url, (res) => {
        // Any non-5xx response indicates the server is up enough to render
        if (res.statusCode && res.statusCode < 500) {
          resolve();
        } else {
          if (Date.now() - start > timeoutMs) {
            reject(new Error(`Timeout waiting for server: ${res.statusCode}`));
          } else {
            setTimeout(attempt, 1000);
          }
        }
      });
      req.on('error', () => {
        if (Date.now() - start > timeoutMs) {
          reject(new Error('Timeout waiting for server (connection error)'));
        } else {
          setTimeout(attempt, 1000);
        }
      });
    };
    attempt();
  });
}

async function runChecks() {
  const server = spawn('npm', ['run', 'dev', '--', '-p', String(PORT)], {
    cwd: FRONTEND_DIR,
    env: { ...process.env, NODE_ENV: 'development' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  let serverLogs = '';
  server.stdout.on('data', (d) => { serverLogs += d.toString(); });
  server.stderr.on('data', (d) => { serverLogs += d.toString(); });

  let browser;
  try {
    await waitForServerReady(URL);
    browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox','--disable-setuid-sandbox'] });
    const page = await browser.newPage();

    const widths = [375, 768, 1024, 1440];
    const results = [];

    for (const w of widths) {
      await page.setViewport({ width: w, height: 900, deviceScaleFactor: 1 });
      await page.goto(URL, { waitUntil: 'domcontentloaded' });
      // Give Tailwind/Next hydration a moment
      await new Promise((r) => setTimeout(r, 1500));

      const runOne = async (injectInterim = false) => {
        return await page.evaluate((injectInterimInner) => {
          const findLeft = () => document.querySelector('div.pointer-events-auto.absolute.bottom-2.left-2');
          const findRight = () => document.querySelector('div.pointer-events-auto.absolute.bottom-2.right-2');
          const left = findLeft();
          const right = findRight();
          if (!left || !right) {
            return { error: 'Control clusters not found' };
          }

          // Find the outer rounded container (offsetParent)
          const container = left.offsetParent;
          const rightParent = right.offsetParent;

          // Optional: inject a simulated interimText overlay into the input wrapper
          if (injectInterimInner) {
            try {
              const input = document.querySelector('form input[placeholder*="Ask anything"]');
              if (input) {
                const wrapper = input.parentElement; // .flex-1.relative.pr-16.pl-16
                if (wrapper && wrapper.className.includes('relative')) {
                  const probe = document.createElement('div');
                  probe.textContent = 'Listening… interim sample';
                  probe.setAttribute('data-probe', 'interim');
                  probe.className = 'absolute inset-y-0 right-0 flex items-center text-xs text-muted-foreground/60 pointer-events-none';
                  wrapper.appendChild(probe);
                }
              }
            } catch {}
          } else {
            // Remove any previous probe
            const probe = document.querySelector('[data-probe="interim"]');
            if (probe && probe.parentElement) probe.parentElement.removeChild(probe);
          }

          const lbox = left.getBoundingClientRect();
          const rbox = right.getBoundingClientRect();
          const sameParent = container && container === rightParent;

          // Baseline (bottom) alignment check
          const baselineDiff = Math.abs(lbox.bottom - rbox.bottom);

          // Vertical separation: ensure controls sit within the input’s bottom padding area, not overlapping content
          const inputEl = document.querySelector('form input[placeholder*="Ask anything"]');
          let verticalSeparationOK = null;
          let paddingLeftPx = null;
          let leftClusterWidth = null;
          if (inputEl) {
            const st = window.getComputedStyle(inputEl);
            const inputRect = inputEl.getBoundingClientRect();
            const padBottom = parseFloat(st.paddingBottom || '0') || 0;
            const contentBottomY = inputRect.bottom - padBottom;
            verticalSeparationOK = lbox.top >= contentBottomY - 1; // top of controls is below content area

            const wrapper = inputEl.parentElement; // has pl-16 / pr-16
            if (wrapper) {
              const wst = window.getComputedStyle(wrapper);
              paddingLeftPx = parseFloat(wst.paddingLeft || '0') || 0;
            }
            leftClusterWidth = lbox.width;
          }

          return {
            sameParent,
            baselineDiff,
            verticalSeparationOK,
            paddingLeftPx,
            leftClusterWidth,
          };
        }, injectInterim);
      };

      const withoutInterim = await runOne(false);
      const withInterim = await runOne(true);

      results.push({ width: w, withoutInterim, withInterim });
    }

    return { ok: true, results, logs: serverLogs };
  } catch (err) {
    return { ok: false, error: String(err), logs: serverLogs };
  } finally {
    try { if (browser) await browser.close(); } catch {}
    try { server.kill('SIGINT'); } catch {}
  }
}

runChecks().then((out) => {
  console.log('COMMAND BAR LAYOUT CHECK RESULT:\n' + JSON.stringify(out, null, 2));
  process.exit(out.ok ? 0 : 1);
});
