import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { WAKE_UP_MESSAGE } from '../api/client'
import { inspectGoogleForms } from '../test/fixtures'
import type { LoadStatus, UploadState } from '../lib/upload'
import { Upload } from './Upload'

const upload: UploadState = {
  file: new File(['x'], 'google_forms_sample.csv'),
  source: 'upload',
  inspect: inspectGoogleForms,
  sampleSchema: null,
}

function setup(status: LoadStatus, state: UploadState | null, labelsNeeded = true) {
  const handlers = {
    onFile: vi.fn(),
    onSample: vi.fn(),
    onCheckLabels: vi.fn(),
    onContinue: vi.fn(),
  }
  render(<Upload status={status} upload={state} labelsNeeded={labelsNeeded} {...handlers} />)
  return handlers
}

describe('Upload', () => {
  it('offers a file chooser and the sample data before anything is loaded', () => {
    const { onSample } = setup({ kind: 'idle' }, null)
    expect(screen.getByLabelText('Choose a file')).toHaveAttribute('type', 'file')
    fireEvent.click(screen.getByRole('button', { name: 'Or try the sample data' }))
    expect(onSample).toHaveBeenCalled()
  })

  it('passes a chosen file on', () => {
    const { onFile } = setup({ kind: 'idle' }, null)
    const file = new File(['A1\n1\n'], 'survey.csv', { type: 'text/csv' })
    fireEvent.change(screen.getByLabelText('Choose a file'), { target: { files: [file] } })
    expect(onFile).toHaveBeenCalledWith(file)
  })

  it('passes a dropped file on', () => {
    const { onFile } = setup({ kind: 'idle' }, null)
    const file = new File(['A1\n1\n'], 'survey.csv', { type: 'text/csv' })
    fireEvent.drop(screen.getByText('Drag a CSV file here'), { dataTransfer: { files: [file] } })
    expect(onFile).toHaveBeenCalledWith(file)
  })

  it('shows the wake-up message while the server starts', () => {
    setup({ kind: 'loading', message: 'Sending survey.csv…', waking: true }, null)
    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('Sending survey.csv…')
    expect(status).toHaveTextContent(WAKE_UP_MESSAGE)
    expect(screen.getByLabelText('Choose a file')).toBeDisabled()
  })

  it("shows the API's error message", () => {
    setup(
      { kind: 'error', title: 'Could not read the file', message: 'The file has no rows.' },
      null,
    )
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Could not read the file')
    expect(alert).toHaveTextContent('The file has no rows.')
  })

  it('summarises the upload and names the personal columns left out', () => {
    setup({ kind: 'idle' }, upload)
    expect(screen.getByRole('heading', { name: /Your file: google_forms_sample.csv/ }))
    const figure = (label: string) => screen.getByText(label).nextElementSibling
    expect(figure('Responses')).toHaveTextContent('12')
    expect(figure('Look like rating questions')).toHaveTextContent('7')
    expect(figure('Personal columns left out')).toHaveTextContent('2')
    expect(screen.getByText('Personal information left out')).toBeInTheDocument()
    expect(screen.getByText('Email Address')).toBeInTheDocument()
    expect(screen.getByText('Your name')).toBeInTheDocument()
  })

  it('previews the rows without the personal columns', () => {
    setup({ kind: 'idle' }, upload)
    const preview = screen.getByRole('region', { name: /Preview of the first/ })
    const headers = within(preview)
      .getAllByRole('columnheader')
      .map((h) => h.textContent)
    expect(headers).toContain('Q1I enjoy working in teams.')
    expect(headers.join(' ')).not.toMatch(/Email|name/)
    expect(within(preview).queryByText(/@example\.com/)).not.toBeInTheDocument()
  })

  it('leads to the label step when answers are words', () => {
    const { onCheckLabels } = setup({ kind: 'idle' }, upload)
    fireEvent.click(screen.getByRole('button', { name: 'Check answer labels' }))
    expect(onCheckLabels).toHaveBeenCalled()
  })

  it('goes straight on to the scales when no labels need checking', () => {
    const { onContinue } = setup({ kind: 'idle' }, upload, false)
    expect(screen.getByText('Answers are already numbers')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Check answer labels' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Continue to scales' }))
    expect(onContinue).toHaveBeenCalled()
  })
})
