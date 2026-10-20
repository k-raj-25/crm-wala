"use client";
import { PageError } from "@crm/ui";
import { useEffect } from "react";

export default function Error({ error }: { error: Error & { digest?: string } }) {
  useEffect(() => { console.error(error); }, [error]);
  return <PageError digest={error.digest} details={process.env.NODE_ENV === "development" ? error.message : undefined} />;
}
