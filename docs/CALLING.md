# Calling through the company number (Exotel)

Employees call leads and clients from the CRM. The CRM rings the employee's own mobile from the company's virtual
number (an Exotel "ExoPhone") and bridges the client in. The client only ever sees the company number, and the
employee never sees the client's number, so a lead can't be taken outside the firm. When a client calls the company
number back, the call rings whoever handles that lead, else the fallback person (the owner by default). A live call
can be handed over: Owners and Admins to anyone, everyone else to their manager.

## 1. On Exotel

1. Sign up at exotel.com and finish KYC (Exotel needs it before an Indian number goes live).
2. Buy an **ExoPhone** (a virtual number). A mobile-style or landline number in your city both work.
3. **Settings → API Settings**: note the **Account SID**, **API key** and **API token**. Note whether your account is
   on the **Mumbai** (`api.in.exotel.com`) or **Singapore** (`api.exotel.com`) cluster.
4. Ask Exotel support to enable **Dynamic URL in the Connect applet** if it isn't on for your account.

## 2. In the CRM

1. **Integrations → Exotel calling → Connect.** Paste the Account SID, API key, API token, region and ExoPhone.
   Leave "Call flow app ID" empty for now. The CRM checks the details with Exotel and shows two webhook URLs.
2. Every employee who calls clients adds their mobile number in **Settings → Profile**. That's the phone the CRM rings.
3. **Settings → Team → Reports to**: set each employee's manager. This decides who they can hand a call to. If it
   isn't set, a more senior member of their team, then the owner, is used.

## 3. The call flow on Exotel (for callbacks and hand-overs)

In **App Bazaar → Create new flow**:

1. **Connect** applet → "Configure parameters dynamically by providing a URL" → Primary URL: the CRM's first URL
   (`…/connect`). Leave "Dial whom", recording and ringing time alone; the CRM sends those.
2. Under the Connect applet, put a **Passthru** applet in both "After the call conversation ends" and "If nobody
   answers", with the CRM's second URL (`…/handover`) and "Make Passthru Async" unticked.
   - If the URL returns **200** → another **Connect** applet set up exactly like step 1 (same URL), followed by the
     same Passthru again. Each Connect + Passthru pair allows one more hand-over; two or three pairs is plenty.
   - If it returns **302** → **Hangup**.
3. Save the flow, then in **ExoPhones** attach this flow to your ExoPhone for incoming calls.
4. Optional: copy the flow's **app ID** (App Bazaar → My Apps) into the CRM ("Change account details") and turn on
   **Ring the client first on outgoing calls**. Outgoing calls then go through the same flow, so they can be handed
   over too. Without it, outgoing calls ring the employee first and can't be handed over.

## How a hand-over works

The employee taps **Hand over** on the live-call card and picks a colleague, then hangs up their phone. Exotel moves
on to the Passthru step, the CRM answers "200", and the client (still on the line, hearing hold music) is rung through
to the colleague. If the colleague doesn't pick up, the call goes back to whoever handed it over (when "Ring the
fallback person if nobody picks up" is on). Exotel only supports this "blind" hand-over; there's no three-way intro.

## Routing settings (Integrations → Exotel calling → Manage)

- **When a client calls back, ring**: the person handling the lead (its owner) else the fallback person, or always the fallback person.
- **Fallback person**: the owner by default; anyone with a mobile number on their profile.
- **Ring the fallback person if nobody picks up**, **New numbers become leads**, **Record calls**, the spoken
  "connecting you to Priya" greeting, ring time, and **Ring the client first on outgoing calls**.

## Notes

- Calls show on the lead's timeline and Calls tab with duration and recording. Phone numbers on call records are
  masked for employees like everywhere else.
- Permissions: `calls.place` (Owner, Admin, Manager, Sales Rep) and `calls.transfer_any` (Owner, Admin).
- The provider sits behind `backend/app/services/telephony/`; Knowlarity, MyOperator or Twilio can be added as
  another adapter without touching the rest.
