import { CSSProperties, ReactNode } from "react";

interface ButtonProps {
  children?: ReactNode
  className?: string;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  disabled?: boolean;
  containerStyle?: CSSProperties;
  width?: 'small'|'regular'|'large'|'auto';
}

export default function Button(props: ButtonProps) {

  const {
    children,
    className = "",
    disabled = false,
    width = "auto",
  } = props

  const baseStyle = 'bg-indigo-500 text-white active:bg-indigo-600 font-bold rounded outline-none focus:outline-none mr-1 mb-1 ease-linear transition-all duration-150'
  const widthStyles: Record<string, string> = {
    small: "text-xs px-4 py-2 shadow hover:shadow-md",
    regular: "text-sm px-6 py-3 shadow hover:shadow-lg",
    large: "text-base px-8 py-3 shadow-md hover:shadow-lg",
    auto: "w-full text-base px-8 py-3 shadow-md hover:shadow-lg",
  };

  const onClick = (event: React.MouseEvent<HTMLButtonElement, MouseEvent>) => {
    // setTrackEvent('button', 'click', props['data-test-id']);
    props.onClick && props.onClick(event);
  };

  const disabledStyles = disabled
  ? "opacity-50 cursor-not-allowed"
  : "active:bg-indigo-600 hover:bg-indigo-600 focus:outline-none";

  return (
    <button
      className={`${baseStyle} ${widthStyles[width]} ${disabledStyles} ${className}`}
      type="button"
      onClick={onClick}
      >
        {children && (children)}
    </button>
    )
}





 