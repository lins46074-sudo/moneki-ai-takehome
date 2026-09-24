/**
 * 看板截图与布局体检工具（开发用，不参与构建）。
 *
 * 用 Chrome 的 DevTools 协议驱动无头浏览器：既能按区域截图看排版，
 * 也能直接在页面上量出实际像素，省得靠眼睛估。
 *
 *   node tools/shoot.mjs http://127.0.0.1:8000 out/ --theme dark
 *   node tools/shoot.mjs --probe          # 只打印体检数据，不截图
 */
import { spawn } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import path from 'node:path'

const CHROME_CANDIDATES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/usr/bin/google-chrome',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
]

const args = process.argv.slice(2)
const probeOnly = args.includes('--probe')
const themeIndex = args.indexOf('--theme')
const theme = themeIndex >= 0 ? args[themeIndex + 1] : 'light'
const positional = args.filter((item, index) => !item.startsWith('--') && args[index - 1] !== '--theme')
const url = positional[0] || 'http://127.0.0.1:8000'
const outDir = path.resolve(positional[1] || 'shots')
const PORT = 9333

const browser = CHROME_CANDIDATES.find((candidate) => existsSync(candidate))
if (!browser) {
  console.error('找不到 Chrome 或 Edge，无法截图')
  process.exit(1)
}

const child = spawn(
  browser,
  [
    '--headless=new',
    '--disable-gpu',
    '--hide-scrollbars',
    `--remote-debugging-port=${PORT}`,
    '--user-data-dir=' + path.join(process.env.TEMP || '/tmp', 'moneki-shoot'),
    '--window-size=1440,1200',
    'about:blank',
  ],
  { stdio: 'ignore' },
)

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

async function targetUrl() {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      const list = await fetch(`http://127.0.0.1:${PORT}/json/list`).then((r) => r.json())
      const page = list.find((item) => item.type === 'page')
      if (page?.webSocketDebuggerUrl) return page.webSocketDebuggerUrl
    } catch (error) {
      /* 浏览器还没起来，继续等 */
    }
    await sleep(250)
  }
  throw new Error('连不上无头浏览器')
}

function connect(socketUrl) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(socketUrl)
    const pending = new Map()
    let nextId = 1
    socket.addEventListener('message', (event) => {
      const payload = JSON.parse(event.data)
      const waiter = pending.get(payload.id)
      if (!waiter) return
      pending.delete(payload.id)
      if (payload.error) waiter.reject(new Error(payload.error.message))
      else waiter.resolve(payload.result)
    })
    socket.addEventListener('error', reject)
    socket.addEventListener('open', () =>
      resolve({
        send(method, params = {}) {
          const id = nextId++
          socket.send(JSON.stringify({ id, method, params }))
          return new Promise((res, rej) => pending.set(id, { resolve: res, reject: rej }))
        },
        close: () => socket.close(),
      }),
    )
  })
}

/** 在页面里跑一段表达式，拿回 JSON 结果。 */
async function evaluate(client, expression) {
  const result = await client.send('Runtime.evaluate', {
    expression,
    returnByValue: true,
    awaitPromise: true,
  })
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.exception?.description || '页面内执行出错')
  }
  return result.result.value
}

const PROBE = `(() => {
  const width = (el) => el ? Math.round(el.getBoundingClientRect().width) : 0;
  const bars = [...document.querySelectorAll('.reason')].map((row) => ({
    name: row.querySelector('.name').textContent.trim(),
    count: Number(row.querySelector('.count').textContent.replace(/[^0-9]/g, '')),
    bar: width(row.querySelector('.bar > i')),
  }));
  // 溢出报告要能直接定位到人：给出选择器路径、实际尺寸与一小段文本
  const describe = (el) => {
    const path = [];
    for (let node = el; node && node !== document.body; node = node.parentElement) {
      let name = node.tagName.toLowerCase();
      if (node.id) name += '#' + node.id;
      else if (node.classList.length) name += '.' + [...node.classList].join('.');
      path.unshift(name);
    }
    return {
      selector: path.join(' > '),
      width: el.clientWidth,
      scrollWidth: el.scrollWidth,
      text: (el.textContent || '').trim().slice(0, 40),
    };
  };
  const overflow = [...document.querySelectorAll('body *')]
    .filter((el) => el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflowX === 'visible')
    .slice(0, 6)
    .map(describe);
  return {
    theme: document.documentElement.dataset.theme,
    heroFontSize: getComputedStyle(document.querySelector('.tile.hero .value')).fontSize,
    tiles: [...document.querySelectorAll('.tile')].map((el) => ({
      label: el.querySelector('.label').textContent.trim(),
      value: el.querySelector('.value').textContent.trim(),
      width: width(el),
    })),
    bars,
    charts: [...document.querySelectorAll('canvas')].map((el) => ({ w: el.width, h: el.height })),
    overflow,
    bodyScrollX: document.documentElement.scrollWidth > window.innerWidth,
  };
})()`

async function main() {
  const client = await connect(await targetUrl())
  await client.send('Page.enable')
  await client.send('Runtime.enable')
  const heightIndex = args.indexOf('--height')
  const viewportHeight = heightIndex >= 0 ? Number(args[heightIndex + 1]) : 1200
  await client.send('Emulation.setDeviceMetricsOverride', {
    width: 1440,
    height: viewportHeight,
    deviceScaleFactor: 1,
    mobile: false,
  })
  // 主题要在页面脚本之前写进 localStorage：应用启动时读它定主题，
  // 加载完再改会留下上一帧的残留（而且会被持久化到下一次运行）。
  await client.send('Page.addScriptToEvaluateOnNewDocument', {
    source: `try { localStorage.setItem('moneki-theme', ${JSON.stringify(theme)}) } catch (e) {}`,
  })
  await client.send('Page.navigate', { url })
  await sleep(2500)

  // --click 选择器，可以给多次：按顺序点，用来截「表」「依据展开」这类要交互才出现的状态
  for (let index = 0; index < args.length; index += 1) {
    if (args[index] !== '--click') continue
    const selector = args[index + 1]
    await evaluate(
      client,
      `(() => {
         const el = document.querySelector(${JSON.stringify(selector)});
         if (!el) throw new Error('找不到元素：' + ${JSON.stringify(selector)});
         el.click();
         return true;
       })()`,
    )
    await sleep(700)
  }

  const report = await evaluate(client, PROBE)
  if (report.theme !== theme) {
    throw new Error(`主题没生效：期望 ${theme}，页面是 ${report.theme}`)
  }
  if (report.bodyScrollX) {
    throw new Error('页面出现横向滚动条，布局溢出了')
  }
  if (report.overflow.length) {
    const lines = report.overflow.map(
      (item) => `  ${item.selector}（可见宽 ${item.width}，内容宽 ${item.scrollWidth}）：${item.text}`,
    )
    throw new Error(`有元素内容溢出：\n${lines.join('\n')}`)
  }
  console.log(JSON.stringify(report, null, 2))

  if (!probeOnly) {
    await mkdir(outDir, { recursive: true })
    const metrics = await client.send('Page.getLayoutMetrics')
    const full = metrics.cssContentSize
    // 截图整页；--card 截某一块，--clip x,y,w,h 截精确像素区域，都放大看细节
    const hasCard = args.includes('--card')
    const hasClip = args.includes('--clip')
    const scaleIndex = args.indexOf('--scale')
    const customScale = scaleIndex >= 0 ? Number(args[scaleIndex + 1]) : null
    let clip
    if (hasClip) {
      const [x, y, width, height] = args[args.indexOf('--clip') + 1].split(',').map(Number)
      clip = { x, y, width, height }
    } else if (hasCard) {
      const selector = args[args.indexOf('--card') + 1]
      clip = await evaluate(
        client,
        `(() => {
           const box = document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();
           return { x: box.left + window.scrollX, y: box.top + window.scrollY, width: box.width, height: box.height };
         })()`,
      )
    } else {
      clip = { x: 0, y: 0, width: full.width, height: full.height }
    }
    const scale = customScale ?? (hasCard || hasClip ? 2 : 1)
    const shot = await client.send('Page.captureScreenshot', {
      format: 'png',
      captureBeyondViewport: true,
      clip: { ...clip, scale },
    })
    const suffix = hasClip ? 'clip' : hasCard ? 'card' : 'dashboard'
    const file = path.join(outDir, `${suffix}-${theme}.png`)
    await writeFile(file, Buffer.from(shot.data, 'base64'))
    console.log(
      `已保存 ${file}（${Math.round(clip.width)}×${Math.round(clip.height)} ×${scale}）`,
    )
  }

  client.close()
  child.kill()
}

main().catch((error) => {
  console.error(error.message)
  child.kill()
  process.exit(1)
})
