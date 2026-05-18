import { chromium } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const OUT = path.resolve(__dirname, '../../assets')
const URL = 'https://better-call-ron-hackathon.vercel.app'

const browser = await chromium.launch()
const ctx = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 2,
})
const page = await ctx.newPage()
await page.goto(URL, { waitUntil: 'networkidle', timeout: 30_000 })
await page.waitForTimeout(800)

// Hero (above the fold).
await page.screenshot({ path: path.join(OUT, 'landing-page-hero.png') })
console.log('Saved hero:', path.join(OUT, 'landing-page-hero.png'))

// Full page (long scrollshot).
await page.screenshot({ path: path.join(OUT, 'landing-page-full.png'), fullPage: true })
console.log('Saved full:', path.join(OUT, 'landing-page-full.png'))

// "Ron runs the room" architecture section — find the heading, scroll its parent
// section into view, then screenshot just that section.
const heading = page.getByRole('heading', { name: /Ron runs the room/i }).first()
await heading.waitFor({ timeout: 10_000 })
const section = heading.locator('xpath=ancestor::section[1]')
await section.scrollIntoViewIfNeeded()
await page.waitForTimeout(400)
await section.screenshot({ path: path.join(OUT, 'landing-page-architecture.png') })
console.log('Saved architecture:', path.join(OUT, 'landing-page-architecture.png'))

await browser.close()
