import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { robustnessGender, sampleSchemaBfi } from '../test/fixtures'
import { Downloads } from './Downloads'

const fetchMock = vi.fn<typeof fetch>()
const file = new File(['id,A1\n'], 'bfi.csv', { type: 'text/csv' })
let saved: { name: string; href: string }[] = []

beforeEach(() => {
  saved = []
  vi.stubGlobal('fetch', fetchMock)
  // jsdom has no object URLs and does not download; record what would be saved instead.
  URL.createObjectURL = vi.fn(() => 'blob:test')
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    saved.push({ name: this.download, href: this.href })
  })
})

afterEach(() => {
  fetchMock.mockReset()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function answer(path: string, response: Response) {
  fetchMock.mockImplementation(async (input) =>
    String(input).endsWith('/api/health')
      ? Response.json({ status: 'ok', version: '0.1.0' })
      : String(input).endsWith(path)
        ? response
        : Response.json({ code: 'not_found', message: 'Not found.' }, { status: 404 }),
  )
}

describe('Downloads', () => {
  it('saves the report under the name the API gives, with the robustness analysis', async () => {
    answer(
      '/api/report',
      new Response('<html></html>', {
        headers: { 'Content-Disposition': 'attachment; filename="surveydoctor_report_bfi.html"' },
      }),
    )
    const analysis = robustnessGender.robustness.analysis
    render(<Downloads file={file} schema={sampleSchemaBfi} analysis={analysis} />)
    fireEvent.click(screen.getByRole('button', { name: 'Download report' }))
    expect(screen.getByRole('status')).toHaveTextContent('Preparing the report…')

    await waitFor(() =>
      expect(saved).toEqual([{ name: 'surveydoctor_report_bfi.html', href: 'blob:test' }]),
    )
    const body = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/api/report'))?.[1]
      ?.body as FormData
    expect(JSON.parse(String(body.get('analysis')))).toEqual(analysis)
    expect(JSON.parse(String(body.get('schema')))).toEqual(sampleSchemaBfi)
    expect(screen.getByRole('status')).toBeEmptyDOMElement()
  })

  it('saves the flags CSV', async () => {
    answer(
      '/api/export/flags',
      new Response('respondent,flagged\n', {
        headers: { 'Content-Disposition': 'attachment; filename="surveydoctor_flags_bfi.csv"' },
      }),
    )
    render(<Downloads file={file} schema={sampleSchemaBfi} analysis={null} />)
    fireEvent.click(screen.getByRole('button', { name: 'Download flags (CSV)' }))
    await waitFor(() => expect(saved[0]?.name).toBe('surveydoctor_flags_bfi.csv'))
  })

  it('makes the schema file without asking the server', () => {
    render(<Downloads file={file} schema={sampleSchemaBfi} analysis={null} />)
    fireEvent.click(screen.getByRole('button', { name: 'Download schema (JSON)' }))
    expect(saved).toEqual([{ name: 'surveydoctor_schema.json', href: 'blob:test' }])
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("shows the API's message when a download fails", async () => {
    answer(
      '/api/report',
      Response.json(
        {
          code: 'data_mismatch',
          message: 'These columns are in the schema but not in the CSV: A1.',
        },
        { status: 400 },
      ),
    )
    render(<Downloads file={file} schema={sampleSchemaBfi} analysis={null} />)
    fireEvent.click(screen.getByRole('button', { name: 'Download report' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Could not prepare the report')
    expect(alert).toHaveTextContent('These columns are in the schema but not in the CSV: A1.')
    expect(saved).toEqual([])
  })
})
