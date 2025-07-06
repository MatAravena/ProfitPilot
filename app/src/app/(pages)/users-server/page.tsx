import { User } from "../users-client/page"

const UsersServer = async () =>{

    await new Promise((resolve) => setTimeout(resolve, 2000))
    const respone = await fetch("https://jsonplaceholder.typicode.com/users")
    const users = await respone.json() 

    return (
        <ul className="space-y-4 p-4">
            {users.map((user : User, i: number) =>  
                <li key={i} className="p-4 bg-white shadow-md rounded-lg text-gray-700">
                    {user.name} ({user.email})
                </li>
            )}
        </ul>
    )
}

export default UsersServer