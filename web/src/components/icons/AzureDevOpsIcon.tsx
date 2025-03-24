import React from "react";

interface IconProps {
  size?: number;
  className?: string;
}

const defaultTailwindCSS = "my-auto flex flex-shrink-0";

export const AzureDevOpsIcon = ({
  size = 16,
  className = defaultTailwindCSS,
}: IconProps) => {
  return (
    <svg
      style={{ width: `${size}px`, height: `${size}px` }}
      className={`w-[${size}px] h-[${size}px] ` + className}
      viewBox="0 0 16 16" 
      xmlns="http://www.w3.org/2000/svg"
      fill="currentColor"
    >
      <path
        d="M15 3.622v8.512L11.5 15l-5.425-1.975v1.958L3.004 10.97l8.951.7V4.005L15 3.622zm-2.984.428L6.994 1v2.001L2.382 4.356 1 6.13v4.029l1.978.873V5.869l9.038-1.818z"
      />
    </svg>
  );
};

export default AzureDevOpsIcon; 