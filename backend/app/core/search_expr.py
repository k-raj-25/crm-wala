from sqlalchemy import literal_column

# These expressions are textually identical to the trigram GIN indexes created in migration 0001
# so Postgres can use the index for ILIKE '%term%'.
LEADS = literal_column("(coalesce(leads.first_name,'') || ' ' || coalesce(leads.last_name,'') || ' ' || coalesce(leads.email,'') || ' ' || coalesce(leads.company_name,''))")
CONTACTS = literal_column("(coalesce(contacts.first_name,'') || ' ' || coalesce(contacts.last_name,'') || ' ' || coalesce(contacts.email,''))")
COMPANIES = literal_column("(coalesce(companies.name,'') || ' ' || coalesce(companies.domain,''))")
DEALS = literal_column("(coalesce(deals.name,''))")
TASKS = literal_column("(coalesce(tasks.title,''))")
NOTES = literal_column("(coalesce(notes.body,''))")
