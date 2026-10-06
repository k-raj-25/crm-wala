"use client";
import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import * as React from "react";
import { cn } from "../lib/cn";
import { Spinner } from "./spinner";

export const buttonVariants = cva(
  "relative inline-flex shrink-0 select-none items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium transition-[background-color,box-shadow,transform,color,border-color] duration-150 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-primary text-primary-fg shadow-xs hover:bg-primary-hover hover:shadow-sm",
        secondary: "border border-border bg-surface text-fg shadow-xs hover:border-border-strong hover:bg-surface-hover",
        soft: "bg-primary-soft text-primary hover:brightness-95",
        ghost: "text-fg-muted hover:bg-surface-hover hover:text-fg",
        danger: "bg-danger text-white shadow-xs hover:brightness-110",
        "danger-soft": "bg-danger-soft text-danger hover:brightness-95",
        link: "h-auto p-0 text-primary underline-offset-4 hover:underline active:scale-100",
      },
      size: { xs: "h-7 px-2.5 text-xs", sm: "h-8 px-3 text-[13px]", md: "h-9 px-4 text-sm", lg: "h-11 px-6 text-[15px]", icon: "size-9", "icon-sm": "size-8", "icon-xs": "size-7" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, asChild, loading, children, disabled, ...props }, ref) => {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp ref={ref} className={cn(buttonVariants({ variant, size }), className)} disabled={disabled || loading} aria-busy={loading || undefined} {...props}>
      {asChild ? children : (
        <>
          {loading && <Spinner className="absolute" />}
          <span className={cn("inline-flex items-center gap-2", loading && "invisible")}>{children}</span>
        </>
      )}
    </Comp>
  );
});
Button.displayName = "Button";
