import { PageError } from "@crm/ui";

export const metadata = { title: "Link not available", robots: { index: false, follow: false } };

export default function NotFound() {
  return <PageError kind="not-found" title="This link isn't available" description="The society may no longer be listed, or the link was copied incompletely. Ask your property advisor for a fresh link." />;
}
