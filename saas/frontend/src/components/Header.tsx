import { Sun, Moon, Bell } from 'lucide-react'
import { useState, useEffect } from 'react'

export default function Header() {
  const [isDark, setIsDark] = useState(false)

  useEffect(() => {
    // Check for dark mode preference
    const isDarkMode = document.documentElement.classList.contains('dark')
    setIsDark(isDarkMode)
  }, [])

  const toggleTheme = () => {
    const newDark = !isDark
    setIsDark(newDark)
    document.documentElement.classList.toggle('dark', newDark)
  }

  return (
    <header className="flex h-16 items-center justify-between border-b border-surface-200 bg-white px-6 dark:border-surface-800 dark:bg-surface-900">
      <div className="flex items-center gap-4">
        {/* Search could go here */}
      </div>
      
      <div className="flex items-center gap-4">
        {/* Notifications */}
        <button className="rounded-lg p-2 text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800">
          <Bell className="h-5 w-5" />
        </button>
        
        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          className="rounded-lg p-2 text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800"
        >
          {isDark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </button>
      </div>
    </header>
  )
}
