// Taskbolt SaaS - Firebase Configuration
// 
// This module initializes Firebase services:
// - Authentication (for user login/signup)
// - Firestore (optional, for real-time features)
// - Storage (for file uploads)

import { initializeApp, FirebaseApp } from 'firebase/app';
import { 
  getAuth, 
  Auth,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signInWithPopup,
  GoogleAuthProvider,
  signOut,
  onAuthStateChanged,
  User,
  UserCredential,
} from 'firebase/auth';

// Firebase configuration from environment
const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

// Initialize Firebase
let app: FirebaseApp;
let auth: Auth;

export function initializeFirebase(): { app: FirebaseApp; auth: Auth } {
  if (!app) {
    app = initializeApp(firebaseConfig);
    auth = getAuth(app);
  }
  return { app, auth };
}

// Get initialized auth instance
export function getAuthInstance(): Auth {
  if (!auth) {
    initializeFirebase();
  }
  return auth;
}

// ============================================================================
// Authentication Methods
// ============================================================================

/**
 * Sign in with email and password
 */
export async function signIn(email: string, password: string): Promise<UserCredential> {
  const auth = getAuthInstance();
  return signInWithEmailAndPassword(auth, email, password);
}

/**
 * Sign up with email and password
 */
export async function signUp(email: string, password: string): Promise<UserCredential> {
  const auth = getAuthInstance();
  return createUserWithEmailAndPassword(auth, email, password);
}

/**
 * Sign in with Google popup
 */
export async function signInWithGoogle(): Promise<UserCredential> {
  const auth = getAuthInstance();
  const provider = new GoogleAuthProvider();
  return signInWithPopup(auth, provider);
}

/**
 * Sign out current user
 */
export async function signOutUser(): Promise<void> {
  const auth = getAuthInstance();
  return signOut(auth);
}

/**
 * Get current user
 */
export function getCurrentUser(): User | null {
  const auth = getAuthInstance();
  return auth.currentUser;
}

/**
 * Get ID token for API requests
 */
export async function getIdToken(forceRefresh = false): Promise<string | null> {
  const user = getCurrentUser();
  if (!user) return null;
  return user.getIdToken(forceRefresh);
}

/**
 * Subscribe to auth state changes
 */
export function subscribeToAuthChanges(callback: (user: User | null) => void): () => void {
  const auth = getAuthInstance();
  return onAuthStateChanged(auth, callback);
}

// ============================================================================
// Auth Token Management
// ============================================================================

/**
 * Get authorization header for API requests
 */
export async function getAuthHeader(): Promise<Record<string, string>> {
  const token = await getIdToken();
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

/**
 * Refresh token and get new header
 */
export async function refreshAuthHeader(): Promise<Record<string, string>> {
  const token = await getIdToken(true); // Force refresh
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

// ============================================================================
// Types
// ============================================================================

export type { User, UserCredential };
