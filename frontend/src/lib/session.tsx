import { createContext, useContext } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, api, type Me, type Role } from './api';

const ME = ['me'] as const;

/** Who is signed in: `null` when nobody is, `undefined` while still finding out. */
export function useMe() {
  return useQuery({
    queryKey: ME,
    queryFn: async (): Promise<Me | null> => {
      try {
        return await api.me();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    staleTime: 60_000,
    retry: false,
  });
}

/** Sign in, sign up and sign out. Each one updates who `useMe` reports. */
export function useAuthActions() {
  const client = useQueryClient();
  const signedIn = (me: Me) => client.setQueryData(ME, me);
  return {
    login: useMutation({ mutationFn: api.login, onSuccess: signedIn }),
    register: useMutation({ mutationFn: api.register, onSuccess: signedIn }),
    createWorkspace: useMutation({ mutationFn: api.createWorkspace, onSuccess: () => client.invalidateQueries({ queryKey: ME }) }),
    logout: useMutation({
      mutationFn: api.logout,
      // Even if the request fails, nothing from this session should stay on screen.
      onSettled: () => {
        client.clear();
        client.setQueryData(ME, null);
      },
    }),
  };
}

type SignedIn = Me & { workspace: NonNullable<Me['workspace']>; role: Role };

const SessionContext = createContext<SignedIn | null>(null);

export const SessionProvider = SessionContext.Provider;

/** The signed-in person and their workspace. Only for screens inside the app shell. */
export function useSession(): SignedIn {
  const session = useContext(SessionContext);
  if (!session) throw new Error('useSession needs a signed-in person with a workspace');
  return session;
}

export function isSignedIn(me: Me): me is SignedIn {
  return me.workspace !== null && me.role !== null;
}

const MANAGER_ROLES: Role[] = ['owner', 'admin'];

export function canManage(role: Role) {
  return MANAGER_ROLES.includes(role);
}
