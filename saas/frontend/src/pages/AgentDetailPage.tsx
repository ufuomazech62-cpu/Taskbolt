import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Bot, Settings, Trash2 } from 'lucide-react'
import api from '../lib/api'

export default function AgentDetailPage() {
  const { agentId } = useParams()

  const { data: agent, isLoading } = useQuery({
    queryKey: ['agent', agentId],
    queryFn: () => api.getAgent(agentId!),
    enabled: !!agentId,
  })

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary-500 border-t-transparent" />
      </div>
    )
  }

  if (!agent) {
    return (
      <div className="flex h-96 flex-col items-center justify-center">
        <Bot className="h-12 w-12 text-surface-400" />
        <p className="mt-4 text-surface-500">Agent not found</p>
        <Link to="/agents" className="mt-2 text-primary-500 hover:underline">
          Back to agents
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link
            to="/agents"
            className="rounded-lg p-2 text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800"
          >
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div>
            <h1 className="text-2xl font-semibold">{agent.name}</h1>
            <p className="text-surface-500">{agent.description || 'No description'}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button className="flex items-center gap-2 rounded-lg border border-surface-300 px-4 py-2 text-sm font-medium hover:bg-surface-50 dark:border-surface-700 dark:hover:bg-surface-800">
            <Settings className="h-4 w-4" />
            Settings
          </button>
          <button className="flex items-center gap-2 rounded-lg border border-red-300 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 dark:border-red-900 dark:hover:bg-red-950">
            <Trash2 className="h-4 w-4" />
            Delete
          </button>
        </div>
      </div>
      
      {/* Agent info */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Main content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Chat interface placeholder */}
          <div className="rounded-xl bg-white p-6 shadow-sm dark:bg-surface-900">
            <h2 className="text-lg font-semibold">Chat</h2>
            <div className="mt-4 h-64 rounded-lg border-2 border-dashed border-surface-300 dark:border-surface-700 flex items-center justify-center">
              <p className="text-surface-500">Chat interface coming soon</p>
            </div>
          </div>
        </div>
        
        {/* Sidebar */}
        <div className="space-y-6">
          {/* Status */}
          <div className="rounded-xl bg-white p-6 shadow-sm dark:bg-surface-900">
            <h3 className="font-semibold">Status</h3>
            <div className="mt-4 flex items-center gap-2">
              <span
                className={`h-2 w-2 rounded-full ${
                  agent.is_active ? 'bg-green-500' : 'bg-surface-400'
                }`}
              />
              <span className="text-sm">
                {agent.is_active ? 'Active' : 'Inactive'}
              </span>
            </div>
          </div>
          
          {/* Configuration */}
          <div className="rounded-xl bg-white p-6 shadow-sm dark:bg-surface-900">
            <h3 className="font-semibold">Configuration</h3>
            <div className="mt-4 space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-surface-500">Channels</span>
                <span>{Object.keys(agent.channels || {}).length}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-surface-500">Tools</span>
                <span>{Object.keys(agent.tools?.builtin_tools || {}).length}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-surface-500">MCP Clients</span>
                <span>{Object.keys(agent.mcp?.clients || {}).length}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
