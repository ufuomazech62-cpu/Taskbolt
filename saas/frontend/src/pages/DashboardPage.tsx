import { useQuery } from '@tanstack/react-query'
import { Bot, MessageSquare, Clock, Zap } from 'lucide-react'
import api from '../lib/api'
import { useAuth } from '../hooks/useAuth'

export default function DashboardPage() {
  const { user } = useAuth()
  
  const { data: tenant } = useQuery({
    queryKey: ['tenant'],
    queryFn: () => api.getTenant(),
  })
  
  const { data: agents } = useQuery({
    queryKey: ['agents'],
    queryFn: () => api.listAgents(),
  })
  
  const { data: usage } = useQuery({
    queryKey: ['usage'],
    queryFn: () => api.getUsage(),
  })

  const stats = [
    { label: 'Agents', value: agents?.agents.length || 0, icon: Bot, color: 'primary' },
    { label: 'Total Chats', value: 0, icon: MessageSquare, color: 'blue' },
    { label: 'Tokens Used', value: usage?.total_tokens?.toLocaleString() || '0', icon: Zap, color: 'green' },
    { label: 'Active Jobs', value: 0, icon: Clock, color: 'orange' },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold">Welcome back!</h1>
        <p className="text-surface-500">
          {tenant?.name || 'Your workspace'} • {tenant?.plan || 'Free'} plan
        </p>
      </div>
      
      {/* Stats grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <div
            key={stat.label}
            className="rounded-xl bg-white p-6 shadow-sm dark:bg-surface-900"
          >
            <div className="flex items-center justify-between">
              <stat.icon className={`h-5 w-5 text-${stat.color}-500`} />
              <span className="text-2xl font-semibold">{stat.value}</span>
            </div>
            <p className="mt-2 text-sm text-surface-500">{stat.label}</p>
          </div>
        ))}
      </div>
      
      {/* Recent activity */}
      <div className="rounded-xl bg-white p-6 shadow-sm dark:bg-surface-900">
        <h2 className="text-lg font-semibold">Recent Activity</h2>
        <p className="mt-4 text-center text-surface-500">
          No recent activity to display.
        </p>
      </div>
    </div>
  )
}
