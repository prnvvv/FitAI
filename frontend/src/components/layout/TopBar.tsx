interface TopBarProps {
  title?: string
}

export function TopBar({ title }: TopBarProps) {
  return (
    <header className="top-bar">
      {title && <span className="top-bar__title">{title}</span>}
    </header>
  )
}
