export const INDUSTRIES = ["SaaS / Software", "Agency / Marketing", "Consulting", "Real Estate", "Retail / E-commerce", "Healthcare", "Education", "Finance / Fintech", "Manufacturing", "Logistics", "Hospitality", "Professional Services", "Non-profit", "Other"];
export const COMPANY_SIZES = [["1", "Just me"], ["2-5", "2–5 people"], ["6-10", "6–10 people"], ["11-25", "11–25 people"], ["26-50", "26–50 people"], ["51-200", "51–200 people"], ["201+", "200+ people"]] as const;
export const SOURCES = ["99acres", "magicbricks", "housing", "walk_in", "referral", "facebook_ads", "instagram", "website", "broker", "site_visit", "cold_outreach", "import", "other"];
const SPECIAL: Record<string, string> = { magicbricks: "MagicBricks", housing: "Housing.com", walk_in: "Walk-in", facebook_ads: "Facebook ads", "99acres": "99acres", site_visit: "Site visit" };
export const label = (s: string | null | undefined) => SPECIAL[s ?? ""] ?? (s ?? "").replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
export const PRIORITIES = [["low", "Low"], ["medium", "Medium"], ["high", "High"], ["urgent", "Urgent"]] as const;
export const CALL_OUTCOMES = [["connected", "Connected"], ["no_answer", "No answer"], ["follow_up_required", "Follow-up required"], ["interested", "Interested"], ["not_interested", "Not interested"]] as const;
export const ROLES_TITLES = ["Broker / agent", "Team leader", "Brokerage owner", "Developer sales", "Channel partner", "Property consultant", "Other"];

export const INTENTS = [["buy", "Wants to buy"], ["rent", "Wants to rent"], ["invest", "Wants to invest"], ["sell", "Wants to sell"], ["lease", "Wants to lease out"]] as const;
export const PROPERTY_TYPES = [["apartment", "Flat / apartment"], ["villa", "Villa / house"], ["plot", "Plot"], ["office", "Office"], ["shop", "Shop"], ["other", "Other"]] as const;
