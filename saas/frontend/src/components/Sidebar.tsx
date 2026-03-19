import { NavLink } from 'react-router-dom'
import { 
  Home, 
  Bot, 
  Settings, 
  CreditCard,
  LogOut,
  PawPrint 
} from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { signOutUser } from '../lib/firebase'

const navItems = [
  { to: '/', icon: Home, label: 'Dashboard' },
  { to: '/agents', icon: Bot, label: 'Agents' },
  { to: '/settings', icon: Settings, label: 'Settings' },
  { to: '/billing', icon: CreditCard, label: 'Billing' },
]

export default function Sidebar() {
  const { user } = useAuth()

  return (
    <aside className="flex w-64 flex-col border-r border-surface-200 bg-white dark:border-surface-800 dark:bg-surface-900">
      {/* Logo */}
      <div className="flex h-16 items-center gap-2 border-b border-surface-200 px-6 dark:border-surface-800">
        <PawPrint className="h-8 w-8 text-primary-500" />
        <span className="text-xl font-semibold">Taskbolt</span>
      </div>
      
      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-4">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-primary-50 text-primary-600 dark:bg-primary-950 dark:text-primary-400'
                  : 'text-surface-600 hover:bg-surface-100 dark:text-surface-400 dark:hover:bg-surface-800'
              }`
            }
          >
            <item.icon className="h-5 w-5" />
            {item.label}
          </NavLink>
        ))}
      </nav>
      
      {/* User section */}
      <div className="border-t border-surface-200 p-4 dark:border-surface-800">
        <div className="flex items-center gap-3 rounded-lg p-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-surface-200 dark:bg-surface-700">
            {user?.photoURL ? (
              <img src={user.photoURL} alt="" className="h-8 w-8 rounded-full" />
            ) : (
              <span className="text-sm font-medium">
                {user?.email?.charAt(0).toUpperCase()}
              </span>
            )}
          </div>
          <div className="flex-1 truncate">
            <p className="text-sm font-medium">{user?.displayName || 'User'}</p>
            <p className="truncate text-xs text-surface-500">{user?.email}</p>
          </div>
        </div>
        
        <button
          onClick={() => signOutUser()}
          className="mt-2 flex w-full items-center gap-2 rounded-lg px-4 py-2 text-sm text-surface-600 hover:bg-surface-100 dark:text-surface-400 dark:hover:bg-surface-800"
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </button>
      </div>
    </aside>
  )
}
