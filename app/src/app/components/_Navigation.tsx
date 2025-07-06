// "use client"
// import Link from "next/link"
// import { usePathname } from "next/navigation"
// import { SignedIn, SignedOut, SignInButton, UserButton } from "@clerk/nextjs"


// export const Navigation = () => {
//     const pathname = usePathname();

//     const routes: route[] = [
//         { name: "Home", url: '/' },
//         { name: "about", url: '/about' },
//         { name: "Product 1", url: '/components/products/1' },
//     ]

//     return <nav className="flex justify-center items-center p-4">
//         {routes && Object.keys(routes).length && routes.map((route, i) =>{
//             console.log(pathname)
//             return <Link 
//                     href={route.url} key={i.toString()} 
//                     className={pathname && pathname === route.url? "font-bold mr-4" : "mr-4 text-blue-500"}>
//                         {route.name} 
//                     </Link>
//         })}

//         <SignedOut>
//             <SignInButton mode="modal" />
//         </SignedOut>
//         <SignedIn>
//             <UserButton />
//         </SignedIn>

//     </nav>
// }


// export default Navigation