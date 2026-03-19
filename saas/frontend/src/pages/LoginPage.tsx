import { useState } from 'react'
import { PawPrint, Mail, Lock, Chrome } from 'lucide-react'
import { signIn, signInWithGoogle } from '../lib/firebase'
import { useNavigate } from 'react-router-dom'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const navigate = useNavigate()

  const handleEmailLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsLoading(true)

    try {
      await signIn(email, password)
      navigate('/')
    } catch (err: any) {
      setError(err.message || 'Failed to sign in')
    } finally {
      setIsLoading(false)
    }
  }

  const handleGoogleLogin = async () => {
    setError('')
    setIsLoading(true)

    try {
      await signInWithGoogle()
      navigate('/')
    } catch (err: any) {
      setError(err.message || 'Failed to sign in with Google')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-50 dark:bg-surface-950">
      <div className="w-full max-w-md space-y-8 rounded-2xl bg-white p-8 shadow-lg dark:bg-surface-900">
        {/* Logo */}
        <div className="flex flex-col items-center">
          <div className="flex items-center gap-2">
            <PawPrint className="h-12 w-12 text-primary-500" />
            <span className="text-3xl font-bold">Taskbolt</span>
          </div>
          <p className="mt-2 text-surface-500">Sign in to your account</p>
        </div>

        {/* Error message */}
        {error && (
          <div className="rounded-lg bg-red-50 p-4 text-sm text-red-600 dark:bg-red-950 dark:text-red-400">
            {error}
          </div>
        )}

        {/* Email login form */}
        <form onSubmit={handleEmailLogin} className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium">
              Email
            </label>
            <div className="relative mt-1">
              <Mail className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-surface-400" />
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-surface-300 bg-white py-2.5 pl-10 pr-4 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 dark:border-surface-700 dark:bg-surface-800"
                placeholder="you@example.com"
                required
              />
            </div>
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium">
              Password
            </label>
            <div className="relative mt-1">
              <Lock className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-surface-400" />
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-surface-300 bg-white py-2.5 pl-10 pr-4 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 dark:border-surface-700 dark:bg-surface-800"
                placeholder="••••••••"
                required
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full rounded-lg bg-primary-500 py-2.5 text-sm font-medium text-white hover:bg-primary-600 disabled:opacity-50"
          >
            {isLoading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>

        {/* Divider */}
        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-surface-200 dark:border-surface-700" />
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="bg-white px-2 text-surface-500 dark:bg-surface-900">
              Or continue with
            </span>
          </div>
        </div>

        {/* Google login */}
        <button
          onClick={handleGoogleLogin}
          disabled={isLoading}
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-surface-300 bg-white py-2.5 text-sm font-medium hover:bg-surface-50 disabled:opacity-50 dark:border-surface-700 dark:bg-surface-800 dark:hover:bg-surface-700"
        >
          <Chrome className="h-5 w-5" />
          Google
        </button>

        {/* Sign up link */}
        <p className="text-center text-sm text-surface-500">
          Don't have an account?{' '}
          <a href="#" className="text-primary-500 hover:text-primary-600">
            Sign up
          </a>
        </p>
      </div>
    </div>
  )
}
