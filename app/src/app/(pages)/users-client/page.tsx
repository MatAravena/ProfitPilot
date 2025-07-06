"use client"
import { User } from "@app//types/general";
import { useState, useEffect } from "react";

const UsersClient = () =>{
    const [users, setUsers] = useState<User[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')

    useEffect(() => {
        const fetchUsers = async () => {
            try {
                const respone = await fetch("https://jsonplaceholder.typicode.com/users")

                if (!respone.ok) throw new Error('Failed to fetch users')
                
                const data = await respone.json()
                setUsers(data)

            } catch (err) {
                setError('Failed to fetch users')
                if (err instanceof Error) setError(`Failed to fetch users: ${err.message} `)
            }
            finally{
                setLoading(false)
            }
        }

        fetchUsers()
    }, [])


    if(loading) return <div>Loading ... </div>
    if(error) return <div>{error}</div>

    return (
        <ul className="space-y-4 p-4">
            {users.map((user, i) =>  
                <li key={i} className="p-4 bg-white shadow-md rounded-lg text-gray-700">
                    {user.name} ({user.email})
                </li>
            )}
        </ul>
    )
    
}

export { UsersClient };
// export type { User };
 