export const users = [
    {id:1, name:"Matias Aravena"},
    {id:2, name:"Sandra Edwards"},
]

export const GET = async () =>{
    return Response.json(users)
}

export const POST = async (request: Request) => {

    const userReq = await request.json()
    const newUser = {
        id: users.length +1,
        name: userReq.name
    }

    users.push(newUser)

    return new Response(JSON.stringify(newUser), {
        headers: {"Content-Type": "application/json"},
        status: 201
    })
}
