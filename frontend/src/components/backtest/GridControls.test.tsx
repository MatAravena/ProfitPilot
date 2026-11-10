import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { GridControls } from './GridControls'
import { DEFAULT_GRID_PARAMS, GRID_PRESETS, mergeGridParams } from '@/lib/gridParams'

function setup(overrides: Partial<React.ComponentProps<typeof GridControls>> = {}) {
  const onChange = vi.fn()
  const onRun = vi.fn()
  const props: React.ComponentProps<typeof GridControls> = {
    params: DEFAULT_GRID_PARAMS,
    onChange,
    onRun,
    isPending: false,
    ...overrides,
  }
  render(<GridControls {...props} />)
  return { ...props, onChange, onRun }
}

describe('GridControls', () => {
  it('hides the parameter fields until the panel is expanded', async () => {
    setup()
    expect(screen.queryByLabelText('Min edge (× costs)')).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: /tune parameters/i }))
    expect(screen.getByLabelText('Min edge (× costs)')).toBeInTheDocument()
  })

  it('renders fields from both param groups', async () => {
    setup()
    await userEvent.click(screen.getByRole('button', { name: /tune parameters/i }))
    expect(screen.getByLabelText('Range width (× ATR)')).toBeInTheDocument()   // grid group
    expect(screen.getByLabelText('EMA fast')).toBeInTheDocument()              // regime group
  })

  it('calls onChange with the edited numeric field value', async () => {
    const { onChange } = setup()
    await userEvent.click(screen.getByRole('button', { name: /tune parameters/i }))
    fireEvent.change(screen.getByLabelText('Min edge (× costs)'), { target: { value: '5' } })
    expect(onChange).toHaveBeenCalled()
    const last = onChange.mock.calls.slice(-1)[0][0]
    expect(last.grid.min_edge).toBe(5)
  })

  it('calls onChange when the spacing_mode enum is switched', async () => {
    const { onChange } = setup()
    await userEvent.click(screen.getByRole('button', { name: /tune parameters/i }))
    await userEvent.selectOptions(screen.getByLabelText('Spacing mode'), 'arithmetic')
    const last = onChange.mock.calls.slice(-1)[0][0]
    expect(last.grid.spacing_mode).toBe('arithmetic')
  })

  it('applies a preset through onChange', async () => {
    const { onChange } = setup()
    await userEvent.click(screen.getByRole('button', { name: /tune parameters/i }))
    await userEvent.selectOptions(screen.getByLabelText(/preset/i), 'tight')
    expect(onChange).toHaveBeenLastCalledWith(GRID_PRESETS.tight)
  })

  it('resets to defaults', async () => {
    const { onChange } = setup({ params: mergeGridParams({ grid: { min_edge: 9 } }) })
    await userEvent.click(screen.getByRole('button', { name: /tune parameters/i }))
    await userEvent.click(screen.getByRole('button', { name: /reset/i }))
    expect(onChange).toHaveBeenLastCalledWith(DEFAULT_GRID_PARAMS)
  })

  it('fires onRun and disables the run button while pending', async () => {
    const { onRun } = setup()
    await userEvent.click(screen.getByRole('button', { name: /run grid backtest/i }))
    expect(onRun).toHaveBeenCalledTimes(1)

    setup({ isPending: true })
    expect(screen.getByRole('button', { name: /running grid/i })).toBeDisabled()
  })
})
