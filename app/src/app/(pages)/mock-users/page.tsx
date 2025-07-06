import { revalidatePath } from "next/cache"
import { auth, currentUser } from "@clerk/nextjs/server";

type User = {
    id: number;
    name: string;
}

const UsersServer = async () =>{

    const authObj = await auth()
    const userObj = await currentUser()

    //server display for auth
    console.log({
        authObj,
        userObj
    })

    const mockUrl = "https://67b7373a2bddacfb270e284a.mockapi.io/users"
    const respone = await fetch(mockUrl)
    const users = await respone.json()

    const AddUser = async (formData: FormData) => {
        "use server"
        const name = formData.get('name')
        const res = await fetch(mockUrl,
            { 
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({name})
            })
        const newUser = await res.json()
        revalidatePath("/mock-users")
        console.log(newUser)
    }

    return (
    <div className="py-10">
        <form action={AddUser} className="mb-4">
            <input type="text" name="name" required className="border p-2 mr-2 rounded" />
            <button type="submit" className="bg-blue-500 text-white px-4 py-2 rounded">Add User</button>
        </form>
        <div className="grid grid-cols-4 gap-4 py-10">
            {users.map((user : User, i: number) =>  
                <div key={i} className="p-4 bg-white shadow-md rounded-lg text-gray-700">
                    {user.name}
                </div>
            )}
        </div>
    </div>
    )
}

export default UsersServer