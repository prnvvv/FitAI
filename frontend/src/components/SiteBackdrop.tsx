import { useLocation } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'
import '../backdrop.css'

export function SiteBackdrop() {
  const location = useLocation()
  const isInitialMountRef = useRef(true)
  const [isInitialMount, setIsInitialMount] = useState(true)

  const route = location.pathname === '/' ? 'landing' : 'auth'

  // Preload image on first mount
  useEffect(() => {
    const img = new Image()
    img.src = '/images/fitai-roman-pillar.png'
    
    // Mark initial mount as complete after first render
    if (isInitialMountRef.current) {
      isInitialMountRef.current = false
      setIsInitialMount(false)
    }
  }, [])

  return (
    <div
      className="backdrop"
      data-route={route}
      data-initial={isInitialMount ? 'true' : 'false'}
      aria-hidden="true"
    >
      <img
        className="backdrop__img"
        src="/images/fitai-roman-pillar.png"
        alt=""
        decoding="async"
        fetchPriority="high"
      />
      <div className="backdrop__shade shade--landing" />
      <div className="backdrop__shade shade--auth" />
      <div className="backdrop__blur" />
      <div className="backdrop__glow" />
      <div className="backdrop__arc" />
    </div>
  )
}