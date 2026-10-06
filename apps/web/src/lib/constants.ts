export const INDUSTRIES = ["SaaS / Software", "Agency / Marketing", "Consulting", "Real Estate", "Retail / E-commerce", "Healthcare", "Education", "Finance / Fintech", "Manufacturing", "Logistics", "Hospitality", "Professional Services", "Non-profit", "Other"];
export const COMPANY_SIZES = [["1", "Just me"], ["2-5", "2–5 people"], ["6-10", "6–10 people"], ["11-25", "11–25 people"], ["26-50", "26–50 people"], ["51-200", "51–200 people"], ["201+", "200+ people"]] as const;
export const SOURCES = ["website", "referral", "linkedin", "event", "ads", "cold_outreach", "demo_request", "pricing_page", "webinar", "import", "other"];
export const label = (s: string | null | undefined) => (s ?? "").replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
export const PRIORITIES = [["low", "Low"], ["medium", "Medium"], ["high", "High"], ["urgent", "Urgent"]] as const;
export const CALL_OUTCOMES = [["connected", "Connected"], ["no_answer", "No answer"], ["follow_up_required", "Follow-up required"], ["interested", "Interested"], ["not_interested", "Not interested"]] as const;
export const ROLES_TITLES = ["Founder / CEO", "Sales leader", "Sales rep", "Marketing", "Operations", "Freelancer", "Other"];
