"use client";
import { motion } from "framer-motion";
import { cn } from "@crm/ui";

export function PageHeader({ title, description, actions, tabs, className, back }: { title: React.ReactNode; description?: React.ReactNode; actions?: React.ReactNode; tabs?: React.ReactNode; className?: string; back?: React.ReactNode }) {
  return (
    <div className={cn("mb-6", className)}>
      {back}
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="min-w-0"><h1 className="truncate text-2xl font-semibold tracking-tight sm:text-[28px]">{title}</h1>{description && <p className="mt-1 text-[15px] text-fg-muted">{description}</p>}</div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {tabs && <div className="mt-5">{tabs}</div>}
    </div>
  );
}

export function PageContainer({ children, className, wide }: { children: React.ReactNode; className?: string; wide?: boolean }) {
  return <div className={cn("mx-auto w-full px-4 py-6 sm:px-8 sm:py-8", wide ? "max-w-[1600px]" : "max-w-[1280px]", className)}>{children}</div>;
}

export function Stagger({ children, className }: { children: React.ReactNode; className?: string }) {
  return <motion.div className={className} initial="hidden" animate="show" variants={{ show: { transition: { staggerChildren: 0.05 } } }}>{children}</motion.div>;
}
export const StaggerItem = ({ children, className }: { children: React.ReactNode; className?: string }) => (
  <motion.div className={className} variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: [0.16, 1, 0.3, 1] } } }}>{children}</motion.div>
);
