import type { ReactNode } from "react";

import { Button, type ButtonProps } from "@/components/Button";
import { Tooltip } from "@/components/Tooltip";

interface IconButtonProps extends Omit<ButtonProps, "size" | "children"> {
  label: string;
  children: ReactNode;
  tooltip?: string;
}

export function IconButton({ label, tooltip = label, children, ...props }: IconButtonProps) {
  return (
    <Tooltip content={tooltip}>
      <Button size="icon" aria-label={label} title={label} {...props}>{children}</Button>
    </Tooltip>
  );
}
