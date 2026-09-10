// API Users
import type { User } from '../types/agent';
import { apiFetch } from './base';

export async function listUsers(): Promise<User[]> {
  return apiFetch<User[]>('/api/users');
}

export async function getUser(userId: string): Promise<User> {
  return apiFetch<User>(`/api/users/${userId}`);
}

export async function createUser(name: string): Promise<User> {
  return apiFetch<User>('/api/users', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}
