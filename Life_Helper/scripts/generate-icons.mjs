// Pure-Node icon generator: no native deps (sharp's win32 binding fails to
// load in this environment), so we rasterize by hand and encode PNG via
// zlib from the standard library only.
import { deflateSync } from 'node:zlib'
import { writeFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const outDir = path.join(__dirname, '..', 'public')
mkdirSync(outDir, { recursive: true })

const BG = [20, 18, 33, 255] // #141221 canvas
const FG = [124, 92, 255, 255] // #7c5cff card
const GLYPH = [20, 18, 33, 255] // dark glyph on card

// 'L' then gap then 'H', 12 rows tall.
const L = [
  '#....',
  '#....',
  '#....',
  '#....',
  '#....',
  '#....',
  '#....',
  '#....',
  '#....',
  '#....',
  '#....',
  '#####',
]
const H = [
  '#.....#',
  '#.....#',
  '#.....#',
  '#.....#',
  '#.....#',
  '#######',
  '#######',
  '#.....#',
  '#.....#',
  '#.....#',
  '#.....#',
  '#.....#',
]
const GAP = 2
const glyphRows = L.length
const glyphCols = L[0].length + GAP + H[0].length
function glyphAt(row, col) {
  if (col < L[0].length) return L[row][col] === '#'
  const hCol = col - L[0].length - GAP
  if (hCol < 0) return false
  return H[row][hCol] === '#'
}

function setPixel(buf, size, x, y, [r, g, b, a]) {
  if (x < 0 || y < 0 || x >= size || y >= size) return
  const i = (y * size + x) * 4
  buf[i] = r
  buf[i + 1] = g
  buf[i + 2] = b
  buf[i + 3] = a
}

function drawRoundedSquare(buf, size, inset, radius, color) {
  const x0 = inset
  const y0 = inset
  const x1 = size - inset
  const y1 = size - inset
  for (let y = y0; y < y1; y++) {
    for (let x = x0; x < x1; x++) {
      const inCornerBox =
        (x < x0 + radius && y < y0 + radius) ||
        (x >= x1 - radius && y < y0 + radius) ||
        (x < x0 + radius && y >= y1 - radius) ||
        (x >= x1 - radius && y >= y1 - radius)
      if (inCornerBox) {
        const cx = x < x0 + radius ? x0 + radius : x1 - radius
        const cy = y < y0 + radius ? y0 + radius : y1 - radius
        const dx = x - cx + 0.5
        const dy = y - cy + 0.5
        if (dx * dx + dy * dy > radius * radius) continue
      }
      setPixel(buf, size, x, y, color)
    }
  }
}

function drawGlyph(buf, size, boxSize, color) {
  const scale = Math.floor(boxSize / glyphCols)
  const glyphW = scale * glyphCols
  const glyphH = scale * glyphRows
  const startX = Math.floor((size - glyphW) / 2)
  const startY = Math.floor((size - glyphH) / 2)
  for (let row = 0; row < glyphRows; row++) {
    for (let col = 0; col < glyphCols; col++) {
      if (!glyphAt(row, col)) continue
      for (let dy = 0; dy < scale; dy++) {
        for (let dx = 0; dx < scale; dx++) {
          setPixel(buf, size, startX + col * scale + dx, startY + row * scale + dy, color)
        }
      }
    }
  }
}

function renderIcon(size, { maskable }) {
  const buf = Buffer.alloc(size * size * 4)
  for (let i = 0; i < buf.length; i += 4) {
    buf[i] = BG[0]
    buf[i + 1] = BG[1]
    buf[i + 2] = BG[2]
    buf[i + 3] = BG[3]
  }
  const inset = maskable ? Math.round(size * 0.02) : Math.round(size * 0.08)
  const radius = maskable ? Math.round(size * 0.18) : Math.round(size * 0.22)
  drawRoundedSquare(buf, size, inset, radius, FG)
  // Maskable safe zone is the inner 80%; keep the glyph well inside it.
  const glyphBox = maskable ? size * 0.42 : size * 0.6
  drawGlyph(buf, size, glyphBox, GLYPH)
  return buf
}

// --- Minimal PNG encoder (8-bit RGBA, filter type 0, single IDAT) ---
const CRC_TABLE = (() => {
  const table = new Uint32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    }
    table[n] = c >>> 0
  }
  return table
})()

function crc32(buf) {
  let c = 0xffffffff
  for (let i = 0; i < buf.length; i++) {
    c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8)
  }
  return (c ^ 0xffffffff) >>> 0
}

function chunk(type, data) {
  const typeBuf = Buffer.from(type, 'ascii')
  const lenBuf = Buffer.alloc(4)
  lenBuf.writeUInt32BE(data.length, 0)
  const crcBuf = Buffer.alloc(4)
  crcBuf.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])), 0)
  return Buffer.concat([lenBuf, typeBuf, data, crcBuf])
}

function encodePng(rgba, size) {
  const raw = Buffer.alloc(size * (1 + size * 4))
  for (let y = 0; y < size; y++) {
    const rowStart = y * (1 + size * 4)
    raw[rowStart] = 0 // filter: none
    rgba.copy(raw, rowStart + 1, y * size * 4, (y + 1) * size * 4)
  }
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(size, 0)
  ihdr.writeUInt32BE(size, 4)
  ihdr[8] = 8 // bit depth
  ihdr[9] = 6 // color type: RGBA
  ihdr[10] = 0
  ihdr[11] = 0
  ihdr[12] = 0
  const idat = deflateSync(raw)
  const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])
  return Buffer.concat([
    signature,
    chunk('IHDR', ihdr),
    chunk('IDAT', idat),
    chunk('IEND', Buffer.alloc(0)),
  ])
}

const targets = [
  { name: 'pwa-192x192.png', size: 192, maskable: false },
  { name: 'pwa-512x512.png', size: 512, maskable: false },
  { name: 'maskable-icon-512x512.png', size: 512, maskable: true },
  { name: 'apple-touch-icon-180x180.png', size: 180, maskable: false },
  { name: 'favicon-32x32.png', size: 32, maskable: false },
]

for (const t of targets) {
  const buf = renderIcon(t.size, { maskable: t.maskable })
  const png = encodePng(buf, t.size)
  writeFileSync(path.join(outDir, t.name), png)
  console.log(`wrote ${t.name} (${png.length} bytes)`)
}
