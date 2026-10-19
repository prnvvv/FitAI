import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PanelMenu } from './PanelMenu'
import { SegmentedControl } from './SegmentedControl'
import { TemplatePopover } from './TemplatePopover'

describe('SegmentedControl', () => {
  it('checks the current value and reports changes', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <SegmentedControl
        label="Day type"
        name="day-type"
        options={[
          { value: 'workout', label: 'Workout' },
          { value: 'rest', label: 'Rest' },
        ]}
        value="workout"
        onChange={onChange}
      />,
    )

    expect(screen.getByRole('radio', { name: 'Workout' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Rest' })).not.toBeChecked()

    await user.click(screen.getByRole('radio', { name: 'Rest' }))
    expect(onChange).toHaveBeenCalledWith('rest')
  })
})

describe('PanelMenu', () => {
  it('opens on trigger click, selects an item, and closes', async () => {
    const onSelect = vi.fn()
    const user = userEvent.setup()
    render(
      <PanelMenu
        triggerLabel="Day options"
        trigger={<span>…</span>}
        items={[{ label: 'Mark as rest day', onSelect }]}
      />,
    )

    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Day options' }))
    expect(screen.getByRole('menu')).toBeInTheDocument()

    await user.click(screen.getByRole('menuitem', { name: 'Mark as rest day' }))
    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('moves with arrow keys and closes on Esc, returning focus', async () => {
    const user = userEvent.setup()
    render(
      <PanelMenu
        triggerLabel="Day options"
        trigger={<span>…</span>}
        items={[
          { label: 'First', onSelect: () => {} },
          { label: 'Second', onSelect: () => {} },
        ]}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Day options' }))
    expect(screen.getByRole('menuitem', { name: 'First' })).toHaveFocus()

    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('menuitem', { name: 'Second' })).toHaveFocus()

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Day options' })).toHaveFocus()
  })
})

describe('TemplatePopover', () => {
  const templates = [{ key: 'upper_lower', name: 'Upper Lower', days: [] }]

  it('renders nothing when closed', () => {
    render(
      <TemplatePopover
        open={false}
        templates={templates}
        templateKey=""
        templateDate="2026-10-14"
        applying={false}
        onKeyChange={() => {}}
        onDateChange={() => {}}
        onApply={() => {}}
        onClose={() => {}}
      />,
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('disables Apply without a template and reports changes', async () => {
    const onKeyChange = vi.fn()
    const onApply = vi.fn()
    const user = userEvent.setup()
    const { rerender } = render(
      <TemplatePopover
        open
        templates={templates}
        templateKey=""
        templateDate="2026-10-14"
        applying={false}
        onKeyChange={onKeyChange}
        onDateChange={() => {}}
        onApply={onApply}
        onClose={() => {}}
      />,
    )

    expect(screen.getByRole('button', { name: 'Apply template' })).toBeDisabled()
    await user.click(screen.getByRole('radio', { name: /Upper Lower/ }))
    expect(onKeyChange).toHaveBeenCalledWith('upper_lower')

    rerender(
      <TemplatePopover
        open
        templates={templates}
        templateKey="upper_lower"
        templateDate="2026-10-14"
        applying={false}
        onKeyChange={onKeyChange}
        onDateChange={() => {}}
        onApply={onApply}
        onClose={() => {}}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Apply template' }))
    expect(onApply).toHaveBeenCalledTimes(1)
  })

  it('closes on Escape', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(
      <TemplatePopover
        open
        templates={templates}
        templateKey=""
        templateDate="2026-10-14"
        applying={false}
        onKeyChange={() => {}}
        onDateChange={() => {}}
        onApply={() => {}}
        onClose={onClose}
      />,
    )

    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
