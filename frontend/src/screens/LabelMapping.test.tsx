import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { googleFormsLabels, unknownLabels } from '../test/fixtures'
import { LabelMapping } from './LabelMapping'

function setup(props: Partial<Parameters<typeof LabelMapping>[0]> = {}) {
  const handlers = { onConfirm: vi.fn(), onEdit: vi.fn(), onBack: vi.fn() }
  render(<LabelMapping labels={googleFormsLabels} confirmed={null} {...handlers} {...props} />)
  return handlers
}

const numberFor = (label: string) => screen.getByRole('combobox', { name: `Number for “${label}”` })
const confirmButton = () => screen.getByRole('button', { name: 'Confirm labels' })

describe('LabelMapping', () => {
  it('shows the proposed number for every recognised label', () => {
    setup()
    expect(numberFor('strongly disagree')).toHaveValue('1')
    expect(numberFor('neutral')).toHaveValue('3')
    expect(numberFor('strongly agree')).toHaveValue('5')
    expect(screen.getByText('Recognised: agreement labels, 5 points')).toBeInTheDocument()
  })

  it('names the alternative label set', () => {
    setup()
    expect(screen.getByText(/They also match agreement labels, 7 points/)).toBeInTheDocument()
  })

  it('lists the unrecognised label without a number', () => {
    setup()
    const table = screen.getByRole('table', { name: 'Answers that need a number' })
    expect(within(table).getByText('needs a number')).toBeInTheDocument()
    expect(numberFor('Strongly agre')).toHaveValue('')
  })

  it('does not confirm while a label has no number', () => {
    const { onConfirm } = setup()
    fireEvent.click(confirmButton())
    expect(onConfirm).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Choose a number for “Strongly agre”, or mark it as not a rating answer.',
    )
  })

  it('confirms once the unrecognised label is mapped', () => {
    const { onConfirm } = setup()
    fireEvent.change(numberFor('Strongly agre'), { target: { value: '5' } })
    fireEvent.click(confirmButton())
    expect(onConfirm).toHaveBeenCalledWith({
      labelMap: { ...googleFormsLabels.label_map, 'Strongly agre': 5 },
      scaleMin: 1,
      scaleMax: 5,
      notRatings: [],
    })
  })

  it('can mark an unrecognised label as not a rating answer', () => {
    const { onConfirm } = setup()
    fireEvent.change(numberFor('Strongly agre'), { target: { value: 'missing' } })
    fireEvent.click(confirmButton())
    const choice = onConfirm.mock.calls[0][0]
    expect(choice.notRatings).toEqual(['Strongly agre'])
    expect(choice.labelMap).not.toHaveProperty('Strongly agre')
  })

  it('lets the user correct a proposed number', () => {
    const { onConfirm } = setup()
    fireEvent.change(numberFor('neutral'), { target: { value: '2' } })
    fireEvent.change(numberFor('Strongly agre'), { target: { value: '5' } })
    fireEvent.click(confirmButton())
    expect(onConfirm.mock.calls[0][0].labelMap.neutral).toBe(2)
  })

  it('refuses numbers outside a changed scale range', () => {
    const { onConfirm } = setup()
    fireEvent.change(numberFor('Strongly agre'), { target: { value: '5' } })
    fireEvent.change(screen.getByLabelText('Highest answer'), { target: { value: '4' } })
    fireEvent.click(confirmButton())
    expect(onConfirm).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent(
      '“strongly agree” is set to 5, outside the scale range 1–4.',
    )
    expect(numberFor('strongly agree')).toHaveDisplayValue('5 (outside the range)')
  })

  it('offers 1 to 7 when the range is widened for a 7-point form', () => {
    setup()
    fireEvent.change(screen.getByLabelText('Highest answer'), { target: { value: '7' } })
    const options = within(numberFor('agree')).getAllByRole('option')
    expect(options.map((o) => o.textContent)).toEqual(['1', '2', '3', '4', '5', '6', '7'])
  })

  it('shows the confirmation and withdraws it on the next edit', () => {
    const confirmed = {
      labelMap: { ...googleFormsLabels.label_map, 'Strongly agre': 5 },
      scaleMin: 1,
      scaleMax: 5,
      notRatings: [],
    }
    const { onEdit } = setup({ confirmed })
    expect(screen.getByText('Labels confirmed')).toBeInTheDocument()
    expect(numberFor('Strongly agre')).toHaveValue('5')
    fireEvent.change(numberFor('agree'), { target: { value: '3' } })
    expect(onEdit).toHaveBeenCalledTimes(1)
  })

  it('asks for the scale range when the API could not propose one', () => {
    const { onConfirm } = setup({ labels: unknownLabels })
    expect(screen.queryByText(/Recognised:/)).not.toBeInTheDocument()
    fireEvent.click(confirmButton())
    expect(onConfirm).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent(/Enter the lowest and highest answer/)

    fireEvent.change(screen.getByLabelText('Lowest answer'), { target: { value: '0' } })
    fireEvent.change(screen.getByLabelText('Highest answer'), { target: { value: '1' } })
    fireEvent.change(numberFor('Yes'), { target: { value: '1' } })
    fireEvent.change(numberFor('No'), { target: { value: '0' } })
    fireEvent.click(confirmButton())
    expect(onConfirm).toHaveBeenCalledWith({
      labelMap: { No: 0, Yes: 1 },
      scaleMin: 0,
      scaleMax: 1,
      notRatings: [],
    })
  })

  it('goes back to the upload', () => {
    const { onBack } = setup()
    fireEvent.click(screen.getByRole('button', { name: 'Back to upload' }))
    expect(onBack).toHaveBeenCalled()
  })
})
