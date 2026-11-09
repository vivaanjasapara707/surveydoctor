import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, errorMessage, inspectFile, waitForServer } from './client'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const fetchMock = vi.fn<typeof fetch>()

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  fetchMock.mockReset()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('errors', () => {
  it("uses the API's code and message", async () => {
    const message =
      "This looks like an Excel workbook, not a CSV file. In Excel choose File > Save As > 'CSV UTF-8'."
    fetchMock.mockResolvedValue(json({ code: 'not_csv', message }, 400))
    const error = await inspectFile(new File(['x'], 'a.xlsx')).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ code: 'not_csv', status: 400, message })
  })

  it('explains an error response that is not from the API', async () => {
    fetchMock.mockResolvedValue(new Response('<html>Bad gateway</html>', { status: 502 }))
    const error = await inspectFile(new File(['x'], 'a.csv')).catch((e: unknown) => e)
    expect(errorMessage(error)).toBe(
      'The analysis server answered with an error (502). Try again; if it keeps happening, the ' +
        'server may be down.',
    )
  })

  it('explains a failed connection', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const error = await inspectFile(new File(['x'], 'a.csv')).catch((e: unknown) => e)
    expect(error).toMatchObject({ code: 'network_error', status: null })
    expect(errorMessage(error)).toMatch(/^Could not reach the analysis server/)
  })

  it('sends the file as multipart form data', async () => {
    fetchMock.mockResolvedValue(json({}))
    const file = new File(['A1,A2\n1,2\n'], 'survey.csv', { type: 'text/csv' })
    await inspectFile(file)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/api/inspect')
    expect(init?.method).toBe('POST')
    expect((init?.body as FormData).get('file')).toBeInstanceOf(File)
  })
})

describe('waitForServer', () => {
  it('retries while the server starts and says so after 3 seconds', async () => {
    vi.useFakeTimers()
    fetchMock
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(new Response('', { status: 503 }))
      .mockResolvedValueOnce(json({ status: 'ok', version: '0.1.0' }))
    const onSlow = vi.fn()
    const done = waitForServer({ onSlow })

    await vi.advanceTimersByTimeAsync(2999)
    expect(onSlow).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(2000)
    await done
    expect(onSlow).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('does not report slowness when the server answers at once', async () => {
    vi.useFakeTimers()
    fetchMock.mockResolvedValue(json({ status: 'ok', version: '0.1.0' }))
    const onSlow = vi.fn()
    await waitForServer({ onSlow })
    await vi.advanceTimersByTimeAsync(10_000)
    expect(onSlow).not.toHaveBeenCalled()
  })

  it('gives up after the time limit', async () => {
    vi.useFakeTimers()
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const outcome = expect(waitForServer({ timeoutMs: 10_000 })).rejects.toMatchObject({
      code: 'server_unreachable',
    })
    await vi.advanceTimersByTimeAsync(12_000)
    await outcome
  })

  it('does not retry an error that waiting cannot fix', async () => {
    fetchMock.mockResolvedValue(json({ code: 'not_found', message: 'Not found.' }, 404))
    await expect(waitForServer()).rejects.toMatchObject({ code: 'not_found' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
