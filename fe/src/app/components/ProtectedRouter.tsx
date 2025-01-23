"use client"

import type { ReactNode } from 'react';
import { useContext, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import AuthContext from '../context/authContext'

const ProtectedRoute = (children: ReactNode) => {
    const user = useContext(AuthContext)?.user;
    const router = useRouter()

    useEffect(() => {

        if(!user){
            router.push('/login')
        }
    }, [user, router])

    return  user ? children : null ;
}

export default ProtectedRoute;