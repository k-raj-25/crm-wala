import { Hero } from "@/components/marketing/hero";
import { Nav } from "@/components/marketing/nav";
import { Benefits, Features, ProductPreview, TrustedBy } from "@/components/marketing/sections-a";
import { AISection, AnalyticsSection, AutomationSection } from "@/components/marketing/sections-b";
import { FAQ, FinalCTA, Footer, Integrations, Pricing, Testimonials } from "@/components/marketing/sections-c";

export default function Landing() {
  return (
    <>
      <Nav />
      <main>
        <Hero />
        <TrustedBy />
        <Benefits />
        <ProductPreview />
        <Features />
        <AISection />
        <AutomationSection />
        <AnalyticsSection />
        <Integrations />
        <Testimonials />
        <Pricing />
        <FAQ />
        <FinalCTA />
      </main>
      <Footer />
    </>
  );
}
