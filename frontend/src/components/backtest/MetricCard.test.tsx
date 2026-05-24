import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TrendingUp } from 'lucide-react'
import { MetricCard } from './MetricCard'

describe('MetricCard', () => {
  it('renders label and value', () => {
    render(<MetricCard label="Total Return" value="12.5%" positive icon={TrendingUp} />)
    expect(screen.getByText('Total Return')).toBeInTheDocument()
    expect(screen.getByText('12.5%')).toBeInTheDocument()
  })

  it('applies success color when positive', () => {
    render(<MetricCard label="Return" value="10%" positive icon={TrendingUp} />)
    expect(screen.getByText('10%')).toHaveClass('text-success')
  })

  it('applies danger color when not positive', () => {
    render(<MetricCard label="Drawdown" value="-5%" positive={false} icon={TrendingUp} />)
    expect(screen.getByText('-5%')).toHaveClass('text-danger')
  })
})
