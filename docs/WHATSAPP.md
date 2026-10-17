# WhatsApp Business setup

CRM Wala talks to the **Meta WhatsApp Cloud API** directly. Each workspace (organisation) connects its **own** WhatsApp
Business number through its **own** Meta app. Nothing is shared between workspaces, and there is no sandbox mode.

## What you need (one-time, in Meta)

1. **A Meta Business portfolio** at [business.facebook.com](https://business.facebook.com), ideally verified (unverified
   businesses are limited to a small number of conversations a day).
2. **A Meta app** at [developers.facebook.com/apps](https://developers.facebook.com/apps): *Create app → Business*,
   then add the **WhatsApp** product to it.
3. **A phone number** under *WhatsApp → API Setup → Add phone number*. Use a number that is **not** registered on the
   WhatsApp or WhatsApp Business phone apps (or delete it from the app first). Verify it by SMS or call.
4. **A permanent access token**: *Business settings → Users → System users → Add* (Admin), then *Assign assets* →
   your app and your WhatsApp account (full control), then *Generate new token* for your app with the permissions
   `whatsapp_business_messaging` and `whatsapp_business_management`, expiry **Never**. Copy it.
   (The temporary token on the API Setup page expires in 24 hours. Don't use it.)
5. **Copy these four values:**
   | CRM field | Where in Meta |
   |---|---|
   | Phone number ID | WhatsApp → API Setup, under the phone number |
   | WhatsApp Business Account ID | WhatsApp → API Setup, just below |
   | Access token | the System User token from step 4 |
   | App secret | App settings → Basic → App secret → Show |
6. **Add a payment method** in WhatsApp Manager so business-initiated (template) conversations aren't blocked.

## Connect in CRM Wala

1. **Integrations → WhatsApp Business → Connect**, paste the four values, then click **Connect WhatsApp Business**.
   The CRM checks each value with Meta and subscribes your app to the WhatsApp account. If anything is wrong, it tells
   you which field.
2. The dialog then shows a **Callback URL** and a **Verify token**. In Meta: *WhatsApp → Configuration → Webhook → Edit*,
   paste both, click **Verify and save**, then under *Webhook fields* **subscribe to `messages`**.
   Without this step messages still send, but replies and delivery ticks won't arrive.
3. **Create templates** in [WhatsApp Manager → Message templates](https://business.facebook.com/wa/manage/message-templates/).
   They appear in the CRM once Meta approves them (usually minutes). Suggested ones:
   - `site_visit_reminder` (Utility): `Hi {{1}}, a reminder about your site visit to {{2}} on {{3}}.`
   - `property_brochure` (Marketing) with a **Document** header:
     `Hi {{1}}, here are the details for {{2}} you asked about.`
4. **Integrations → WhatsApp → Manage → Brochure template**: pick `property_brochure`. Its `{{1}}` is filled with the
   client's first name and `{{2}}` with the flat and project.

The API must be reachable from the internet at `WEB_ORIGIN` (Meta calls the callback URL). Run the database migrations
(`flask db upgrade`, which Render runs on every start) before first use.

## Day to day

- **Message a lead or client**: open the record → **WhatsApp** tab (or the WhatsApp button). Pick an approved template,
  fill its placeholders and check the preview. Once the client replies, you can type free messages for 24 hours.
- **Send a brochure or floor plan**: open a flat in the building view → **Brochures & floor plans** → upload a PDF
  (for *this flat* or the *whole project*) → **Send**, then choose the lead or client. If they haven't written to you in
  the last 24 hours, it goes out with your brochure template. Otherwise it goes as a plain document with your message.
- **Replies** appear on the lead's or client's **Activity** timeline and WhatsApp tab, and notify the record's owner.
  A message from a number not in the CRM creates a new lead with source *whatsapp*.
- **Ticks**: one tick = sent, two = delivered, blue = read. Failed messages show Meta's reason.

## The CRM inside WhatsApp (for your team)

Reps can update the CRM without opening the app, by messaging your company's WhatsApp number from their own phone.

1. **Link a number.** Each rep adds their mobile number to *Settings → Profile*, then opens *Settings → Notifications → WhatsApp* and presses **Link my WhatsApp**. They send the code shown (`LINK 123456`) to your company number from that phone. Only the number on a rep's profile counts as theirs, and changing it unlinks WhatsApp.
2. **Send updates.** A text or voice note such as *"Visited Priya, liked 1502, follow up Sunday"* comes back as a card with **Confirm** and **Cancel** buttons. Nothing is saved until the rep taps Confirm; the change is then made as that rep, with their permissions, and the audit log shows "(via WhatsApp)". *"New lead Neha 98765 43210, 3 BHK Baner"* prepares a new lead. Questions ("which leads haven't I called?") are answered too.
3. **Voice notes** are turned into text with your workspace's AI key, which needs to be an OpenAI key for audio. Without one, reps are asked to send text.
4. **Morning plan and new lead alerts** are opt-in per rep (switches on the same page, or send *plan on* / *alerts on*). The plan arrives at 9 AM in the workspace's timezone; *plan* sends it any time.

A linked rep's messages never become leads and never appear on a client's timeline. Client phone numbers stay hidden in WhatsApp replies for roles that can't see them.

**Team alert template.** WhatsApp only lets you message someone first within 24 hours of their last message. So that plans and alerts reach reps who haven't written that day, create a *Utility* template with one placeholder (for example `CRM Wala: {{1}}`), get it approved, and pick it under *Integrations → WhatsApp → Manage → Team alert template*. Without it, plans and alerts only go to reps who messaged in the last 24 hours.

## Rules WhatsApp enforces

- **24-hour window**: free text and plain files only go to someone who messaged you in the last 24 hours. Otherwise
  use an approved template.
- **Files**: PDFs up to 100 MB, JPG/PNG up to 5 MB. Files are uploaded to Meta directly, so your file storage never has
  to be public.
- **Templates** that need header text or button values can't be filled from the CRM yet. They're hidden from the picker.

## Troubleshooting

| You see | Fix |
|---|---|
| "Meta rejected the phone number ID or access token" | Check the ID and that the token is the System User token with both permissions |
| "…token can't manage its templates" | Regenerate the token with `whatsapp_business_management` |
| Integration shows **Reconnect** | The token expired or was revoked. Click Reconnect and paste a new token; blank fields keep their saved values |
| Messages send but no replies or ticks | Finish webhook step 2 and make sure the `messages` field is subscribed |
| "hasn't messaged you in the last 24 hours" | Send a template, or set the brochure template for files |

Environment variables (optional): `WHATSAPP_GRAPH_VERSION` (default `v21.0`) and `WHATSAPP_DEFAULT_COUNTRY_CODE`
(default `91`, added to 10-digit numbers saved without a country code).
