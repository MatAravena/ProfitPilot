"use client"

import React, { createContext, useState } from "react"
import { useRouter } from "next/navigation";
import axios from "axios"; 
import { AuthContextType, AuthProviderProps } from '@app//types/auth';

const AuthContext = createContext<AuthContextType>({ 
    user: undefined,
    login: async () => {},
    logout: () => {},
});

export const AuthProvider = ({ children }: AuthProviderProps) =>{
    const [user, setUser] = useState()
    const router = useRouter()

    const login = async ( username: string, pass: string) =>{
        try {
            const formData = new FormData();
            formData.append('username',username)
            formData.append('password',pass)
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
