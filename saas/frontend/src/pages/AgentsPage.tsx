import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Bot, Plus } from 'lucide-react'
import api from '../lib/api'

export default function AgentsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['agents'],
    queryFn: () => api.listAgents(),
  })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Agents</h1>
          <p className="text-surface-500">
            Manage your AI agents
          </p>
        </div>
        <button className="flex items-center gap-2 rounded-lg bg-primary-500 px-4 py-2 text-sm font-medium text-white hover:bg-primary-600">
          <Plus className="h-4 w-4" />
          Create Agent
        </button>
      </div>
      
      {/* Agents grid */}
      {isLoading ? (
        <div className="flex h-48 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary-500 border-t-transparent" />
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data?.agents.map((agent) => (
            <Link
              key={agent.id}
              to={`/agents/${agent.id}`}
              className="group rounded-xl bg-white p-6 shadow-sm transition-shadow hover:shadow-md dark:bg-surface-900"
            >
              <div className="flex items-start gap-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-primary-100 dark:bg-primary-900">
                  <Bot className="h-6 w-6 text-primary-500" />
                </div>
                <div className="flex-1">
                  <h3 className="font-semibold group-hover:text-primary-500">
                    {agent.name}
                  </h3>
                  <p className="mt-1 text-sm text-surface-500">
                    {agent.description || 'No description'}
                  </p>
                </div>
              </div>
              <div className="mt-4 flex items-center gap-2">
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    agent.is_active
                      ? 'bg-green-100 text-green-600 dark:bg-green-900 dark:text-green-400'
                      : 'bg-surface-100 text-surface-600 dark:bg-surface-800 dark:text-surface-400'
                  }`}
                >
                  {agent.is_active ? 'Active' : 'Inactive'}
                </span>
              </div>
            </Link>
          ))}
          
          {data?.agents.length === 0 && (
            <div className="col-span-full rounded-xl bg-white p-12 text-center dark:bg-surface-900">
              <Bot className="mx-auto h-12 w-12 text-surface-400" />
              <h3 className="mt-4 font-semibold">No agents yet</h3>
              <p className="mt-2 text-sm text-surface-500">
                Create your first agent to get started
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
