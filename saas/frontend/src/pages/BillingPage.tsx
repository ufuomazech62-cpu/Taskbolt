import { useQuery } from '@tanstack/react-query'
import { CreditCard, Check, Zap } from 'lucide-react'
import api from '../lib/api'

const PLANS = [
  {
    id: 'FREE',
    name: 'Free',
    price: 0,
    features: ['1 Agent', '1 User', '1GB Storage', 'Basic Support'],
  },
  {
    id: 'STARTER',
    name: 'Starter',
    price: 19,
    features: ['3 Agents', '5 Users', '10GB Storage', 'Email Support', 'API Access'],
  },
  {
    id: 'PROFESSIONAL',
    name: 'Professional',
    price: 49,
    features: ['10 Agents', '25 Users', '100GB Storage', 'Priority Support', 'Custom Integrations'],
    popular: true,
  },
  {
    id: 'ENTERPRISE',
    name: 'Enterprise',
    price: 199,
    features: ['Unlimited Agents', 'Unlimited Users', '1TB Storage', '24/7 Support', 'Dedicated Infrastructure'],
  },
]

export default function BillingPage() {
  const { data: tenant } = useQuery({
    queryKey: ['tenant'],
    queryFn: () => api.getTenant(),
  })
  
  const { data: usage } = useQuery({
    queryKey: ['usage'],
    queryFn: () => api.getUsage(),
  })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold">Billing</h1>
        <p className="text-surface-500">Manage your subscription and billing</p>
      </div>
      
      {/* Current usage */}
      <div className="rounded-xl bg-white p-6 shadow-sm dark:bg-surface-900">
        <div className="flex items-center gap-3">
          <Zap className="h-5 w-5 text-surface-500" />
          <h2 className="text-lg font-semibold">Current Usage</h2>
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <div className="rounded-lg bg-surface-50 p-4 dark:bg-surface-800">
            <p className="text-sm text-surface-500">Input Tokens</p>
            <p className="mt-1 text-2xl font-semibold">
              {usage?.input_tokens?.toLocaleString() || 0}
            </p>
          </div>
          <div className="rounded-lg bg-surface-50 p-4 dark:bg-surface-800">
            <p className="text-sm text-surface-500">Output Tokens</p>
            <p className="mt-1 text-2xl font-semibold">
              {usage?.output_tokens?.toLocaleString() || 0}
            </p>
          </div>
          <div className="rounded-lg bg-surface-50 p-4 dark:bg-surface-800">
            <p className="text-sm text-surface-500">Estimated Cost</p>
            <p className="mt-1 text-2xl font-semibold">
              ${usage?.estimated_cost_dollars?.toFixed(2) || '0.00'}
            </p>
          </div>
        </div>
      </div>
      
      {/* Plans */}
      <div className="rounded-xl bg-white p-6 shadow-sm dark:bg-surface-900">
        <div className="flex items-center gap-3">
          <CreditCard className="h-5 w-5 text-surface-500" />
          <h2 className="text-lg font-semibold">Plans</h2>
        </div>
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PLANS.map((plan) => (
            <div
              key={plan.id}
              className={`relative rounded-xl border-2 p-6 ${
                tenant?.plan === plan.id
                  ? 'border-primary-500 bg-primary-50 dark:bg-primary-950'
                  : 'border-surface-200 dark:border-surface-700'
              }`}
            >
              {plan.popular && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-primary-500 px-3 py-1 text-xs font-medium text-white">
                  Popular
                </span>
              )}
              <h3 className="font-semibold">{plan.name}</h3>
              <p className="mt-2">
                <span className="text-3xl font-bold">${plan.price}</span>
                <span className="text-surface-500">/mo</span>
              </p>
              <ul className="mt-4 space-y-2">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-center gap-2 text-sm">
                    <Check className="h-4 w-4 text-green-500" />
                    {feature}
                  </li>
                ))}
              </ul>
              <button
                className="mt-6 w-full rounded-lg py-2 text-sm font-medium ${
                  tenant?.plan === plan.id
                    ? 'bg-surface-100 text-surface-500 dark:bg-surface-800'
                    : 'bg-primary-500 text-white hover:bg-primary-600'
                }`}
                disabled={tenant?.plan === plan.id}
              >
                {tenant?.plan === plan.id ? 'Current Plan' : 'Upgrade'}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
