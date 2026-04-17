import React, { createContext, useContext, useState } from 'react';

const mockUser = {
  id: '00000000-0000-0000-0000-000000000000',
  email: 'dev@example.com',
  full_name: 'Developer Mode',
  role: 'admin' as const,
  organization_id: '00000000-0000-0000-0000-000000000000',
  is_active: true,
  created_at: new Date().toISOString()
};

const AuthContext = createContext({
  user: mockUser,
  isAuthenticated: true,
  isLoading: false,
  role: 'admin' as const,
  login: async () => {},
  register: async () => {},
  logout: async () => {}
});

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  console.log('--- AUTH PROVIDER MOUNTING (STABILIZATION MODE) ---');
  return (
    <AuthContext.Provider
      value={{
        user: mockUser,
        isAuthenticated: true,
        isLoading: false,
        role: 'admin',
        login: async () => {},
        register: async () => {},
        logout: async () => {}
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
