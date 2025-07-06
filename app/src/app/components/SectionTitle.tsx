import React from "react";
import { Container } from "@components/Container";

interface SectionTitleProps {
  preTitle?: string;
  title?: string;
  align?: "left" | "center";
  children?: React.ReactNode;
  widthChildren?: number | 'auto' | string
  texts?: string[]
}

export const SectionTitle = (props: Readonly<SectionTitleProps>) => {

  const width = !props.widthChildren ? "max-w-2xl" : props.widthChildren.toString() === 'auto'? "w-auto" : `.w-${props.widthChildren}`

  return (
    <Container
      className={`flex w-full flex-col mt-4 ${
        props.align === "left" ? "" : "items-center justify-center text-center"
      }`}>

      {props.preTitle && (
        <div className="text-sm font-bold tracking-wider text-indigo-600 uppercase">
          {props.preTitle}
        </div>
      )}

      {props.title && (
        <h2 className="max-w-2xl mt-3 text-3xl font-bold leading-snug tracking-tight text-gray-800 lg:leading-tight lg:text-4xl dark:text-white">
          {props.title}
        </h2>
      )}

      {props.texts && (
        <p className={`${width} py-4 text-lg leading-normal text-gray-500 lg:text-xl xl:text-xl dark:text-gray-300`}>
          {props.texts.map((text, i) => (
            <>
              {text}
              {props.texts?.length != i && <br />}
            </>
          ))}
        </p>
      )}

      {props.children && (
        <p
          className={`${width} py-4 text-lg leading-normal text-gray-500 lg:text-xl xl:text-xl dark:text-gray-300`}>
          {props.children}
        </p>
      )}

    </Container>
  );
}
