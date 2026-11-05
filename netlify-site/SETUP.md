# CU Bus Pass on Netlify + Supabase: setup guide

This folder (`netlify-site/`) is the Netlify version of the CU Transport Department bus pass app.

| Part | What it does |
|---|---|
| **Netlify** | Hosts the website (`public/`) and three small server functions (`netlify/functions/`) |
| **Supabase** (free plan is enough to start) | Database (students, passes, stops, settings), private photo storage, staff login |

Time needed: about 20 minutes. You need a GitHub account, a Netlify account and a Supabase account (all free).

---

## 1. Create the Supabase project

1. Go to **supabase.com**, then **New project**. Pick the region **South Asia (Mumbai)** so it's close to campus. Save the database password somewhere safe.
2. When it's ready, open **SQL Editor**, then **New query**. Paste the whole of `supabase/schema.sql`, and click **Run**.
   You should see "Success". This creates the tables, the security rules, the pass functions and the private `photos` bucket.
3. **Authentication → Sign In / Providers → Email**: turn **off** "Allow new users to sign up". Only you create accounts.
4. **Authentication → Users → Add user → Create new user**: enter the transport office email and a strong password.
   Tick **Auto Confirm User**. Repeat for each staff member who needs access.
5. **Project Settings → API**: copy the **Project URL** and the **anon public** key. You'll need both in step 3.
   (Do **not** use the `service_role` key anywhere. This app doesn't need it.)

## 2. Put the code on GitHub

Create a new **private** GitHub repository and upload this project (the whole `akash` folder is fine,
or only `netlify-site/`). The `.gitignore` files keep secrets and local data out.

## 3. Create the Netlify site

1. **netlify.com → Add new site → Import an existing project → GitHub**, then choose the repository.
2. Build settings:
   - **Base directory:** `netlify-site` (leave empty if the repo contains only this folder)
   - **Build command:** *(leave empty)*
   - **Publish directory:** `public` (this is set by `netlify.toml`)
3. **Site configuration → Environment variables → Add a variable** for each of these:

   | Key | Value |
   |---|---|
   | `SUPABASE_URL` | the Project URL from step 1.5 |
   | `SUPABASE_ANON_KEY` | the anon public key from step 1.5 |
   | `QR_SIGNING_KEY` | a long random secret (see below). **Keep it private and never change it once cards are printed** |
   | `UNIVERSITY_NAME` | `Chandigarh University` |
   | `UNIVERSITY_SHORT` | `CU` |

   Make a random `QR_SIGNING_KEY` on any PC with Node installed:
   ```bash
   node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
   ```
   If cards were already printed with the Flask version, use the **same** `QR_SIGNING_KEY` as in its `.env`,
   so those cards keep verifying.
4. **Deploys → Trigger deploy**. When it's done, open the site URL (e.g. `https://cu-buspass.netlify.app`).
5. Back in Supabase: **Authentication → URL Configuration → Site URL**, then paste your Netlify URL.

## 4. First use

1. Open the site and sign in with the account from step 1.4.
2. **Card settings & stops**: check the university name and tagline, and enter the official return
   instructions, contact and helpline numbers, and notes. The pass number prefix defaults to `CU`.
3. **New bus pass**: fill in the details (fields marked ● are needed for the pass) and add a photo.
   Click **Save & create pass**, and the card with its unique offline QR opens.
4. **Print card** (front and back, 85.6 × 54 mm) or, on **Issued passes**, select several and choose **Print selected**
   (4 per A4, two-sided). In the print dialog choose **Scale 100%**, **Margins: None**, **Background graphics: on**,
   and **Save as PDF** if you want a PDF file.

## How the QR codes work

- **Offline (default):** the QR holds plain text such as *Name, UID, Class, Pickup, Valid upto* plus a signature line.
  **Any phone camera shows the details with no internet and no app.** On the **Scan QR** page, the app also checks
  the signature, so edited or forged codes are rejected, and it shows whether the pass was revoked or has expired.
- **Online (optional):** the QR is a link to `https://<your-site>/verify.html?t=<random token>`, showing live status.
- Guardian name, phone and address are **never** in a QR code or on the public verify page.

## Security notes

- Every database table has row-level security: only signed-in staff can read or change anything.
- The public verify page can only call `verify_pass()`, which returns name, UID, program, pass number and validity.
- Photos are in a **private** bucket and are shown through short-lived signed links.
- `QR_SIGNING_KEY` exists only in Netlify's environment variables. Browsers never see it.
- Backups: Supabase backs up daily on paid plans. On the free plan, use **Database → Backups** or export the tables
  as CSV from the **Table Editor** regularly.

## Running the tests

```bash
cd netlify-site
npm test
```
The function tests simulate Supabase, so no account is needed.
