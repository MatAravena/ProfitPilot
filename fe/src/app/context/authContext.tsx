"use client"

import type { ReactNode } from 'react';
import React, { createContext, useState } from "react"
import { useRouter } from "next/navigation";
import axios from "axios";

export interface User {
    username?: string;
    pass?: string;
    email?: string;
    roles?: string[];
    token?: string;
}

interface AuthContextType {
    user: User | undefined; 
    login: (username: string, password: string) => Promise<void>;
    logout: () => void;
}

interface AuthProviderProps {
    children: ReactNode;
}

const AuthContext = createContext<AuthContextType| null>(null);

export const AuthProvider = ({ children }: AuthProviderProps) =>{
    const [user, setUser] = useState()
    const router = useRouter()

    const login = async ( username: string, pass: string) =>{
        try {
            const formData = new FormData();
            formData.append('username',username)
            formData.append('pass',pass)

            const response = await axios.post('http://localhost:8000/auth/token', formData, {
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            });

            axios.defaults.headers.common['Authorization'] = `Bearer ${response.data.access_token}`
            localStorage.setItem('token', response.data.access_token)
            setUser(response.data);
            router.push('/')
        } catch (error) {
            console.log('Login Failed: ', error)
        }
    }

    const logout = ( ) =>{
        setUser(undefined)
        delete axios.defaults.headers.common['Authorization']
        router.push('/login')
    }

    return (
        <AuthContext.Provider value={{ user, login, logout }}>
            {children}
        </AuthContext.Provider>
    );
}

export default AuthContext;
