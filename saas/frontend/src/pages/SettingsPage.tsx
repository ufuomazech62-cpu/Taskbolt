import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Settings, Users, Key, Globe } from 'lucide-react'
import { useState } from 'react'
import api from '../lib/api'

export default function SettingsPage() {
  const queryClient = useQueryClient()
  
  const { data: tenant } = useQuery({
    queryKey: ['tenant'],
    queryFn: () => api.getTenant(),
  })
  
  const { data: apiKeys } = useQuery({
    queryKey: ['api-keys'],
    queryFn: () => api.listApiKeys(),
  })

  const [newKeyName, setNewKeyName] = useState('')

  const createKeyMutation = useMutation({
    mutationFn: () => api.createApiKey(newKeyName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
      setNewKeyName('')
    },
  })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-surface-500">Manage your workspace settings</p>
      </div>
      
      {/* General settings */}
      <div className="rounded-xl bg-white p-6 shadow-sm dark:bg-surface-900">
        <div className="flex items-center gap-3">
          <Settings className="h-5 w-5 text-surface-500" />
          <h2 className="text-lg font-semibold">General</h2>
        </div>
        <div className="mt-4 space-y-4">
          <div>
            <label className="block text-sm font-medium">Workspace Name</label>
            <input
              type="text"
              defaultValue={tenant?.name}
              className="mt-1 w-full max-w-md rounded-lg border border-surface-300 bg-white px-4 py-2 text-sm dark:border-surface-700 dark:bg-surface-800"
            />
          </div>
          <div>
            <label className="block text-sm font-medium">Plan</label>
            <p className="mt-1 text-surface-500">{tenant?.plan} plan</p>
          </div>
        </div>
      </div>
      
      {/* API Keys */}
      <div className="rounded-xl bg-white p-6 shadow-sm dark:bg-surface-900">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Key className="h-5 w-5 text-surface-500" />
            <h2 className="text-lg font-semibold">API Keys</h2>
          </div>
          <button
            onClick={() => newKeyName && createKeyMutation.mutate()}
            disabled={!newKeyName}
            className="rounded-lg bg-primary-500 px-4 py-2 text-sm font-medium text-white hover:bg-primary-600 disabled:opacity-50"
          >
            Create Key
          </button>
        </div>
        
        <div className="mt-4 flex max-w-md gap-2">
          <input
            type="text"
            value={newKeyName}
            onChange={(e) => setNewKeyName(e.target.value)}
            placeholder="Key name"
            className="flex-1 rounded-lg border border-surface-300 bg-white px-4 py-2 text-sm dark:border-surface-700 dark:bg-surface-800"
          />
        </div>
        
        <div className="mt-4 space-y-2">
          {apiKeys?.api_keys.map((key) => (
            <div
              key={key.id}
              className="flex items-center justify-between rounded-lg border border-surface-200 p-4 dark:border-surface-700"
            >
              <div>
                <p className="font-medium">{key.name}</p>
                <p className="text-sm text-surface-500">{key.key_prefix}...</p>
              </div>
              <div className="text-sm text-surface-500">
                {key.last_used_at ? `Last used: ${new Date(key.last_used_at).toLocaleDateString()}` : 'Never used'}
              </div>
            </div>
          ))}
          
          {apiKeys?.api_keys.length === 0 && (
            <p className="py-4 text-center text-surface-500">No API keys yet</p>
          )}
        </div>
      </div>
    </div>
  )
}
