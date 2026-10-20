import { PageError } from "@crm/ui";

export const metadata = { title: "Page not found" };

export default function NotFound() {
  return <PageError kind="not-found" />;
}
