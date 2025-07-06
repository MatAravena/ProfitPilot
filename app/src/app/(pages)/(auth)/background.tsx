import { ReactNode } from "react";
import image  from "@images/background/b-ideas.jpg"

type BackgroundType = {
  children : ReactNode
}

export default function LoginBackground(props: BackgroundType) {
    return (
        <section className="relative w-full h-full py-40 min-h-screen">
        <div
          className="absolute top-0 w-full h-full bg-blueGray-800 bg-no-repeat bg-full"
          style={{
            backgroundImage: `url(${image.src})`,
            backgroundSize: "cover",
            backgroundPosition: "center",
          }}
        ></div>
        {props.children}
      </section>
    )
}
