import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DcaCompareControls } from './DcaCompareControls'
import { DEFAULT_DCA_PARAMS, DCA_PRESETS, mergeDcaParams } from '@/lib/dcaCompareParams'

function setup(overrides: Partial<React.ComponentProps<typeof DcaCompareControls>> = {}) {
  const props = {
    params: DEFAULT_DCA_PARAMS,
    onChange: vi.fn(),
    onRun: vi.fn(),
    isPending: false,
    ...overrides,
  }
  render(<DcaCompareControls {...props} />)
  return props
}

describe('DcaCompareControls', () => {
  it('hides the parameter fields until the panel is expanded', async () => {
    setup()
    expect(screen.queryByLabelText('Days to top')).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: /tune parameters/i }))
    expect(screen.getByLabelText('Days to top')).toBeInTheDocument()
  })

  it('calls onChange with the edited field value', async () => {
    const { onChange } = setup()
    await userEvent.click(screen.getByRole('button', { name: /tune parameters/i }))
    fireEvent.change(screen.getByLabelText('Days to top'), { target: { value: '600' } })
    expect(onChange).toHaveBeenCalled()
    const last = onChange.mock.calls.at(-1)![0]
    expect(last.cycle.days_to_top).toBe(600)
  })

  it('applies a preset through onChange', async () => {
    const { onChange } = setup()
    await userEvent.click(screen.getByRole('button', { name: /tune parameters/i }))
    await userEvent.selectOptions(screen.getByLabelText(/preset/i), 'sellEverything')
    expect(onChange).toHaveBeenLastCalledWith(DCA_PRESETS.sellEverything)
  })

  it('resets to defaults', async () => {
    const { onChange } = setup({ params: mergeDcaParams({ cycle: { days_to_top: 700 } }) })
    await userEvent.click(screen.getByRole('button', { name: /tune parameters/i }))
    await userEvent.click(screen.getByRole('button', { name: /reset/i }))
    expect(onChange).toHaveBeenLastCalledWith(DEFAULT_DCA_PARAMS)
  })

  it('hides the window day offsets while the gaussian clock is selected', async () => {
    setup()
    await userEvent.click(screen.getByRole('button', { name: /tune parameters/i }))
    expect(screen.getByLabelText(/timing mode/i)).toHaveValue('gaussian')
    expect(screen.queryByLabelText(/start selling/i)).toBeNull()
  })

  it('reveals the day offsets once the timing mode is switched to windows', async () => {
    const { onChange } = setup()
    await userEvent.click(screen.getByRole('button', { name: /tune parameters/i }))
    await userEvent.selectOptions(screen.getByLabelText(/timing mode/i), 'windows')
    expect(onChange.mock.calls.at(-1)![0].cycle.timing_mode).toBe('windows')

    // Re-render in windows mode (the parent owns the state) — now the day fields exist.
    setup({ params: mergeDcaParams({ cycle: { timing_mode: 'windows' } }) })
    await userEvent.click(screen.getAllByRole('button', { name: /tune parameters/i })[1])
    expect(screen.getByLabelText(/start selling/i)).toBeInTheDocument()
  })

  it('sends an empty day offset back as null (auto-derive) instead of NaN', async () => {
    const { onChange } = setup({
      params: mergeDcaParams({ cycle: { timing_mode: 'windows', sell_start_day: 500 } }),
    })
    await userEvent.click(screen.getByRole('button', { name: /tune parameters/i }))
    fireEvent.change(screen.getByLabelText(/start selling/i), { target: { value: '' } })
    expect(onChange.mock.calls.at(-1)![0].cycle.sell_start_day).toBeNull()
  })

  it('fires onRun when the run button is clicked', async () => {
    const { onRun } = setup()
    await userEvent.click(screen.getByRole('button', { name: /compare dca vs cycle grid/i }))
    expect(onRun).toHaveBeenCalledTimes(1)
  })
})
