import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import {
  analyzeBfi,
  inspectBfi,
  inspectGoogleForms,
  robustnessGender,
  sampleSchemaBfi,
} from './test/fixtures'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const fetchMock = vi.fn<typeof fetch>()

/** Answer like the API. The analysis is always the bfi one: these tests check the flow and
 *  what is sent, not the statistics. */
function api(inspect = inspectGoogleForms) {
  fetchMock.mockImplementation(async (input) => {
    const url = String(input)
    if (url.endsWith('/api/health')) return json({ status: 'ok', version: '0.1.0' })
    if (url.endsWith('/api/sample')) {
      return json({ filename: 'bfi.csv', csv: 'id,A1\n61617,2\n', schema: sampleSchemaBfi })
    }
    if (url.endsWith('/api/inspect')) return json(inspect)
    if (url.endsWith('/api/analyze')) return json(analyzeBfi)
    if (url.endsWith('/api/robustness')) return json(robustnessGender)
    return json({ code: 'not_found', message: 'Not found.' }, 404)
  })
}

/** The schema sent with the last /api/analyze request. */
function sentSchema() {
  const call = fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/api/analyze')).at(-1)
  const body = call?.[1]?.body as FormData
  return JSON.parse(String(body.get('schema')))
}

// The Results and Robustness screens load on demand; the first load can take a moment.
const LAZY = { timeout: 5000 }

const progress = () => screen.getByRole('navigation', { name: 'Progress' })

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('scrollTo', vi.fn())
  api()
})

afterEach(() => {
  fetchMock.mockReset()
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('goes from an upload with text labels to the results', async () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Upload your survey' }))

    const file = new File(['x'], 'google_forms_sample.csv', { type: 'text/csv' })
    fireEvent.change(screen.getByLabelText('Choose a file'), { target: { files: [file] } })
    fireEvent.click(await screen.findByRole('button', { name: 'Check answer labels' }))

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Check the answer labels')
    const select = screen.getByRole('combobox', { name: 'Number for “Strongly agre”' })
    fireEvent.change(select, { target: { value: '5' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm labels' }))

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Build your scales')
    expect(within(progress()).getByRole('button', { name: '1 Upload (completed)' })).toBeVisible()
    expect(within(progress()).getByRole('button', { name: '2 Labels (completed)' })).toBeVisible()
    expect(screen.getByLabelText('Lowest answer')).toHaveValue('1')
    expect(screen.getByLabelText('Highest answer')).toHaveValue('5')

    fireEvent.click(screen.getByRole('button', { name: 'Add a scale' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Name of scale 1' }), {
      target: { value: 'Teamwork' },
    })
    for (const code of ['Q1', 'Q2', 'Q3', 'Q4']) {
      const scale = screen.getByRole('combobox', { name: `Scale for ${code}` })
      fireEvent.change(scale, { target: { value: (scale as HTMLSelectElement).options[1].value } })
    }
    fireEvent.click(screen.getByRole('checkbox', { name: 'Q2 is reverse-worded' }))
    fireEvent.click(screen.getByRole('button', { name: 'Run checks' }))

    expect(
      await screen.findByText('Review before drawing conclusions', {}, LAZY),
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Review before drawing conclusions',
    )
    const schema = sentSchema()
    expect(schema.scales).toEqual({ Teamwork: ['Q1', 'Q2', 'Q3', 'Q4'] })
    expect(schema.reverse_items).toEqual(['Q2'])
    expect(schema.label_map['Strongly agre']).toBe(5)
    expect(schema.question_text.Q2).toBe('I prefer to work alone.')
    expect(within(progress()).getByText('4 Results', { selector: '[aria-current="step"]' }))
  })

  it('runs the sample data with its own scales', async () => {
    api(inspectBfi)
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Try with sample data' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Continue to scales' }))

    expect(screen.getByText('Sample scales filled in')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Run checks' }))
    expect(
      await screen.findByText('Review before drawing conclusions', {}, LAZY),
    ).toBeInTheDocument()
    expect(sentSchema()).toEqual({ ...sampleSchemaBfi, label_map: null })
  })

  it('clears the results when the scales change', async () => {
    api(inspectBfi)
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Try with sample data' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Continue to scales' }))
    fireEvent.click(screen.getByRole('button', { name: 'Run checks' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Change scales' }, LAZY))

    expect(within(progress()).getByRole('button', { name: '4 Results' })).toBeVisible()
    fireEvent.click(screen.getByRole('checkbox', { name: 'A1 is reverse-worded' }))
    expect(within(progress()).queryByRole('button', { name: '4 Results' })).not.toBeInTheDocument()
  })

  it("shows the API's message when the checks cannot run", async () => {
    api(inspectBfi)
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Try with sample data' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Continue to scales' }))
    fetchMock.mockImplementation(async (input) =>
      String(input).endsWith('/api/health')
        ? json({ status: 'ok', version: '0.1.0' })
        : json(
            {
              code: 'data_mismatch',
              message: 'These columns are in the schema but not in the CSV: A1.',
            },
            400,
          ),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Run checks' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The checks could not run')
    expect(alert).toHaveTextContent('These columns are in the schema but not in the CSV: A1.')
  })

  it('checks robustness and shows the updated verdict on the results', async () => {
    api(inspectBfi)
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Try with sample data' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Continue to scales' }))
    fireEvent.click(screen.getByRole('button', { name: 'Run checks' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Check robustness' }, LAZY))

    expect(await screen.findByRole('heading', { name: 'Check robustness' }, LAZY)).toBeVisible()
    fireEvent.change(screen.getByLabelText('Column that defines the groups'), {
      target: { value: 'gender' },
    })
    fireEvent.change(screen.getByLabelText('Group A'), { target: { value: '1' } })
    fireEvent.change(screen.getByLabelText('Group B'), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Run robustness check' }))
    expect(await screen.findByText(robustnessGender.robustness.sentence)).toBeInTheDocument()

    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/api/robustness'))
    const body = call?.[1]?.body as FormData
    expect(JSON.parse(String(body.get('analysis')))).toEqual(robustnessGender.robustness.analysis)
    expect(JSON.parse(String(body.get('schema')))).toEqual({ ...sampleSchemaBfi, label_map: null })
    expect(within(progress()).getByText('5 Robustness', { selector: '[aria-current="step"]' }))

    fireEvent.click(screen.getByRole('button', { name: 'Back to results' }))
    const chips = within(await screen.findByRole('list', { name: 'Checks' }, LAZY)).getAllByRole(
      'listitem',
    )
    expect(chips[3]).toHaveTextContent('RobustnessNo concern')
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
