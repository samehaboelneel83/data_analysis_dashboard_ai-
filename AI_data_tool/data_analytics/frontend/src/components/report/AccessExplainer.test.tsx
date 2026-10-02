import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import AccessExplainer from './AccessExplainer'

describe('AccessExplainer data rules (3.13)', () => {
  it('lists the row and column rules applied to me', () => {
    render(<AccessExplainer onClose={() => {}} decisions={[
      { resource: 'report', id: 1, action: 'view', allowed: true, reason: 'Shared with your role.' },
      { resource: 'report', id: 1, action: 'data_rules', allowed: true, reason: 'Your role (Dept manager) sees this data through 1 rule set.',
        rules: [{ dataset_id: 3, dataset_name: 'Current workforce', row_rule: 'owner == USEREMAIL()',
                  row_rule_for_you: "owner == 'm@hr.co'", hidden_columns: ['salary'] }] },
    ]} />)
    const box = screen.getByTestId('access-data-rules')
    expect(within(box).getByText('Current workforce')).toBeInTheDocument()
    expect(within(box).getByText("owner == 'm@hr.co'")).toBeInTheDocument()
    expect(within(box).getByText('salary')).toBeInTheDocument()
    // the rules are a section, not a fake "may I" line
    expect(within(screen.getByTestId('access-decisions')).queryByText('data_rules')).not.toBeInTheDocument()
  })
})
