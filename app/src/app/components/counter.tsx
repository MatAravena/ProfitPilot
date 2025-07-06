"use client"
import { useState } from "react"

export const Counter = () => {

    // const { isLoaded, userId, sessionId, getToken } = useAuth()
    // const { isLoaded, isSignedIn, user } = useUser()
    // console.log("user",user )

    const [count, setCount] = useState(0)

    // if(!isLoaded || !isSignedIn){
    //     return null
    // }

    return <>
        <h1>Counter</h1>
        <button onClick={()=> setCount( count+1)} > Clicked {count} times</button>
        {/* 
        <br />
        sessionId: {sessionId}

        <br />
        getToken: {getToken}  */}

        <br />
        {/* user: {...user} */}
    </>

}