import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { SidebarNavItem } from './SidebarNavItem'

describe('SidebarNavItem', () => {
  it('calls onClick when pressed', () => {
    const onClick = vi.fn()
    render(<SidebarNavItem icon={<span>icon</span>} label="New chat" onClick={onClick} />)

    fireEvent.click(screen.getByRole('button', { name: 'New chat' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })
})
