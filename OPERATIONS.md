# LeadProphet operator guide

## First launch

1. Start the app and sign in.
2. Open **Setup** for required, recommended, and optional readiness checks.
3. Open **Settings** and replace placeholder public profile values with verified details. This is the single public profile for the deployment and feeds the public contact page, metadata, and footer.
4. Use **Create first campaign**. A starter template creates a campaign, four-step sequence, and message variant.
5. Import leads from CSV or use discovery. Keep sending manual until a real email provider is configured and tested.

## Demo mode

Local, development, test, and demo environments show a `Local sandbox` banner. Owners can reset their tenant data from **Settings > Import / export** by typing `RESET SANDBOX`. The control and endpoint return 404 in production.

## Reuse and providers

Campaign detail pages support JSON export and cloning. Versioned imports validate before creation, are additive, preserve sequence/variant relationships, and scope records to the current user. Site bundles contain CMS copy and legal versions; imported drafts remain private until explicitly published.

Google OAuth and email delivery remain environment-managed. Settings shows status but never stores provider secrets in the database. Without those providers, LeadProphet still supports campaigns, ICP/scoring, lead import and deterministic discovery, drafting, sequences, tasks, reminders, and manual sending.
