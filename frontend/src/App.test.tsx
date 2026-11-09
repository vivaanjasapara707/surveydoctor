import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { inspectGoogleForms } from './test/fixtures'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const fetchMock = vi.fn<typeof fetch>()

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('scrollTo', vi.fn())
  fetchMock.mockImplementation(async (input) => {
    const url = String(input)
    if (url.endsWith('/api/health')) return json({ status: 'ok', version: '0.1.0' })
    if (url.endsWith('/api/inspect')) return json(inspectGoogleForms)
    return json({ code: 'not_found', message: 'Not found.' }, 404)
  })
})

afterEach(() => {
  fetchMock.mockReset()
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('goes from upload to confirmed labels', async () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Upload your survey' }))

    const file = new File(['x'], 'google_forms_sample.csv', { type: 'text/csv' })
    fireEvent.change(screen.getByLabelText('Choose a file'), { target: { files: [file] } })
    fireEvent.click(await screen.findByRole('button', { name: 'Check answer labels' }))

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Check the answer labels')
    const select = screen.getByRole('combobox', { name: 'Number for “Strongly agre”' })
    fireEvent.change(select, { target: { value: '5' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm labels' }))
    expect(screen.getByText('Labels confirmed')).toBeInTheDocument()

    const progress = screen.getByRole('navigation', { name: 'Progress' })
    expect(within(progress).getByRole('button', { name: '1 Upload (completed)' })).toBeVisible()
    expect(within(progress).getByText('2 Labels', { selector: '[aria-current="step"]' }))
  })

  it('refuses a file over 10 MB without sending it', () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Upload your survey' }))
    const file = new File(['x'], 'big.csv', { type: 'text/csv' })
    Object.defineProperty(file, 'size', { value: 11 * 1024 * 1024 })
    fireEvent.change(screen.getByLabelText('Choose a file'), { target: { files: [file] } })

    expect(screen.getByRole('alert')).toHaveTextContent('The file is larger than 10 MB.')
    const inspectCalls = fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/inspect'))
    expect(inspectCalls).toHaveLength(0)
  })
})
