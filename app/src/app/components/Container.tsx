import React from "react";

interface ContainerProps {
  children: React.ReactNode;
  className?: string;
  widthChildren?: number | 'auto' | string
}

export function Container(props: Readonly<ContainerProps>) {
  return (
    <div
      className={`container p-8 mx-auto xl:px-0 ${
        props.className ? props.className : ""
      }`}>
      {props.children}
    </div>
  );
}

