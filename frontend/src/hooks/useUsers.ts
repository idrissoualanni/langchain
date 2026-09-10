// Hook Users — liste + création
import { useCallback, useEffect, useState } from 'react';
import type { User } from '../types/agent';
import { createUser, listUsers } from '../api/users';

export function useUsers() {
  const [users, setUsersState] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const list = await listUsers();
      setUsersState(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const create = useCallback(
    async (name: string): Promise<User> => {
      const user = await createUser(name);
      await refresh();
      return user;
    },
    [refresh]
  );

  return { users, loading, error, refresh, create };
}
