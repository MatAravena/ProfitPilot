import { users } from "../route"

export const GET = async (
    _request: Request, 
    { params }: { params: { id:string } }) =>{
    
    const { id } = await params
    const user = users.find( user => user.id === parseInt(id))
    return Response.json(user)
}

// export const POST = async (request: Request) => {

//     const userReq = await request.json()
//     const newUser = {
//         id: users.length +1,
//         name: userReq.name
//     }

//     users.push(newUser)

//     return new Response(JSON.stringify(newUser), {
//         headers: {"Content-Type": "application/json"},
//         status: 201
//     })
// }
