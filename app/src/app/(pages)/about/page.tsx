"use client"
import { useRouter } from "next/navigation"

export const About= () => {
    const router = useRouter();

    return  <div>
        <h1>About Us</h1>
        <button 
            onClick={() => router.push('/')}
            className="bg-blue-500 text-white p2 rounded-md"
        >
        Go Home
        </button>
    </div>

}


export default About