import { test, expect, type ConsoleMessage } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const SHOTS = path.resolve(__dirname, 'screenshots')

function attachConsoleCapture(messages: ConsoleMessage[], errors: string[]) {
  return (page: import('@playwright/test').Page) => {
    page.on('console', (msg) => {
      messages.push(msg)
      if (msg.type() === 'error') errors.push(`[console.error] ${msg.text()}`)
    })
    page.on('pageerror', (err) => errors.push(`[pageerror] ${err.message}`))
    page.on('requestfailed', (req) => {
      const failure = req.failure()
      // Don't fail on Google Fonts hiccups in headless mode.
      if (req.url().includes('fonts.googleapis.com') || req.url().includes('fonts.gstatic.com')) return
      errors.push(`[requestfailed] ${req.url()} — ${failure?.errorText}`)
    })
  }
}

test('full UI walkthrough — screenshot every tab', async ({ page }) => {
  const messages: ConsoleMessage[] = []
  const errors: string[] = []
  attachConsoleCapture(messages, errors)(page)

  await page.goto('/')
  // Wait for the sidebar to render — it's the most stable anchor.
  await expect(page.getByText('Better Call Ron')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Live Transcripts' })).toBeVisible()

  // Live Transcripts (default tab)
  await expect(page.getByRole('heading', { name: 'No call selected' })).toBeVisible()
  await page.screenshot({ path: path.join(SHOTS, '01-live.png'), fullPage: true })

  // History
  await page.getByRole('button', { name: 'History' }).click()
  await expect(page.getByRole('heading', { name: 'History' })).toBeVisible()
  // Wait for at least one row OR the empty-state text.
  await page.waitForFunction(
    () =>
      !document.body.textContent?.includes('Loading…') ||
      document.querySelectorAll('tbody tr').length > 0,
  )
  await page.screenshot({ path: path.join(SHOTS, '02-history.png'), fullPage: true })

  // Try expanding the first row.
  const firstRow = page.locator('tbody tr').first()
  if (await firstRow.count()) {
    await firstRow.click()
    // Wait for "Loading call detail…" to either appear or skip past.
    await page.waitForTimeout(500)
    await page.screenshot({ path: path.join(SHOTS, '03-history-expanded.png'), fullPage: true })
  }

  // Users
  await page.getByRole('button', { name: 'Users', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Users' })).toBeVisible()
  await page.waitForFunction(
    () =>
      !document.body.textContent?.includes('Loading…') ||
      document.querySelectorAll('tbody tr').length > 0,
  )
  await page.screenshot({ path: path.join(SHOTS, '04-users.png'), fullPage: true })

  // Lawyers
  await page.getByRole('button', { name: 'Lawyers', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Lawyers' })).toBeVisible()
  await page.waitForFunction(
    () =>
      !document.body.textContent?.includes('Loading…') ||
      document.querySelectorAll('tbody tr').length > 0,
  )
  await page.screenshot({ path: path.join(SHOTS, '05-lawyers.png'), fullPage: true })

  // Filter chip on History — switch to History tab again and click "Urgent".
  await page.getByRole('button', { name: 'History' }).click()
  await page.getByRole('button', { name: 'Urgent', exact: true }).click()
  await page.waitForTimeout(300)
  await page.screenshot({ path: path.join(SHOTS, '06-history-filtered-urgent.png'), fullPage: true })

  // Live Transcripts filter
  await page.getByRole('button', { name: 'Live Transcripts' }).click()
  await page.waitForTimeout(300)
  await page.screenshot({ path: path.join(SHOTS, '07-live-filter-default.png'), fullPage: true })

  // Report any captured errors.
  if (errors.length) {
    throw new Error(`Console / page / network errors:\n${errors.join('\n')}`)
  }
})

test('narrow viewport — layout survives squeeze', async ({ page }) => {
  // Simulates the user's zoomed-in case where the right pane was being
  // squeezed and "No call selected" got clipped.
  await page.setViewportSize({ width: 800, height: 700 })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'No call selected' })).toBeVisible()
  await page.screenshot({ path: path.join(SHOTS, 'narrow-01-live.png'), fullPage: true })

  await page.getByRole('button', { name: 'History' }).click()
  await page.waitForFunction(
    () =>
      !document.body.textContent?.includes('Loading…') ||
      document.querySelectorAll('tbody tr').length > 0,
  )
  await page.screenshot({ path: path.join(SHOTS, 'narrow-02-history.png'), fullPage: true })

  await page.getByRole('button', { name: 'Lawyers', exact: true }).click()
  await page.waitForFunction(
    () =>
      !document.body.textContent?.includes('Loading…') ||
      document.querySelectorAll('tbody tr').length > 0,
  )
  await page.screenshot({ path: path.join(SHOTS, 'narrow-03-lawyers.png'), fullPage: true })
})
